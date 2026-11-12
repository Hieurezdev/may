"""Consented customer features, time-split validation, and eligible peer suggestions."""

import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from .auth import Customer, Operator, RegisteredCustomer
from .clustering import Scaler, dbscan, pair_agreement
from .db import connection, new_id
from .dtos import ConsentInput, TrainInput
from .inventory import audit
from .models import CustomerFeatures

router = APIRouter(prefix='/api',tags=['Recommendations'])


def features(db: sqlite3.Connection, cutoff: str, categories: tuple[str, ...]) -> tuple[CustomerFeatures, ...]:
    result: list[CustomerFeatures] = []
    cutoff_dt = datetime.strptime(cutoff,'%Y-%m-%d %H:%M:%S')
    for customer in db.execute('SELECT id FROM customers WHERE consent_state=1 AND email IS NOT NULL ORDER BY id').fetchall():
        orders = db.execute("SELECT id,total,delivered_at FROM orders WHERE customer_id=? AND status='delivered' AND delivered_at<=? AND delivered_at>datetime(?,'-90 days') ORDER BY delivered_at", (customer['id'],cutoff,cutoff)).fetchall()
        if not orders:
            continue
        counts: Counter[str] = Counter()
        items = 0
        refunded = 0
        return_quantity = 0
        for order in orders:
            refunded += db.execute("SELECT COALESCE(SUM(amount),0) AS n FROM refunds WHERE order_id=? AND status='succeeded' AND settled_at<=?", (order['id'],cutoff)).fetchone()['n']
            return_quantity += db.execute("SELECT COALESCE(SUM(rl.quantity),0) AS n FROM return_lines rl JOIN refunds f ON f.request_id=rl.request_id WHERE rl.order_id=? AND f.status='succeeded' AND f.settled_at<=?", (order['id'],cutoff)).fetchone()['n']
            for line in db.execute('SELECT category_snapshot,quantity FROM order_items WHERE order_id=?', (order['id'],)):
                counts[line['category_snapshot']] += line['quantity']
                items += line['quantity']
        recency = (cutoff_dt-datetime.strptime(orders[-1]['delivered_at'],'%Y-%m-%d %H:%M:%S')).total_seconds()/86400
        net = max(0,sum(o['total'] for o in orders)-refunded)
        values = (recency,math.log1p(len(orders)),math.log1p(net),items/len(orders),return_quantity/items)+tuple(counts[c]/items for c in categories)
        result.append(CustomerFeatures(customer['id'],values))
    return tuple(result)


def eligible_ids(db: sqlite3.Connection, category: str) -> set[str]:
    return {r['id'] for r in db.execute('''SELECT DISTINCT p.id FROM products p JOIN variants v ON v.product_id=p.id JOIN inventory_positions i ON i.variant_id=v.id
        WHERE p.active=1 AND v.sellable=1 AND i.on_hand>i.reserved AND (?='' OR p.category=?)''', (category,category))}


def popularity(db: sqlite3.Connection, before: str | None) -> list[str]:
    return [r['id'] for r in db.execute('''SELECT p.id,COALESCE(SUM(CASE WHEN o.status='delivered' AND (? IS NULL OR o.delivered_at<=?) THEN l.quantity ELSE 0 END),0) AS score
        FROM products p LEFT JOIN variants v ON v.product_id=p.id LEFT JOIN order_items l ON l.variant_id=v.id LEFT JOIN orders o ON o.id=l.order_id
        GROUP BY p.id ORDER BY score DESC,p.id''', (before,before))]


def peer_products(db: sqlite3.Connection, peers: set[str], before: str | None) -> list[str]:
    scores: Counter[str] = Counter()
    for peer in sorted(peers):
        for r in db.execute('''SELECT v.product_id,l.quantity FROM order_items l JOIN variants v ON v.id=l.variant_id JOIN orders o ON o.id=l.order_id
            WHERE o.customer_id=? AND o.status='delivered' AND (? IS NULL OR o.delivered_at<=?)''', (peer,before,before)):
            scores[r['product_id']] += r['quantity']
    return sorted(scores,key=lambda identity:(-scores[identity],identity))


