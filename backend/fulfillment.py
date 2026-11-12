"""Merchant inventory and fulfillment, separated from support and operator powers."""

import sqlite3
import hashlib
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from .auth import Customer, Merchant, Operator, RegisteredCustomer, Support
from .db import ROOT, connection, new_id
from .dtos import OrderResult, Product, ProductCreate, ProductUpdate, ShipmentInput, StatusInput, StockInput
from .inventory import audit, expire, notify
from .order_views import order_result
from .models import InventoryPosition

router = APIRouter(prefix='/api',tags=['Operations'])


def catalog_product(db: sqlite3.Connection, row: sqlite3.Row) -> Product:
    values = dict(row)
    values['specs'] = json.loads(row['specs'])
    values['variants'] = [dict(v) for v in db.execute('''SELECT v.id,v.color,v.size,COALESCE((SELECT pr.price_minor FROM price_rules pr WHERE pr.variant_id=v.id AND pr.starts_at<=CURRENT_TIMESTAMP AND pr.ends_at>CURRENT_TIMESTAMP ORDER BY pr.starts_at DESC LIMIT 1),v.price) AS price,
        CASE WHEN v.sellable=1 THEN i.on_hand-i.reserved ELSE 0 END AS stock
        FROM variants v JOIN inventory_positions i ON i.variant_id=v.id WHERE v.product_id=? ORDER BY v.id''', (row['id'],))]
    if values['variants']:
        values['price'] = min(v['price'] for v in values['variants'])
    return Product.model_validate(values)


@router.get('/admin/products',response_model=list[Product])
def catalog(merchant: Merchant) -> list[Product]:
    with connection() as db:
        return [catalog_product(db,r) for r in db.execute('SELECT * FROM products')]


@router.patch('/admin/products/{product_id}',response_model=Product)
def update_product(product_id: str, data: ProductUpdate, merchant: Merchant) -> Product:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('UPDATE products SET name=?,price=?,active=?,source_version=source_version+1 WHERE id=?', (data.name,data.price,data.active,product_id)).rowcount:
            raise HTTPException(404,'Không tìm thấy sản phẩm.')
        db.execute('UPDATE variants SET price=? WHERE product_id=?', (data.price,product_id))
        audit(db,merchant,'catalog.updated',product_id,data.reason)
        return catalog_product(db,db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone())


