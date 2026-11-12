"""Behavioral integration coverage for transaction and authorization invariants."""

import base64
import io
import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from backend import db
from backend.clustering import Scaler, dbscan
from backend.dtos import EmbeddingResponse
from backend.main import app
from backend.payments import signature


class CommerceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory=tempfile.TemporaryDirectory()
        self.database=patch.object(db,'DB_PATH',Path(self.directory.name)/'test.sqlite3')
        self.database.start()
        self.environment=patch.dict(os.environ,{'MAY_DEMO_MODE':'1'})
        self.environment.start()
        self.client=TestClient(app)
        self.client.__enter__()
        self.customer=self.client.get('/api/me').json()['id']
        self.product=self.client.get('/api/products').json()[0]
        self.variant=self.product['variants'][0]['id']
        self.staff: list[TestClient]=[]

    def tearDown(self) -> None:
        for client in self.staff:
            client.__exit__(None,None,None)
        self.client.__exit__(None,None,None)
        self.environment.stop()
        self.database.stop()
        self.directory.cleanup()

    def actor(self,role: str) -> TestClient:
        client=TestClient(app)
        client.__enter__()
        client.get('/api/me')
        response=client.post('/api/auth/login',json={'email':role+'@may.local','password':'MayDemo2026!'})
        self.assertEqual(response.status_code,200,response.text)
        self.staff.append(client)
        return client

    def purchase(self,quantity: int,method: str,key: str) -> dict:
        added=self.client.post('/api/cart',json={'variant_id':self.variant,'quantity':quantity})
        self.assertEqual(added.status_code,200,added.text)
        quote=self.client.post('/api/checkout/quote',json={}).json()
        response=self.client.post('/api/orders',json={'recipient_name':'Khách thử nghiệm','phone':'0901234567','address':'123 Nguyễn Huệ, Quận 1, TP HCM','payment_method':method,'idempotency_key':key,'expected_total':quote['total']})
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def payment_event(self,order: dict,outcome: str,event_id: str) -> bytes:
        with db.connection() as conn:
            attempt=conn.execute('SELECT * FROM payment_attempts WHERE order_id=?',(order['id'],)).fetchone()
        return json.dumps({'event_id':event_id,'attempt_id':attempt['id'],'provider_reference':attempt['provider_reference'],'amount':attempt['amount'],'currency':'VND','outcome':outcome}).encode()

    def callback(self,payload: bytes):
        return self.client.post('/api/payments/callback',content=payload,headers={'X-Signature':signature(payload),'Content-Type':'application/json'})

    def fulfill(self,order: dict) -> dict:
        merchant=self.actor('merchant')
        self.assertEqual(merchant.patch('/api/admin/orders/'+order['id'],json={'status':'processing'}).status_code,200)
        self.assertEqual(merchant.post('/api/admin/orders/'+order['id']+'/ship',json={'provider':'Local carrier','tracking_code':'TRACK-'+order['id']}).status_code,200)
        response=merchant.patch('/api/admin/orders/'+order['id'],json={'status':'delivered'})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_stock_is_held_then_dispatched_exactly_once(self) -> None:
        order=self.purchase(2,'online-demo','stock-held-test-key')
        with db.connection() as conn:
            before=conn.execute('SELECT on_hand,reserved FROM inventory_positions WHERE variant_id=?',(self.variant,)).fetchone()
            self.assertEqual(before['reserved'],2)
        paid=self.callback(self.payment_event(order,'captured','capture-1'))
        self.assertEqual(paid.json()['status'],'paid')
        self.fulfill(order)
        with db.connection() as conn:
            after=conn.execute('SELECT on_hand,reserved FROM inventory_positions WHERE variant_id=?',(self.variant,)).fetchone()
            self.assertEqual(after['on_hand'],before['on_hand']-2)
            self.assertEqual(after['reserved'],0)
        merchant=self.staff[-1]
        self.assertEqual(merchant.post('/api/admin/orders/'+order['id']+'/ship',json={'provider':'Carrier','tracking_code':'SECOND'}).status_code,409)

    def test_callback_requires_signature_matching_money_and_unique_payload(self) -> None:
        order=self.purchase(1,'online-demo','signed-payment-test')
        raw=self.payment_event(order,'captured','event-unique')
        self.assertEqual(self.client.post('/api/payments/callback',content=raw,headers={'X-Signature':'bad'}).status_code,401)
        invalid=json.loads(raw);invalid['amount']+=1
        self.assertEqual(self.callback(json.dumps(invalid).encode()).status_code,422)
        for _ in range(2):
            self.assertEqual(self.callback(raw).json()['payment_status'],'captured')
        invalid=json.loads(raw);invalid['outcome']='failed'
        self.assertEqual(self.callback(json.dumps(invalid).encode()).status_code,409)
        later=self.payment_event(order,'failed','late-failure')
        self.assertEqual(self.callback(later).json()['payment_status'],'captured')
        with db.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM provider_events').fetchone()[0],2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outbox_events WHERE kind='payment.captured'").fetchone()[0],1)

    def test_late_capture_requires_reconciliation_without_reacquiring_stock(self) -> None:
        order=self.purchase(1,'online-demo','late-capture-test-key')
        with db.connection() as conn:
            conn.execute("UPDATE reservations SET expires_at=datetime('now','-1 minute')")
        late=self.callback(self.payment_event(order,'captured','late-capture'))
        self.assertEqual(late.json()['status'],'reconciliation')
        with db.connection() as conn:
            self.assertEqual(conn.execute('SELECT reserved FROM inventory_positions WHERE variant_id=?',(self.variant,)).fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT state FROM reservations').fetchone()[0],'released')
        merchant=self.actor('merchant')
        self.assertEqual(merchant.patch('/api/admin/orders/'+order['id'],json={'status':'processing'}).status_code,409)

    def test_last_unit_has_only_one_successful_concurrent_checkout(self) -> None:
        other=TestClient(app);other.__enter__();self.staff.append(other)
        other.get('/api/me')
        with db.connection() as conn:
            conn.execute('UPDATE inventory_positions SET on_hand=1 WHERE variant_id=?',(self.variant,))
        for client in [self.client,other]:
            self.assertEqual(client.post('/api/cart',json={'variant_id':self.variant,'quantity':1}).status_code,200)
        total=self.client.post('/api/checkout/quote',json={}).json()['total']
        def submit(args):
            client,key=args
            return client.post('/api/orders',json={'recipient_name':'Test shopper','phone':'0901234567','address':'123 Nguyễn Huệ, TP HCM','payment_method':'cod','idempotency_key':key,'expected_total':total}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(submit,[(self.client,'last-unit-client-one'),(other,'last-unit-client-two')]))
        self.assertEqual(sorted(outcomes),[201,409])
        with db.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1)
            self.assertEqual(tuple(conn.execute('SELECT on_hand,reserved FROM inventory_positions WHERE variant_id=?',(self.variant,)).fetchone()),(1,1))

    def test_idempotency_payload_conflict_and_quote_change_rollback(self) -> None:
        self.client.post('/api/cart',json={'variant_id':self.variant,'quantity':1})
        data={'recipient_name':'Test buyer','phone':'0901234567','address':'123 Nguyễn Huệ, TP HCM','payment_method':'cod','idempotency_key':'conflicting-key-0001','expected_total':1}
        changed=self.client.post('/api/orders',json=data)
        self.assertEqual(changed.status_code,409)
        self.assertEqual(changed.json()['detail']['code'],'quote_changed')
        with db.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],0)
        self.assertEqual(len(self.client.get('/api/cart').json()),1)
        data['expected_total']=changed.json()['detail']['quote']['total']
        data['idempotency_key']='reconfirmed-key-0001'
        first=self.client.post('/api/orders',json=data)
        self.assertEqual(first.status_code,201)
        self.assertEqual(self.client.post('/api/orders',json=data).json()['id'],first.json()['id'])
        self.assertEqual(self.client.post('/api/orders',json={**data,'address':'Another address, TP HCM'}).status_code,409)
        with db.connection() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('UPDATE order_items SET unit_price=1')

    def test_checkout_requires_an_explicit_integer_confirmed_total(self) -> None:
        self.client.post('/api/cart',json={'variant_id':self.variant,'quantity':1})
        command={'recipient_name':'Test buyer','phone':'0901234567','address':'123 Nguyễn Huệ, TP HCM','payment_method':'cod','idempotency_key':'required-quote-0001'}
        for value in [None,True,'100000',-1]:
            with self.subTest(value=value):
                self.assertEqual(self.client.post('/api/orders',json={**command,'expected_total':value}).status_code,422)
        self.assertEqual(self.client.post('/api/orders',json=command).status_code,422)
        with db.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],0)
        self.assertEqual(len(self.client.get('/api/cart').json()),1)

    def test_role_separation_and_inventory_reserved_floor(self) -> None:
        order=self.purchase(2,'cod','role-separation-test')
        merchant=self.actor('merchant');support=self.actor('support');operator=self.actor('operator')
        self.assertEqual(support.get('/api/admin/orders').status_code,403)
        self.assertEqual(merchant.get('/api/support/returns').status_code,403)
        self.assertEqual(operator.patch('/api/admin/variants/'+self.variant,json={'stock':0}).status_code,403)
        self.assertEqual(merchant.patch('/api/admin/variants/'+self.variant,json={'stock':1}).status_code,409)
        self.assertEqual(self.client.get('/api/operator/audit').status_code,401)
        self.assertEqual(support.patch('/api/admin/orders/'+order['id'],json={'status':'delivered'}).status_code,403)

    def test_partial_returns_refunds_and_restock_are_bounded(self) -> None:
        order=self.fulfill(self.purchase(2,'cod','return-test-purchase'))
        line=order['items'][0]['id']
        request=self.client.post('/api/orders/'+order['id']+'/returns',json={'reason':'Wrong size on delivery','lines':[{'order_line_id':line,'quantity':1}]})
        self.assertEqual(request.status_code,201,request.text)
        request_id=request.json()['id']
        duplicate=self.client.post('/api/orders/'+order['id']+'/returns',json={'reason':'Too many returned items','lines':[{'order_line_id':line,'quantity':2}]})
        self.assertEqual(duplicate.status_code,409)
        support=self.actor('support');merchant=self.staff[0];operator=self.actor('operator')
        refund_path='/api/support/returns/'+request_id+'/refund'
        key={'idempotency_key':'partial-refund-key-0001'}
        self.assertEqual(support.post(refund_path,json=key).status_code,409)
        support.patch('/api/support/returns/'+request_id,json={'decision':'approve','reason':'Within return policy'}).raise_for_status()
        inspection={'accepted':True,'restock':True,'reason':'Labels intact and unused'}
        merchant.post('/api/admin/returns/'+request_id+'/inspect',json=inspection).raise_for_status()
        self.assertEqual(merchant.post('/api/admin/returns/'+request_id+'/inspect',json=inspection).status_code,409)
        for _ in range(2):
            refunded=support.post(refund_path,json=key)
            self.assertEqual(refunded.status_code,200,refunded.text)
            self.assertEqual(refunded.json()['refund_amount'],order['items'][0]['unit_price'])
        refunds=operator.get('/api/operator/refunds').json()
        self.assertEqual(len(refunds),1)
        operator.post('/api/operator/refunds/'+refunds[0]['id']+'/demo-settle').raise_for_status()
        operator.post('/api/operator/refunds/'+refunds[0]['id']+'/demo-settle').raise_for_status()
        final=self.client.get('/api/orders/'+order['id']).json()
        self.assertEqual(final['payment_status'],'partially_refunded')
        self.assertEqual(final['returns'][0]['status'],'completed')

    def test_nonowned_or_undelivered_return_is_rejected(self) -> None:
        order=self.purchase(1,'cod','undelivered-returns')
        request={'reason':'Not eligible before delivery','lines':[{'order_line_id':order['items'][0]['id'],'quantity':1}]}
        self.assertEqual(self.client.post('/api/orders/'+order['id']+'/returns',json=request).status_code,409)
        other=TestClient(app);other.__enter__();self.staff.append(other);other.get('/api/me')
        self.assertEqual(other.post('/api/orders/'+order['id']+'/returns',json=request).status_code,404)

    def test_paid_cancellation_creates_only_one_pending_refund(self) -> None:
        order=self.purchase(1,'online-demo','paid-cancel-test-key')
        self.callback(self.payment_event(order,'captured','cancel-capture'))
        for _ in range(2):
            result=self.client.post('/api/orders/'+order['id']+'/cancel',json={'reason':'Changed delivery schedule'})
            self.assertEqual(result.status_code,200,result.text)
        with db.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM refunds').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT amount FROM refunds').fetchone()[0],order['total'])
            self.assertEqual(conn.execute('SELECT reserved FROM inventory_positions WHERE variant_id=?',(self.variant,)).fetchone()[0],0)

    def test_search_eligibility_consent_and_explicit_fallback(self) -> None:
        with patch('backend.discovery.embed_text',new_callable=AsyncMock) as embed:
            from fastapi import HTTPException
            embed.side_effect=HTTPException(503,'Not configured')
            result=self.client.post('/api/search',json={'query':'áo len'})
        self.assertEqual(result.status_code,200)
        self.assertTrue(result.json()['product_ids'])
        self.assertEqual(result.json()['fallback_reason'],'text_encoder_unavailable')
        with db.connection() as conn:
            conn.execute('UPDATE products SET active=0 WHERE id=?',(result.json()['product_ids'][0],))
        next_result=self.client.post('/api/search',json={'query':'áo len','semantic':False}).json()
        self.assertNotIn(result.json()['product_ids'][0],next_result['product_ids'])
        self.assertEqual(self.client.post('/api/search',json={'image_base64':'YWJj'}).status_code,422)
        self.assertEqual(self.client.post('/api/search',json={'image_base64':'YWJj','media_consent':True}).status_code,422)
        self.assertEqual(self.client.post('/api/search/transcribe',content=b'audio'*100,headers={'Content-Type':'audio/webm'}).status_code,422)

    def test_vector_index_versions_and_stale_source_filter(self) -> None:
        operator=self.actor('operator')
        async def fake_embedding(text: str) -> EmbeddingResponse:
            return EmbeddingResponse(model_revision='test-text-v1',vector=[1.0,float(len(text)%10+1)])
        with patch('backend.discovery.embed_text',side_effect=fake_embedding):
            built=operator.post('/api/operator/indexes/build',json={'kind':'text'})
            self.assertEqual(built.status_code,200,built.text)
            with db.connection() as conn:
                conn.execute('UPDATE products SET name=?,source_version=source_version+1 WHERE id=?',('Removed lexical phrase',self.product['id']))
            result=self.client.post('/api/search',json={'query':'zzzz','limit':100}).json()
        self.assertNotIn(self.product['id'],result['product_ids'])
        self.assertEqual(result['mode'],'hybrid')

    def test_image_search_uses_only_the_visual_encoder(self) -> None:
        operator=self.actor('operator')
        image=io.BytesIO();Image.new('RGB',(8,8),'red').save(image,format='PNG')
        with patch('backend.discovery.embed_image',new_callable=AsyncMock,return_value=EmbeddingResponse(model_revision='test-visual-v1',vector=[1.0,0.0])) as visual:
            built=operator.post('/api/operator/indexes/build',json={'kind':'image'})
            self.assertEqual(built.status_code,200,built.text)
            with patch('backend.discovery.embed_text',new_callable=AsyncMock) as text:
                result=self.client.post('/api/search',json={'image_base64':base64.b64encode(image.getvalue()).decode(),'media_consent':True})
                self.assertEqual(result.status_code,200,result.text)
                self.assertTrue(result.json()['product_ids'])
                text.assert_not_called()
                self.assertTrue(visual.called)

    def test_consent_and_insufficient_training_do_not_promote_model(self) -> None:
        self.assertEqual(self.client.get('/api/recommendations').json()['fallback_reason'],'opt_out')
        self.client.post('/api/auth/register',json={'email':'consented@example.com','password':'A-private-password','full_name':'Test customer'}).raise_for_status()
        self.client.put('/api/me/recommendation-consent',json={'consent':True}).raise_for_status()
        self.assertEqual(self.client.get('/api/recommendations').json()['fallback_reason'],'missing_model')
        operator=self.actor('operator')
        trained=operator.post('/api/operator/segments/train',json={'eps':1.5,'min_samples':2,'cutoff_at':'2026-10-01T00:00:00Z'})
        self.assertEqual(trained.status_code,409)
        self.assertEqual(operator.get('/api/operator/segments').json(),[])
        self.client.put('/api/me/recommendation-consent',json={'consent':False}).raise_for_status()
        self.assertEqual(self.client.get('/api/recommendations').json()['mode'],'popular')


    def test_guest_access_proof_is_order_scoped_and_expires(self) -> None:
        order=self.purchase(1,'cod','guest-proof-purchase')
        token=self.client.post('/api/orders/'+order['id']+'/guest-access').json()['access_token']
        other=TestClient(app);other.__enter__();self.staff.append(other)
        path='/api/guest/orders/'+order['id']
        self.assertEqual(other.get(path).status_code,401)
        self.assertEqual(other.get(path,headers={'Authorization':'Bearer '+token}).status_code,200)
        with db.connection() as conn:
            conn.execute("UPDATE guest_access_proofs SET expires_at=datetime('now','-1 minute')")
        self.assertEqual(other.get(path,headers={'Authorization':'Bearer '+token}).status_code,404)

    def test_successful_training_promotion_serving_and_consent_withdrawal(self) -> None:
        # Historical snapshots are explicit synthetic fixtures, never seeded as real sales.
        variants=[self.variant,self.client.get('/api/products',params={'category':'bottoms'}).json()[0]['variants'][0]['id']]
        customers=[]
        with db.connection() as conn:
            for index in range(4):
                customer=db.new_id();customers.append(customer)
                conn.execute('INSERT INTO customers(id,email,consent_state) VALUES (?,?,1)',(customer,f'history-{index}@example.com'))
                variant=conn.execute('SELECT v.*,p.name,p.image,p.category FROM variants v JOIN products p ON p.id=v.product_id WHERE v.id=?',(variants[index//2],)).fetchone()
                for phase,when in [('train','2026-09-20 12:00:00'),('holdout','2026-10-10 12:00:00')]:
                    order=db.new_id();line=db.new_id()
                    conn.execute("""INSERT INTO orders(id,customer_id,recipient_name,phone,address,subtotal,discount,shipping,total,status,payment_method,payment_status,idempotency_key,request_hash,delivered_at)
                        VALUES (?,?,?,'0901234567','Synthetic fixture address',?,0,0,?,'delivered','cod','captured',?,?,?)""",(order,customer,'Synthetic fixture',variant['price'],variant['price'],f'{index}-{phase}','fixture',when))
                    conn.execute('''INSERT INTO order_items(id,order_id,variant_id,sku_snapshot,name,color,size,image,category_snapshot,quantity,unit_price)
                        VALUES (?,?,?,?,?,?,?,?,?,1,?)''',(line,order,variant['id'],variant['sku'],variant['name'],variant['color'],variant['size'],variant['image'],variant['category'],variant['price']))
        operator=self.actor('operator')
        trained=operator.post('/api/operator/segments/train',json={'eps':0.5,'min_samples':2,'cutoff_at':'2026-10-01T00:00:00Z'})
        self.assertEqual(trained.status_code,200,trained.text)
        version=trained.json()['model_version']
        self.assertEqual(trained.json()['metrics']['clusters'],2)
        self.assertEqual(trained.json()['metrics']['holdout_customers'],4)
        self.assertEqual(operator.post('/api/operator/segments/'+version+'/approve').status_code,200)
        from backend.recommendations import recommendations, consent
        from backend.dtos import ConsentInput
        result=recommendations(customers[0])
        self.assertEqual(result['mode'],'dbscan-peers')
        self.assertTrue(result['product_ids'])
        consent(ConsentInput(consent=False),customers[0])
        with db.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM segment_assignments WHERE model_version=?',(version,)).fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT core_samples FROM segment_models WHERE model_version=?',(version,)).fetchone()[0],'[]')
        self.assertEqual(recommendations(customers[1])['fallback_reason'],'missing_model')

    def test_notification_outbox_retries_only_transient_failure(self) -> None:
        import httpx
        order=self.purchase(1,'cod','outbox-purchase-key')
        operator=self.actor('operator')
        self.assertEqual(operator.get('/api/operator/outbox').status_code,200)
        original_client=httpx.AsyncClient
        config={'NOTIFICATION_URL':'https://notifications.example/events','NOTIFICATION_SECRET':'test-notification-key'}
        def unavailable(request: httpx.Request) -> httpx.Response:
            self.assertIn('idempotency-key',request.headers)
            self.assertNotIn('phone',request.content.decode())
            return httpx.Response(503)
        with patch('backend.notifications.setting',side_effect=config.get):
            with patch('backend.notifications.httpx.AsyncClient',side_effect=lambda **kw:original_client(transport=httpx.MockTransport(unavailable),**kw)):
                result=operator.post('/api/operator/outbox/dispatch')
                self.assertEqual(result.json()['retrying'],1)
            with db.connection() as conn:
                conn.execute("UPDATE outbox_events SET next_attempt_at=datetime('now','-1 second')")
            with patch('backend.notifications.httpx.AsyncClient',side_effect=lambda **kw:original_client(transport=httpx.MockTransport(lambda r:httpx.Response(400)),**kw)):
                result=operator.post('/api/operator/outbox/dispatch')
                self.assertEqual(result.json()['failed'],1)
        with db.connection() as conn:
            self.assertEqual(conn.execute('SELECT status FROM outbox_events WHERE aggregate_id=?',(order['id'],)).fetchone()[0],'failed')

    def test_merchant_creates_product_with_real_foreign_keys(self) -> None:
        merchant=self.actor('merchant')
        result=merchant.post('/api/admin/products',json={'name':'Áo thử nghiệm mới','brand':'Coursework','category':'tops','image':self.product['image'],'variants':[{'color':'Beige','size':'M','price':200000,'on_hand':4}],'reason':'Create a new coursework catalog item'})
        self.assertEqual(result.status_code,201,result.text)
        product=result.json()
        self.assertEqual(product['variants'][0]['stock'],4)
        self.assertEqual(self.client.get('/api/products/'+product['id']).status_code,200)
        with db.connection() as conn:
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])


class ClusteringTests(unittest.TestCase):
    def test_dbscan_cluster_noise_and_border_point(self) -> None:
        labels,core=dbscan(((0.0,),(0.1,),(0.2,),(5.0,),(5.1,),(20.0,)),0.15,2)
        self.assertEqual(labels,(0,0,0,1,1,-1))
        self.assertNotIn(5,core)
        # Noise encountered before a core is reclassified as a border member.
        labels,_=dbscan(((0.0,),(0.1,),(0.2,)),0.15,3)
        self.assertEqual(labels,(0,0,0))

    def test_scaler_is_fitted_only_on_training_rows(self) -> None:
        scaler=Scaler.fit(((1.0,3.0),(3.0,3.0)))
        self.assertEqual(scaler.means,(2.0,3.0))
        self.assertEqual(scaler.transform((101.0,3.0)),(99.0,0.0))
        self.assertEqual(scaler.means,(2.0,3.0))
        with self.assertRaises(ValueError):
            scaler.transform((1.0,))
