"""Cart, quotes, stock reservation and durable idempotent checkout."""

import hashlib
import json
import os
import sqlite3
from datetime import date

from fastapi import APIRouter, Header, HTTPException

from .auth import Customer, RegisteredCustomer
from .db import connection, new_id
from .dtos import AddressInput, CartInput, CartLine, OrderInput, OrderResult, Quote, QuoteInput, ReasonInput, Voucher
from .inventory import audit, expire, notify, release
from .order_views import domain_order, order_result, owned_order

router = APIRouter(prefix='/api',tags=['Shopping'])


def cart_id(db: sqlite3.Connection, customer: str) -> str:
    row = db.execute('SELECT id FROM carts WHERE customer_id=?', (customer,)).fetchone()
    if row:
        return str(row['id'])
    identity = new_id()
    db.execute('INSERT INTO carts(id,customer_id) VALUES (?,?)', (identity,customer))
    return identity


def cart_lines(db: sqlite3.Connection, customer: str) -> list[CartLine]:
    rows = db.execute('''SELECT c.variant_id,v.product_id,p.name,p.image,v.color,v.size,
        COALESCE((SELECT pr.price_minor FROM price_rules pr WHERE pr.variant_id=v.id AND pr.starts_at<=CURRENT_TIMESTAMP AND pr.ends_at>CURRENT_TIMESTAMP ORDER BY pr.starts_at DESC LIMIT 1),v.price) AS price,
        CASE WHEN p.active=1 AND v.sellable=1 THEN i.on_hand-i.reserved ELSE 0 END AS stock,c.quantity
        FROM cart_items c JOIN carts ca ON ca.id=c.cart_id JOIN variants v ON v.id=c.variant_id
        JOIN products p ON p.id=v.product_id JOIN inventory_positions i ON i.variant_id=v.id
        WHERE ca.customer_id=? ORDER BY v.id''', (customer,))
    return [CartLine.model_validate(dict(row)) for row in rows]


@router.get('/cart',response_model=list[CartLine])
def get_cart(customer: Customer) -> list[CartLine]:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        return cart_lines(db,customer)


@router.post('/cart',response_model=list[CartLine])
def add_cart(data: CartInput, customer: Customer) -> list[CartLine]:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        cart = cart_id(db,customer)
        variant = db.execute('''SELECT i.on_hand-i.reserved AS available FROM variants v JOIN products p ON p.id=v.product_id
            JOIN inventory_positions i ON i.variant_id=v.id WHERE v.id=? AND p.active=1 AND v.sellable=1''', (data.variant_id,)).fetchone()
        if variant is None:
            raise HTTPException(404,'Biến thể không còn khả dụng.')
        existing = db.execute('SELECT quantity FROM cart_items WHERE cart_id=? AND variant_id=?', (cart,data.variant_id)).fetchone()
        quantity = data.quantity + (existing['quantity'] if existing else 0)
        if quantity > min(variant['available'],99):
            raise HTTPException(409,'Số lượng vượt quá tồn kho khả dụng.')
        db.execute('''INSERT INTO cart_items(id,cart_id,variant_id,quantity) VALUES (?,?,?,?)
            ON CONFLICT(cart_id,variant_id) DO UPDATE SET quantity=excluded.quantity''', (new_id(),cart,data.variant_id,quantity))
        return cart_lines(db,customer)


@router.put('/cart/{variant_id}',response_model=list[CartLine])
def update_cart(variant_id: str, data: CartInput, customer: Customer) -> list[CartLine]:
    if variant_id != data.variant_id:
        raise HTTPException(422,'Biến thể không khớp.')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        cart = cart_id(db,customer)
        available = db.execute('''SELECT i.on_hand-i.reserved AS n FROM inventory_positions i JOIN variants v ON v.id=i.variant_id
            JOIN products p ON p.id=v.product_id WHERE v.id=? AND p.active=1 AND v.sellable=1''', (variant_id,)).fetchone()
        if not available or data.quantity > available['n']:
            raise HTTPException(409,'Số lượng vượt quá tồn kho khả dụng.')
        if not db.execute('UPDATE cart_items SET quantity=? WHERE cart_id=? AND variant_id=?', (data.quantity,cart,variant_id)).rowcount:
            raise HTTPException(404,'Sản phẩm không có trong giỏ.')
        return cart_lines(db,customer)


@router.delete('/cart/{variant_id}',response_model=list[CartLine])
def delete_cart(variant_id: str, customer: Customer) -> list[CartLine]:
    with connection() as db:
        db.execute('DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE customer_id=?) AND variant_id=?', (customer,variant_id))
        return cart_lines(db,customer)


@router.get('/vouchers',response_model=list[Voucher])
def vouchers() -> list[Voucher]:
    with connection() as db:
        return [Voucher.model_validate(dict(r)) for r in db.execute("SELECT * FROM vouchers WHERE active=1 AND used_count<usage_limit AND expires_at>=date('now')")]