@router.put('/me/recommendation-consent')
def consent(data: ConsentInput, customer: RegisteredCustomer) -> dict[str,bool]:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE customers SET consent_state=? WHERE id=?', (data.consent,customer))
        if not data.consent:
            versions = [r['model_version'] for r in db.execute('SELECT model_version FROM segment_assignments WHERE customer_id=?', (customer,))]
            for version in versions:
                db.execute("UPDATE segment_models SET validation_state='retired',core_samples='[]',scaler='{}' WHERE model_version=?", (version,))
                db.execute('DELETE FROM segment_assignments WHERE model_version=?', (version,))
        audit(db,customer,'recommendation.consent',customer,'granted' if data.consent else 'withdrawn')
    return {'consent':data.consent}


@router.get('/me/recommendation-consent')
def read_consent(customer: Customer) -> dict[str,bool]:
    with connection() as db:
        return {'consent':bool(db.execute('SELECT consent_state FROM customers WHERE id=?', (customer,)).fetchone()[0])}


@router.get('/recommendations')
def recommendations(customer: Customer, category: str = '') -> dict[str,str | list[str] | None]:
    with connection() as db:
        allowed = eligible_ids(db,category)
        opted_in = db.execute('SELECT consent_state FROM customers WHERE id=?', (customer,)).fetchone()[0]
        model = db.execute("SELECT model_version FROM segment_models WHERE validation_state='approved'").fetchone()
        reason = 'opt_out' if not opted_in else 'missing_model'
        ranking: list[str] = []
        version: str | None = None
        if opted_in and model:
            version = model['model_version']
            assigned = db.execute('SELECT cluster_label FROM segment_assignments WHERE customer_id=? AND model_version=?', (customer,version)).fetchone()
            reason = 'cold_start' if not assigned else 'noise' if assigned['cluster_label']==-1 else 'segment'
            if reason=='segment':
                peers = {r['customer_id'] for r in db.execute('''SELECT a.customer_id FROM segment_assignments a JOIN customers c ON c.id=a.customer_id
                    WHERE a.model_version=? AND a.cluster_label=? AND a.customer_id!=? AND c.consent_state=1''', (version,assigned['cluster_label'],customer))}
                ranking = peer_products(db,peers,None)
                if not any(p in allowed for p in ranking):
                    reason = 'empty_segment'
        if reason!='segment':
            ranking = popularity(db,None)
        result = [identity for identity in ranking if identity in allowed][:10]
        audit(db,customer,'recommendation.served',version or 'none',reason)
        return {'product_ids':result,'mode':'dbscan-peers' if reason=='segment' else 'popular','fallback_reason':None if reason=='segment' else reason,'model_version':version}


