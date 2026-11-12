"""Verified callback processing; the demo uses the same signature and event path."""

import hashlib
import hmac
import os
import secrets
import sqlite3

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

from .auth import Customer, Operator
from .config import setting
from .db import connection, new_id
from .dtos import CallbackInput, OrderResult, PaymentInput, RefundCallback
from .inventory import audit, expire, notify, release
from .order_views import order_result, owned_order

router = APIRouter(prefix='/api',tags=['Payments'])
_DEMO_SECRET = secrets.token_bytes(32)


def signing_key() -> bytes:
    key = setting('PAYMENT_WEBHOOK_SECRET')
    if key:
        return key.encode()
    if os.environ.get('MAY_DEMO_MODE')=='1':
        return _DEMO_SECRET
    raise HTTPException(503,'Chưa cấu hình khóa xác thực callback thanh toán.')


def signature(payload: bytes) -> str:
    return hmac.new(signing_key(),payload,hashlib.sha256).hexdigest()


def check_signature(payload: bytes, supplied: str) -> None:
    if not hmac.compare_digest(signature(payload),supplied):
        raise HTTPException(401,'Chữ ký callback không hợp lệ.')


def record_event(db: sqlite3.Connection, event: CallbackInput | RefundCallback, payload: bytes, kind: str) -> bool:
    digest = hashlib.sha256(payload).hexdigest()
    existing = db.execute("SELECT payload_hash FROM provider_events WHERE provider='demo' AND event_id=?", (event.event_id,)).fetchone()
    if existing:
        if existing['payload_hash'] != digest:
            raise HTTPException(409,'Mã sự kiện đã được dùng cho nội dung khác.')
        return False
    attempt = event.attempt_id if isinstance(event,CallbackInput) else None
    refund = event.refund_id if isinstance(event,RefundCallback) else None
    db.execute("INSERT INTO provider_events(provider,event_id,attempt_id,refund_id,kind,payload_hash,outcome) VALUES ('demo',?,?,?,?,?,?)", (event.event_id,attempt,refund,kind,digest,event.outcome))
    return True


def process_payment(event: CallbackInput, raw: bytes) -> OrderResult:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        attempt = db.execute("SELECT * FROM payment_attempts WHERE id=? AND provider='demo'", (event.attempt_id,)).fetchone()
        if not attempt:
            raise HTTPException(404,'Không tìm thấy lần thanh toán.')
        if (event.amount,event.currency,event.provider_reference)!=(attempt['amount'],attempt['currency'],attempt['provider_reference']):
            raise HTTPException(422,'Số tiền, loại tiền hoặc mã giao dịch không khớp.')
        row = db.execute('SELECT * FROM orders WHERE id=?', (attempt['order_id'],)).fetchone()
        if not record_event(db,event,raw,'payment'):
            return order_result(db,row)
        # Failure events arriving after capture cannot undo captured money.
        if attempt['status'] in {'captured','reconciliation'}:
            return order_result(db,row)
        if event.outcome=='captured':
            holds = db.execute('''SELECT r.state FROM reservations r JOIN order_items l ON l.id=r.order_line_id WHERE l.order_id=?''', (row['id'],)).fetchall()
            state = 'captured' if row['status']=='pending_payment' and holds and all(r['state']=='held' for r in holds) else 'reconciliation'
            db.execute('UPDATE payment_attempts SET status=? WHERE id=?', (state,attempt['id']))
            db.execute('UPDATE orders SET payment_status=?,status=? WHERE id=?', (state,'paid' if state=='captured' else 'reconciliation',row['id']))
            if state=='captured':
                db.execute("UPDATE reservations SET state='committed' WHERE order_line_id IN (SELECT id FROM order_items WHERE order_id=?) AND state='held'", (row['id'],))
        else:
            release(db,row['id'])
            db.execute('UPDATE payment_attempts SET status=? WHERE id=?', (event.outcome,attempt['id']))
            db.execute("UPDATE orders SET payment_status=?,status='payment_failed' WHERE id=? AND status='pending_payment'", (event.outcome,row['id']))
        audit(db,None,'payment.callback',row['id'],event.outcome)
        notify(db,row['id'],'payment.'+event.outcome)
        return order_result(db,db.execute('SELECT * FROM orders WHERE id=?', (row['id'],)).fetchone())


