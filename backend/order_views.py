"""Materialize immutable purchase snapshots and their fulfillment/after-sales state."""

import sqlite3
from fastapi import HTTPException
from .dtos import OrderResult, ReturnView
from .models import Order, OrderLine, OrderStatus


def owned_order(db: sqlite3.Connection, order_id: str, customer: str) -> sqlite3.Row:
    row = db.execute('SELECT * FROM orders WHERE id=? AND customer_id=?', (order_id,customer)).fetchone()
    if row is None:
        raise HTTPException(404,'Không tìm thấy đơn hàng.')
    return row


def return_view(db: sqlite3.Connection, row: sqlite3.Row) -> ReturnView:
    values = dict(row)
    values['lines'] = [dict(line) for line in db.execute('SELECT order_line_id,quantity FROM return_lines WHERE request_id=?', (row['id'],))]
    refund = db.execute('SELECT status,amount FROM refunds WHERE request_id=?', (row['id'],)).fetchone()
    if refund:
        values['refund_status'] = refund['status']
        values['refund_amount'] = refund['amount']
    return ReturnView.model_validate(values)


def order_result(db: sqlite3.Connection, row: sqlite3.Row) -> OrderResult:
    values = dict(row)
    values['items'] = [dict(item) for item in db.execute('SELECT * FROM order_items WHERE order_id=? ORDER BY rowid', (row['id'],))]
    shipment = db.execute('SELECT id,provider,tracking_code,status FROM shipments WHERE order_id=?', (row['id'],)).fetchone()
    values['shipment'] = dict(shipment) if shipment else None
    values['returns'] = [return_view(db,r) for r in db.execute('SELECT * FROM return_requests WHERE order_id=? ORDER BY rowid', (row['id'],)).fetchall()]
    return OrderResult.model_validate(values)


def domain_order(db: sqlite3.Connection, row: sqlite3.Row) -> Order:
    lines = tuple(OrderLine(id=r['id'],variant_id=r['variant_id'],quantity=r['quantity'],unit_price=r['unit_price'],discount_minor=r['discount_minor'])
                  for r in db.execute('SELECT * FROM order_items WHERE order_id=?', (row['id'],)))
    return Order(id=row['id'],customer_id=row['customer_id'],status=OrderStatus(row['status']),total=row['total'],lines=lines)