@router.post('/operator/segments/train')
def train(data: TrainInput, operator: Operator) -> dict[str,str | dict[str,float | int]]:
    try:
        cutoff_dt = datetime.fromisoformat(data.cutoff_at.replace('Z','+00:00'))
    except ValueError as exc:
        raise HTTPException(422,'cutoff_at phải là thời gian ISO 8601 có múi giờ.') from exc
    if cutoff_dt.tzinfo is None:
        raise HTTPException(422,'cutoff_at cần có múi giờ UTC hoặc offset.')
    cutoff_dt = cutoff_dt.astimezone(timezone.utc)
    if cutoff_dt>datetime.now(timezone.utc)-timedelta(days=1):
        raise HTTPException(422,'Cần ít nhất một ngày holdout sau mốc huấn luyện.')
    cutoff = cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')
    with connection() as db:
        categories = tuple(r['id'] for r in db.execute('SELECT id FROM categories ORDER BY id'))
        rows = features(db,cutoff,categories)
        if len(rows)<data.min_samples*2:
            raise HTTPException(409,'Chưa đủ khách hàng đồng ý và có đơn đã giao trong cửa sổ 90 ngày; tiếp tục gợi ý phổ biến.')
        if len(rows)>1000:
            raise HTTPException(409,'Bản DBSCAN cục bộ giới hạn 1000 khách; cần worker chuyên dụng cho dữ liệu lớn hơn.')
        scaler = Scaler.fit(tuple(r.values for r in rows))
        vectors = tuple(scaler.transform(r.values) for r in rows)
        labels,core = dbscan(vectors,data.eps,data.min_samples)
        lower,_ = dbscan(vectors,data.eps*0.9,data.min_samples)
        upper,_ = dbscan(vectors,data.eps*1.1,data.min_samples)
        holdout_count = 0
        hits = 0
        baseline_hits = 0
        baseline = set(popularity(db,cutoff)[:10])
        for row,label in zip(rows,labels):
            actual = {r['product_id'] for r in db.execute('''SELECT v.product_id FROM orders o JOIN order_items l ON l.order_id=o.id JOIN variants v ON v.id=l.variant_id
                WHERE o.customer_id=? AND o.status='delivered' AND o.delivered_at>?''', (row.customer_id,cutoff))}
            if not actual or label<0:
                continue
            peers = {r.customer_id for r,l in zip(rows,labels) if l==label and r.customer_id!=row.customer_id}
            predicted = set(peer_products(db,peers,cutoff)[:10])
            holdout_count += 1
            hits += bool(predicted & actual)
            baseline_hits += bool(baseline & actual)
        metrics: dict[str,float | int] = {'customers':len(rows),'clusters':len(set(labels)-{-1}),'noise_rate':labels.count(-1)/len(labels),
            'stability':min(pair_agreement(labels,lower),pair_agreement(labels,upper)), 'holdout_customers':holdout_count,
            'hit_rate_at_10':hits/holdout_count if holdout_count else 0,'baseline_hit_rate_at_10':baseline_hits/holdout_count if holdout_count else 0}
        version = new_id()
        schema = ['recency_days','log_frequency','log_net_spend','basket_size','return_rate']+['category:'+c for c in categories]
        db.execute('''INSERT INTO segment_models(model_version,eps,min_samples,feature_schema,scaler,core_samples,cutoff_at,validation_state,metrics)
            VALUES (?,?,?,?,?,?,?,'draft',?)''', (version,data.eps,data.min_samples,json.dumps(schema),json.dumps({'means':scaler.means,'scales':scaler.scales}),json.dumps([{'vector':vectors[i],'label':labels[i]} for i in core]),cutoff,json.dumps(metrics)))
        db.executemany('INSERT INTO segment_assignments(customer_id,model_version,cluster_label) VALUES (?,?,?)', [(r.customer_id,version,label) for r,label in zip(rows,labels)])
        audit(db,operator,'dbscan.trained',version,'Train-only scaler, completed orders and temporal holdout')
        return {'model_version':version,'validation_state':'draft','metrics':metrics}


@router.get('/operator/segments')
def models(operator: Operator) -> list[dict[str,str | float | int]]:
    with connection() as db:
        return [dict(r) for r in db.execute('SELECT model_version,eps,min_samples,cutoff_at,validation_state,metrics FROM segment_models ORDER BY rowid DESC')]


@router.post('/operator/segments/{version}/approve')
def approve(version: str, operator: Operator) -> dict[str,str]:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM segment_models WHERE model_version=?', (version,)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy phiên bản mô hình.')
        m = json.loads(row['metrics'])
        if row['validation_state']!='draft' or m['clusters']<1 or m['noise_rate']>0.6 or m['stability']<0.8 or m['holdout_customers']<2 or m['hit_rate_at_10']<m['baseline_hit_rate_at_10']:
            raise HTTPException(409,'Mô hình chưa đạt cổng kiểm tra về cụm, nhiễu, độ ổn định và holdout; giữ mô hình đang dùng.')
        db.execute("UPDATE segment_models SET validation_state='retired' WHERE validation_state='approved'")
        db.execute("UPDATE segment_models SET validation_state='approved' WHERE model_version=?", (version,))
        audit(db,operator,'dbscan.approved',version,'Validation gate passed')
    return {'model_version':version,'validation_state':'approved'}