@router.post('/payments/callback',response_model=OrderResult)
async def payment_callback(request: Request, x_signature: str = Header(default='')) -> OrderResult:
    raw = await request.body()
    if len(raw)>16384:
        raise HTTPException(413,'Callback quá lớn.')
    check_signature(raw,x_signature)
    try:
        event = CallbackInput.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422,'Callback không đúng hợp đồng.') from exc
    return process_payment(event,raw)


@router.post('/orders/{order_id}/demo-payment',response_model=OrderResult)
def demo_payment(order_id: str, data: PaymentInput, customer: Customer) -> OrderResult:
    if os.environ.get('MAY_DEMO_MODE')!='1':
        raise HTTPException(404,'Mô phỏng thanh toán chưa được bật.')
    with connection() as db:
        row = owned_order(db,order_id,customer)
        if row['payment_method']!='online-demo':
            raise HTTPException(409,'Đơn COD không hỗ trợ thao tác này.')
        if row['payment_status']=='captured':
            return order_result(db,row)
        if row['status']!='pending_payment':
            raise HTTPException(409,'Đơn đã kết thúc thanh toán; hãy đặt lại đơn hoặc liên hệ hỗ trợ.')
        attempt = db.execute('SELECT * FROM payment_attempts WHERE order_id=?', (order_id,)).fetchone()
        event = CallbackInput(event_id=new_id(),attempt_id=attempt['id'],provider_reference=attempt['provider_reference'],amount=attempt['amount'],currency='VND',outcome={'success':'captured','failure':'failed','cancel':'cancelled'}[data.outcome])
    raw = event.model_dump_json().encode()
    check_signature(raw,signature(raw))
    return process_payment(event,raw)


def create_refund(db: sqlite3.Connection, order: sqlite3.Row, request_id: str | None, amount: int, key: str, reason: str) -> sqlite3.Row:
    previous = db.execute('SELECT * FROM refunds WHERE idempotency_key=?', (key,)).fetchone()
    if previous:
        if (previous['order_id'],previous['request_id'],previous['amount'])!=(order['id'],request_id,amount):
            raise HTTPException(409,'Khóa hoàn tiền đã được dùng cho nội dung khác.')
        return previous
    attempt = db.execute("SELECT * FROM payment_attempts WHERE order_id=? AND status IN ('captured','reconciliation')", (order['id'],)).fetchone()
    if not attempt:
        raise HTTPException(409,'Chưa có khoản tiền đã thu để hoàn.')
    allocated = db.execute("SELECT COALESCE(SUM(amount),0) AS n FROM refunds WHERE attempt_id=? AND status IN ('pending','succeeded','reconciliation')", (attempt['id'],)).fetchone()['n']
    if amount<=0 or allocated+amount>attempt['amount']:
        raise HTTPException(409,'Số tiền hoàn vượt phần đã thu còn lại.')
    existing = db.execute('SELECT * FROM refunds WHERE request_id=?', (request_id,)).fetchone() if request_id else None
    if existing:
        if existing['status']!='failed':
            raise HTTPException(409,'Yêu cầu đã có giao dịch hoàn tiền.')
        identity = existing['id']
        db.execute("UPDATE refunds SET status='pending',idempotency_key=? WHERE id=?", (key,identity))
    else:
        identity = new_id()
        db.execute("INSERT INTO refunds(id,request_id,order_id,attempt_id,amount,status,idempotency_key,reason) VALUES (?,?,?,?,?,'pending',?,?)", (identity,request_id,order['id'],attempt['id'],amount,key,reason))
    notify(db,order['id'],'refund.requested')
    return db.execute('SELECT * FROM refunds WHERE id=?', (identity,)).fetchone()


