"""Delivered-line eligibility, reviewed returns, inspection and bounded refunds."""

from fastapi import APIRouter, HTTPException
from .auth import Customer, Merchant, Support
from .db import connection, new_id
from .dtos import InspectionInput, RefundInput, ReturnInput, ReturnView, ReviewInput
from .inventory import audit, notify
from .order_views import owned_order, return_view
from .payments import create_refund

router = APIRouter(prefix='/api',tags=['Returns'])


@router.post('/orders/{order_id}/returns',status_code=201,response_model=ReturnView)
def request_return(order_id: str, data: ReturnInput, customer: Customer) -> ReturnView:
    if len({line.order_line_id for line in data.lines})!=len(data.lines):
        raise HTTPException(422,'Mỗi dòng hàng chỉ xuất hiện một lần trong yêu cầu.')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        order = owned_order(db,order_id,customer)
        eligible = db.execute("SELECT 1 FROM orders WHERE id=? AND status='delivered' AND delivered_at>=datetime('now','-7 days')", (order_id,)).fetchone()
        if not eligible:
            raise HTTPException(409,'Chỉ nhận yêu cầu trong 7 ngày sau khi giao thành công.')
        identity = new_id()
        db.execute("INSERT INTO return_requests(id,order_id,reason,evidence,status) VALUES (?,?,?,?,'requested')", (identity,order['id'],data.reason,data.evidence))
        for line in data.lines:
            purchased = db.execute('SELECT quantity FROM order_items WHERE id=? AND order_id=?', (line.order_line_id,order_id)).fetchone()
            requested = db.execute("SELECT COALESCE(SUM(l.quantity),0) AS n FROM return_lines l JOIN return_requests r ON r.id=l.request_id WHERE l.order_line_id=? AND r.status!='rejected'", (line.order_line_id,)).fetchone()['n']
            if not purchased or requested+line.quantity>purchased['quantity']:
                raise HTTPException(409,'Số lượng trả vượt phần đã giao chưa được yêu cầu trả.')
            db.execute('INSERT INTO return_lines(id,request_id,order_id,order_line_id,quantity) VALUES (?,?,?,?,?)', (new_id(),identity,order_id,line.order_line_id,line.quantity))
        audit(db,customer,'return.requested',identity,data.reason)
        notify(db,order_id,'return.requested')
        return return_view(db,db.execute('SELECT * FROM return_requests WHERE id=?', (identity,)).fetchone())


@router.get('/support/returns',response_model=list[ReturnView])
def support_returns(support: Support) -> list[ReturnView]:
    with connection() as db:
        return [return_view(db,r) for r in db.execute('SELECT * FROM return_requests ORDER BY rowid DESC LIMIT 100').fetchall()]


@router.patch('/support/returns/{request_id}',response_model=ReturnView)
def review(request_id: str, data: ReviewInput, support: Support) -> ReturnView:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM return_requests WHERE id=?', (request_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy yêu cầu.')
        if row['status']!='requested':
            raise HTTPException(409,'Yêu cầu đã được xét duyệt.')
        db.execute('UPDATE return_requests SET status=?,review_reason=? WHERE id=?', ('approved' if data.decision=='approve' else 'rejected',data.reason,request_id))
        audit(db,support,'return.'+data.decision,request_id,data.reason)
        notify(db,row['order_id'],'return.reviewed')
        return return_view(db,db.execute('SELECT * FROM return_requests WHERE id=?', (request_id,)).fetchone())


@router.get('/admin/returns',response_model=list[ReturnView])
def merchant_returns(merchant: Merchant) -> list[ReturnView]:
    with connection() as db:
        return [return_view(db,r) for r in db.execute("SELECT * FROM return_requests WHERE status IN ('approved','inspected','refund_pending','completed') ORDER BY rowid DESC LIMIT 100").fetchall()]


@router.post('/admin/returns/{request_id}/inspect',response_model=ReturnView)
def inspect(request_id: str, data: InspectionInput, merchant: Merchant) -> ReturnView:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM return_requests WHERE id=?', (request_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy yêu cầu.')
        if row['status']!='approved':
            raise HTTPException(409,'Chỉ kiểm tra hàng trả đã được phê duyệt, một lần.')
        if data.restock and not data.accepted:
            raise HTTPException(422,'Hàng không đạt kiểm tra không thể nhập kho bán lại.')
        if data.accepted and data.restock:
            for line in db.execute('''SELECT rl.*,l.variant_id FROM return_lines rl JOIN order_items l ON l.id=rl.order_line_id WHERE rl.request_id=?''', (request_id,)).fetchall():
                db.execute('UPDATE inventory_positions SET on_hand=on_hand+? WHERE variant_id=?', (line['quantity'],line['variant_id']))
                db.execute('UPDATE return_lines SET restocked=1 WHERE id=?', (line['id'],))
        db.execute('UPDATE return_requests SET status=?,review_reason=? WHERE id=?', ('inspected' if data.accepted else 'rejected',data.reason,request_id))
        audit(db,merchant,'return.inspected',request_id,data.reason)
        return return_view(db,db.execute('SELECT * FROM return_requests WHERE id=?', (request_id,)).fetchone())


@router.post('/support/returns/{request_id}/refund',response_model=ReturnView)
def refund(request_id: str, data: RefundInput, support: Support) -> ReturnView:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM return_requests WHERE id=?', (request_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy yêu cầu.')
        previous = db.execute('SELECT * FROM refunds WHERE idempotency_key=?', (data.idempotency_key,)).fetchone()
        if previous:
            if previous['request_id']!=request_id:
                raise HTTPException(409,'Khóa hoàn tiền đã được dùng cho yêu cầu khác.')
            return return_view(db,row)
        if row['status']!='inspected':
            raise HTTPException(409,'Chỉ hoàn tiền sau khi hàng trả đạt kiểm tra.')
        # Cumulative floor differences distribute line discount rounding across partial returns.
        amount = 0
        for line in db.execute('''SELECT rl.order_line_id,rl.quantity AS returned,l.quantity AS bought,l.unit_price,l.discount_minor FROM return_lines rl JOIN order_items l ON l.id=rl.order_line_id WHERE rl.request_id=?''', (request_id,)).fetchall():
            prior = db.execute('''SELECT COALESCE(SUM(rl.quantity),0) AS n FROM return_lines rl JOIN return_requests r ON r.id=rl.request_id
                JOIN refunds f ON f.request_id=r.id WHERE rl.order_line_id=? AND r.id!=? AND f.status IN ('pending','succeeded')''', (line['order_line_id'],request_id)).fetchone()['n']
            net = line['bought']*line['unit_price']-line['discount_minor']
            amount += net*(prior+line['returned'])//line['bought']-net*prior//line['bought']
        order = db.execute('SELECT * FROM orders WHERE id=?', (row['order_id'],)).fetchone()
        create_refund(db,order,request_id,amount,data.idempotency_key,'Approved and inspected return')
        db.execute("UPDATE return_requests SET status='refund_pending' WHERE id=?", (request_id,))
        audit(db,support,'refund.authorized',request_id,'Inspected line value, captured ceiling checked')
        return return_view(db,db.execute('SELECT * FROM return_requests WHERE id=?', (request_id,)).fetchone())