def calculate_quote(db: sqlite3.Connection, customer: str, code: str) -> Quote:
    lines = cart_lines(db,customer)
    if not lines:
        raise HTTPException(409,'Giỏ hàng đang trống.')
    if any(line.quantity > line.stock for line in lines):
        raise HTTPException(409,'Sản phẩm đã thay đổi tồn kho hoặc ngừng bán. Hãy cập nhật giỏ.')
    subtotal = sum(line.price * line.quantity for line in lines)
    shipping = 0 if subtotal >= 499000 else 30000
    discount = 0
    code = code.strip().upper()
    if code:
        v = db.execute('SELECT * FROM vouchers WHERE code=?', (code,)).fetchone()
        if not v or not v['active'] or v['used_count']>=v['usage_limit'] or v['expires_at']<date.today().isoformat():
            raise HTTPException(422,'Voucher không hợp lệ hoặc hết hạn.')
        if subtotal < v['minimum']:
            raise HTTPException(422,f"Đơn tối thiểu {v['minimum']:,}đ để dùng mã này.")
        if v['kind']=='shipping':
            shipping = max(0,shipping-v['value'])
        else:
            discount = min(v['maximum'],subtotal,subtotal*v['value']//100 if v['kind']=='percent' else v['value'])
    return Quote(subtotal=subtotal,discount=discount,shipping=shipping,total=subtotal-discount+shipping,voucher=code or None)


@router.post('/checkout/quote',response_model=Quote)
def quote(data: QuoteInput, customer: Customer) -> Quote:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        return calculate_quote(db,customer,data.voucher)


@router.post('/orders',status_code=201,response_model=OrderResult)
def checkout(data: OrderInput, customer: Customer) -> OrderResult:
    if data.payment_method=='online-demo' and os.environ.get('MAY_DEMO_MODE')!='1':
        raise HTTPException(503,'Thanh toán mô phỏng chưa được bật; hiện tại bạn có thể chọn COD.')
    digest = hashlib.sha256(data.model_dump_json().encode()).hexdigest()
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        existing = db.execute('SELECT * FROM orders WHERE idempotency_key=?', (data.idempotency_key,)).fetchone()
        if existing:
            if existing['customer_id'] != customer or existing['request_hash'] != digest:
                raise HTTPException(409,'Khóa đặt hàng đã được dùng cho yêu cầu khác.')
            return order_result(db,existing)
        totals = calculate_quote(db,customer,data.voucher)
        if data.expected_total != totals.total:
            raise HTTPException(409, {
                'code': 'quote_changed',
                'message': 'Giá đã thay đổi. Hãy xem và xác nhận lại tổng tiền.',
                'quote': totals.model_dump(),
            })
        lines = cart_lines(db,customer)
        identity = new_id()
        status = 'confirmed' if data.payment_method=='cod' else 'pending_payment'
        db.execute('''INSERT INTO orders(id,customer_id,recipient_name,phone,address,subtotal,discount,shipping,total,voucher,status,payment_method,idempotency_key,request_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (identity,customer,data.recipient_name,data.phone,data.address,totals.subtotal,totals.discount,totals.shipping,totals.total,totals.voucher,status,data.payment_method,data.idempotency_key,digest))
        allocated = 0
        for index,line in enumerate(lines):
            line_id = new_id()
            product = db.execute('SELECT p.category,v.sku FROM variants v JOIN products p ON p.id=v.product_id WHERE v.id=?', (line.variant_id,)).fetchone()
            # Allocate rounding residue to the last line so snapshots sum exactly.
            discount = totals.discount-allocated if index==len(lines)-1 else totals.discount*line.price*line.quantity//totals.subtotal
            allocated += discount
            db.execute('''INSERT INTO order_items(id,order_id,variant_id,sku_snapshot,name,color,size,image,category_snapshot,quantity,unit_price,discount_minor)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (line_id,identity,line.variant_id,product['sku'],line.name,line.color,line.size,line.image,product['category'],line.quantity,line.price,discount))
            position = db.execute('SELECT id FROM inventory_positions WHERE variant_id=?', (line.variant_id,)).fetchone()
            changed = db.execute('UPDATE inventory_positions SET reserved=reserved+? WHERE id=? AND on_hand-reserved>=?', (line.quantity,position['id'],line.quantity)).rowcount
            if not changed:
                raise HTTPException(409,'Sản phẩm vừa hết hàng. Chưa tạo đơn hoặc thu tiền.')
            state = 'committed' if data.payment_method=='cod' else 'held'
            db.execute("INSERT INTO reservations(id,position_id,order_line_id,quantity,expires_at,state) VALUES (?,?,?,?,datetime('now','+15 minutes'),?)", (new_id(),position['id'],line_id,line.quantity,state))
        if totals.voucher:
            changed = db.execute('UPDATE vouchers SET used_count=used_count+1 WHERE code=? AND used_count<usage_limit', (totals.voucher,)).rowcount
            if not changed:
                raise HTTPException(409,'Voucher vừa hết lượt dùng.')
        attempt_id = new_id()
        db.execute('INSERT INTO payment_attempts(id,order_id,provider,provider_reference,amount,currency,status) VALUES (?,?,?,?,?,?,?)', (attempt_id,identity,'demo' if data.payment_method=='online-demo' else 'cod','intent-'+attempt_id,totals.total,'VND','pending'))
        db.execute('DELETE FROM cart_items WHERE cart_id=(SELECT id FROM carts WHERE customer_id=?)', (customer,))
        audit(db,customer,'checkout.created',identity,'Server quote and stock reserved atomically')
        notify(db,identity,'order.created')
        return order_result(db,owned_order(db,identity,customer))


@router.get('/orders',response_model=list[OrderResult])
def orders(customer: Customer) -> list[OrderResult]:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        return [order_result(db,r) for r in db.execute('SELECT * FROM orders WHERE customer_id=? ORDER BY rowid DESC', (customer,)).fetchall()]


@router.get('/orders/{order_id}',response_model=OrderResult)
def order_detail(order_id: str, customer: Customer) -> OrderResult:
    with connection() as db:
        return order_result(db,owned_order(db,order_id,customer))


@router.post('/orders/{order_id}/cancel',response_model=OrderResult)
def cancel(order_id: str, data: ReasonInput, customer: Customer) -> OrderResult:
    from .payments import create_refund
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = owned_order(db,order_id,customer)
        if row['status']=='cancelled':
            return order_result(db,row)
        if not domain_order(db,row).can_cancel:
            raise HTTPException(409,'Đơn đã giao cho vận chuyển hoặc đang đối soát, không thể hủy.')
        if row['payment_status']=='captured':
            create_refund(db,row,None,row['total'],'cancel-'+order_id,data.reason)
            db.execute("UPDATE orders SET payment_status='refund_pending' WHERE id=?", (order_id,))
        release(db,order_id)
        db.execute("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))
        audit(db,customer,'order.cancelled',order_id,data.reason)
        notify(db,order_id,'order.cancelled')
        return order_result(db,owned_order(db,order_id,customer))


@router.get('/addresses')
def addresses(customer: RegisteredCustomer) -> list[dict[str,str]]:
    with connection() as db:
        return [dict(r) for r in db.execute('SELECT * FROM addresses WHERE customer_id=?', (customer,))]


@router.post('/addresses',status_code=201)
def save_address(data: AddressInput, customer: RegisteredCustomer) -> dict[str,str]:
    identity = new_id()
    with connection() as db:
        db.execute('INSERT INTO addresses VALUES (?,?,?,?,?)', (identity,customer,data.recipient_name,data.phone,data.address))
    return {'id':identity,**data.model_dump()}


@router.delete('/addresses/{address_id}')
def delete_address(address_id: str, customer: RegisteredCustomer) -> dict[str,bool]:
    with connection() as db:
        if not db.execute('DELETE FROM addresses WHERE id=? AND customer_id=?', (address_id,customer)).rowcount:
            raise HTTPException(404,'Không tìm thấy địa chỉ.')
    return {'ok':True}


@router.post('/orders/{order_id}/guest-access')
def guest_access(order_id: str, customer: Customer) -> dict[str,str]:
    import secrets
    token = secrets.token_urlsafe(32)
    with connection() as db:
        owned_order(db,order_id,customer)
        db.execute("INSERT INTO guest_access_proofs VALUES (?,?,datetime('now','+24 hours'))", (hashlib.sha256(token.encode()).hexdigest(),order_id))
        expires = db.execute('SELECT expires_at FROM guest_access_proofs WHERE proof_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()['expires_at']
    return {'access_token':token,'expires_at':expires}


@router.get('/guest/orders/{order_id}',response_model=OrderResult)
def read_guest_order(order_id: str, authorization: str = Header(default='')) -> OrderResult:
    scheme,_,token = authorization.partition(' ')
    if scheme!='Bearer' or not token:
        raise HTTPException(401,'Cần mã truy cập đơn hàng dành cho khách.')
    with connection() as db:
        proof = db.execute('SELECT 1 FROM guest_access_proofs WHERE proof_hash=? AND order_id=? AND expires_at>CURRENT_TIMESTAMP', (hashlib.sha256(token.encode()).hexdigest(),order_id)).fetchone()
        if not proof:
            raise HTTPException(404,'Mã truy cập không hợp lệ hoặc đã hết hạn.')
        return order_result(db,db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())