@router.patch('/admin/variants/{variant_id}')
def stock(variant_id: str, data: StockInput, merchant: Merchant) -> dict[str,bool]:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        row = db.execute('SELECT * FROM inventory_positions WHERE variant_id=?', (variant_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy biến thể.')
        position = InventoryPosition(row['id'],row['on_hand'],row['reserved'])
        if data.stock<position.reserved:
            raise HTTPException(409,'Tồn thực tế không thể thấp hơn số lượng đang giữ chỗ.')
        db.execute('UPDATE inventory_positions SET on_hand=? WHERE id=?', (data.stock,row['id']))
        audit(db,merchant,'inventory.adjusted',variant_id,f"Physical on-hand {row['on_hand']} -> {data.stock}")
    return {'ok':True}


@router.get('/admin/inventory')
def inventory(merchant: Merchant) -> list[dict[str,str | int]]:
    with connection() as db:
        return [dict(r) for r in db.execute('SELECT *,on_hand-reserved AS available FROM inventory_positions')]


@router.get('/admin/orders',response_model=list[OrderResult])
def orders(merchant: Merchant) -> list[OrderResult]:
    with connection() as db:
        return [order_result(db,r) for r in db.execute('SELECT * FROM orders ORDER BY rowid DESC LIMIT 100').fetchall()]


def dispatch(db: sqlite3.Connection, row: sqlite3.Row, shipment: ShipmentInput, actor: str) -> None:
    if row['status']!='processing':
        raise HTTPException(409,'Chỉ xuất kho đơn đang chuẩn bị.')
    if row['payment_method']!='cod' and row['payment_status']!='captured':
        raise HTTPException(409,'Đơn trực tuyến chưa có thanh toán đã xác minh.')
    identity = new_id()
    if db.execute('SELECT 1 FROM shipments WHERE tracking_code=?', (shipment.tracking_code,)).fetchone():
        raise HTTPException(409,'Mã vận đơn đã tồn tại.')
    db.execute("INSERT INTO shipments(id,order_id,provider,tracking_code,status) VALUES (?,?,?,?,'shipped')", (identity,row['id'],shipment.provider,shipment.tracking_code))
    holds = db.execute('''SELECT r.*,l.id AS line_id FROM reservations r JOIN order_items l ON l.id=r.order_line_id WHERE l.order_id=?''', (row['id'],)).fetchall()
    if not holds or any(h['state']!='committed' for h in holds):
        raise HTTPException(409,'Đơn chưa có đầy đủ giữ chỗ đã cam kết.')
    for hold in holds:
        db.execute('UPDATE inventory_positions SET on_hand=on_hand-?,reserved=reserved-? WHERE id=?', (hold['quantity'],hold['quantity'],hold['position_id']))
        db.execute("UPDATE reservations SET state='dispatched' WHERE id=?", (hold['id'],))
        db.execute('INSERT INTO shipment_lines VALUES (?,?,?)', (identity,hold['line_id'],hold['quantity']))
    db.execute("UPDATE orders SET status='shipped' WHERE id=?", (row['id'],))
    audit(db,actor,'shipment.dispatched',row['id'],shipment.tracking_code)
    notify(db,row['id'],'order.shipped')


@router.post('/admin/orders/{order_id}/ship',response_model=OrderResult)
def ship(order_id: str, data: ShipmentInput, merchant: Merchant) -> OrderResult:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy đơn.')
        dispatch(db,row,data,merchant)
        return order_result(db,db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())


@router.patch('/admin/orders/{order_id}',response_model=OrderResult)
def change_status(order_id: str, data: StatusInput, merchant: Merchant) -> OrderResult:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Không tìm thấy đơn.')
        if data.status=='processing' and row['status'] in {'confirmed','paid'}:
            db.execute("UPDATE orders SET status='processing' WHERE id=?", (order_id,))
        elif data.status=='delivered' and row['status']=='shipped':
            if row['payment_method']=='cod':
                # A staff delivery confirmation explicitly includes cash collection in this local demo.
                db.execute("UPDATE payment_attempts SET status='captured' WHERE order_id=? AND provider='cod'", (order_id,))
                db.execute("UPDATE orders SET payment_status='captured' WHERE id=?", (order_id,))
            db.execute("UPDATE orders SET status='delivered',delivered_at=CURRENT_TIMESTAMP WHERE id=?", (order_id,))
            db.execute("UPDATE shipments SET status='delivered' WHERE order_id=?", (order_id,))
        else:
            raise HTTPException(409,'Chuyển trạng thái không hợp lệ; xuất kho cần mã vận đơn riêng.')
        audit(db,merchant,'fulfillment.'+data.status,order_id,'Staff recorded fulfillment outcome')
        notify(db,order_id,'order.'+data.status)
        return order_result(db,db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())


@router.get('/operator/audit')
def audit_trail(operator: Operator) -> list[dict[str,str | None]]:
    with connection() as db:
        return [dict(r) for r in db.execute('SELECT * FROM audit_events ORDER BY rowid DESC LIMIT 200')]


@router.get('/operator/outbox')
def outbox(operator: Operator) -> list[dict[str,str | int | None]]:
    with connection() as db:
        return [dict(r) for r in db.execute('SELECT * FROM outbox_events ORDER BY rowid DESC LIMIT 200')]


@router.get('/operator/refunds')
def refunds(operator: Operator) -> list[dict[str,str | int | None]]:
    with connection() as db:
        return [dict(r) for r in db.execute('SELECT * FROM refunds ORDER BY rowid DESC LIMIT 100')]


@router.post('/operator/reservations/expire')
def expire_reservations(operator: Operator) -> dict[str,int]:
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        return {'expired':expire(db)}


@router.post('/admin/products',status_code=201,response_model=Product)
def create_product(data: ProductCreate, merchant: Merchant) -> Product:
    image_path = ROOT / 'frontend' / 'assets' / data.image
    if not image_path.is_file():
        raise HTTPException(422,'Chọn ảnh có sẵn trong thư mục frontend/assets.')
    if len({(v.color,v.size) for v in data.variants})!=len(data.variants):
        raise HTTPException(422,'Màu và kích cỡ của mỗi biến thể phải khác nhau.')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM categories WHERE id=?', (data.category,)).fetchone():
            raise HTTPException(422,'Danh mục không tồn tại.')
        identity = new_id()
        price = min(v.price for v in data.variants)
        db.execute("""INSERT INTO products(id,name,brand,category,price,original_price,image,tag,specs,collected_at)
            VALUES (?,?,?,?,?,?,?,'',?,date('now'))""", (identity,data.name,data.brand,data.category,price,price,data.image,json.dumps(data.specs,ensure_ascii=False)))
        db.execute('INSERT INTO product_categories VALUES (?,?)', (identity,data.category))
        db.execute('INSERT INTO media_assets(id,product_id,uri,media_hash) VALUES (?,?,?,?)', (new_id(),identity,data.image,hashlib.sha256(image_path.read_bytes()).hexdigest()))
        for variant in data.variants:
            variant_id = new_id()
            db.execute('INSERT INTO variants(id,product_id,sku,color,size,price) VALUES (?,?,?,?,?,?)', (variant_id,identity,'SKU-'+variant_id,variant.color,variant.size,variant.price))
            db.execute('INSERT INTO inventory_positions(id,variant_id,location_id,on_hand) VALUES (?,?,?,?)', (new_id(),variant_id,'main',variant.on_hand))
        audit(db,merchant,'catalog.created',identity,data.reason)
        return catalog_product(db,db.execute('SELECT * FROM products WHERE id=?', (identity,)).fetchone())
