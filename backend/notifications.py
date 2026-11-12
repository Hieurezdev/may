"""Transactional outbox delivery with leases and bounded transient retries."""

import hashlib
import hmac
import secrets

import httpx
from fastapi import APIRouter, HTTPException

from .auth import Operator
from .config import setting
from .db import connection

router = APIRouter(prefix='/api/operator',tags=['Operations'])


@router.post('/outbox/dispatch')
async def deliver_outbox(operator: Operator) -> dict[str,int]:
    endpoint = setting('NOTIFICATION_URL')
    key = setting('NOTIFICATION_SECRET')
    if not endpoint or not key:
        raise HTTPException(503,'Chưa cấu hình nhà cung cấp thông báo. Sự kiện vẫn được giữ trong outbox.')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        rows = db.execute("""SELECT * FROM outbox_events WHERE attempts<5 AND
            ((status='pending' AND next_attempt_at<=CURRENT_TIMESTAMP) OR (status='sending' AND lease_until<=CURRENT_TIMESTAMP))
            ORDER BY rowid LIMIT 20""").fetchall()
        for row in rows:
            db.execute("UPDATE outbox_events SET status='sending',attempts=attempts+1,lease_until=datetime('now','+5 minutes') WHERE id=?", (row['id'],))
    counts = {'sent':0,'retrying':0,'failed':0}
    async with httpx.AsyncClient(timeout=httpx.Timeout(5,connect=2)) as client:
        for row in rows:
            body = row['payload'].encode()
            transient = False
            try:
                response = await client.post(endpoint,content=body,headers={'Content-Type':'application/json','Idempotency-Key':row['id'],'X-Event-Type':row['kind'],'X-Signature':hmac.new(key.encode(),body,hashlib.sha256).hexdigest()})
                success = response.is_success
                transient = response.status_code in {408,429} or response.status_code>=500
            except (httpx.TimeoutException,httpx.NetworkError):
                success = False
                transient = True
            attempts = row['attempts']+1
            state = 'sent' if success else 'pending' if transient and attempts<5 else 'failed'
            counts['sent' if success else 'retrying' if state=='pending' else 'failed'] += 1
            delay = min(3600,2**attempts*10)+secrets.randbelow(6)
            with connection() as db:
                db.execute("UPDATE outbox_events SET status=?,next_attempt_at=datetime('now',?),lease_until=NULL WHERE id=?", (state,f'+{delay} seconds',row['id']))
    return counts