def process_refund(event: RefundCallback, raw: bytes) -> dict[str,str]:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM refunds WHERE id=?', (event.refund_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy giao dịch hoàn.')
        if event.amount!=row['amount']:
            raise HTTPException(422,'Số tiền hoàn không khớp.')
        if not record_event(db,event,raw,'refund') or row['status']=='succeeded':
            return {'id':row['id'],'status':row['status']}
        if event.outcome=='succeeded' and row['status'] in {'failed','reconciliation'}:
            attempt = db.execute('SELECT amount FROM payment_attempts WHERE id=?', (row['attempt_id'],)).fetchone()
            other = db.execute("SELECT COALESCE(SUM(amount),0) AS n FROM refunds WHERE attempt_id=? AND id!=? AND status IN ('pending','succeeded','reconciliation')", (row['attempt_id'],row['id'])).fetchone()['n']
            if other+row['amount']>attempt['amount']:
                db.execute("UPDATE refunds SET status='reconciliation',settled_at=CURRENT_TIMESTAMP WHERE id=?", (row['id'],))
                db.execute("UPDATE orders SET status='reconciliation',payment_status='reconciliation' WHERE id=?", (row['order_id'],))
                audit(db,None,'refund.reconciliation',row['id'],'Late completion conflicts with another refund allocation')
                notify(db,row['order_id'],'refund.reconciliation')
                return {'id':row['id'],'status':'reconciliation'}
        db.execute('UPDATE refunds SET status=?,settled_at=CURRENT_TIMESTAMP WHERE id=?', (event.outcome,row['id']))
        if row['request_id']:
            db.execute('UPDATE return_requests SET status=? WHERE id=?', ('completed' if event.outcome=='succeeded' else 'inspected',row['request_id']))
        refunded = db.execute("SELECT COALESCE(SUM(amount),0) AS n FROM refunds WHERE order_id=? AND status='succeeded'", (row['order_id'],)).fetchone()['n']
        order = db.execute('SELECT total FROM orders WHERE id=?', (row['order_id'],)).fetchone()
        pending = db.execute("SELECT 1 FROM refunds WHERE order_id=? AND status='pending'", (row['order_id'],)).fetchone()
        status = 'refunded' if refunded==order['total'] else 'partially_refunded' if refunded else 'refund_pending' if pending else 'captured'
        db.execute('UPDATE orders SET payment_status=? WHERE id=?', (status,row['order_id']))
        audit(db,None,'refund.callback',row['id'],event.outcome)
        notify(db,row['order_id'],'refund.'+event.outcome)
        return {'id':row['id'],'status':event.outcome}


@router.post('/refunds/callback')
async def refund_callback(request: Request, x_signature: str = Header(default='')) -> dict[str,str]:
    raw = await request.body()
    if len(raw)>16384:
        raise HTTPException(413,'Callback quá lớn.')
    check_signature(raw,x_signature)
    try:
        event = RefundCallback.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422,'Callback không đúng hợp đồng.') from exc
    return process_refund(event,raw)


@router.post('/operator/refunds/{refund_id}/demo-settle')
def demo_refund(refund_id: str, operator: Operator) -> dict[str,str]:
    if os.environ.get('MAY_DEMO_MODE')!='1':
        raise HTTPException(404,'Mô phỏng chưa được bật.')
    with connection() as db:
        row = db.execute('SELECT * FROM refunds WHERE id=?', (refund_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy khoản hoàn.')
    event = RefundCallback(event_id=new_id(),refund_id=refund_id,amount=row['amount'],currency='VND',outcome='succeeded')
    raw = event.model_dump_json().encode()
    check_signature(raw,signature(raw))
    return process_refund(event,raw)
