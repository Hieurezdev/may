"""Inventory transitions called only inside the caller's write transaction."""

import json
import sqlite3

from .db import new_id


def audit(db: sqlite3.Connection, actor: str | None, action: str, entity: str, reason: str) -> None:
    db.execute('INSERT INTO audit_events(id,actor_id,action,entity_id,reason) VALUES (?,?,?,?,?)', (new_id(),actor,action,entity,reason))


def notify(db: sqlite3.Connection, order_id: str, kind: str) -> None:
    # Notifications contain an order reference, never address or payment credentials.
    db.execute('INSERT INTO outbox_events(id,aggregate_id,kind,payload) VALUES (?,?,?,?)', (new_id(),order_id,kind,json.dumps({'order_id':order_id})))


def release(db: sqlite3.Connection, order_id: str) -> None:
    holds = db.execute('''SELECT r.* FROM reservations r JOIN order_items l ON l.id=r.order_line_id
        WHERE l.order_id=? AND r.state IN ('held','committed')''', (order_id,)).fetchall()
    for hold in holds:
        db.execute('UPDATE inventory_positions SET reserved=reserved-? WHERE id=?', (hold['quantity'],hold['position_id']))
        db.execute("UPDATE reservations SET state='released' WHERE id=?", (hold['id'],))
    row = db.execute('SELECT voucher,voucher_released FROM orders WHERE id=?', (order_id,)).fetchone()
    if row['voucher'] and not row['voucher_released']:
        db.execute('UPDATE vouchers SET used_count=used_count-1 WHERE code=?', (row['voucher'],))
        db.execute('UPDATE orders SET voucher_released=1 WHERE id=?', (order_id,))


def expire(db: sqlite3.Connection) -> int:
    rows = db.execute('''SELECT DISTINCT l.order_id FROM reservations r JOIN order_items l ON l.id=r.order_line_id
        JOIN orders o ON o.id=l.order_id WHERE r.state='held' AND r.expires_at<=CURRENT_TIMESTAMP
        AND o.payment_status='pending' AND o.payment_method='online-demo' ''').fetchall()
    for row in rows:
        release(db,row['order_id'])
        db.execute("UPDATE orders SET status='expired',payment_status='expired' WHERE id=?", (row['order_id'],))
        notify(db,row['order_id'],'order.expired')
    return len(rows)
