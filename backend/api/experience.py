"""Experience HTTP endpoints."""

import secrets

from fastapi import APIRouter, HTTPException

from ..auth import Customer
from ..db import connection
from ..dtos.experience import TryOnInput

router = APIRouter()


@router.post("/api/try-on", status_code=201)
def try_on(data: TryOnInput, customer: Customer) -> dict[str, str]:
    with connection() as db:
        product = db.execute("SELECT try_on FROM products WHERE id=? AND active=1", (data.product_id,)).fetchone()
        if product is None or not product["try_on"]:
            raise HTTPException(422, "Sản phẩm không hỗ trợ đeo thử.")
        session_id = secrets.token_hex(16)
        db.execute("INSERT INTO try_on_sessions (id,customer_id,product_id) VALUES (?,?,?)", (session_id, customer, data.product_id))
        return {"id": session_id, "mode": "local-overlay", "privacy": "Ảnh chỉ xử lý trong trình duyệt, không tải lên máy chủ."}


@router.delete("/api/try-on/{session_id}")
def delete_try_on(session_id: str, customer: Customer) -> dict[str, bool]:
    with connection() as db:
        if db.execute("UPDATE try_on_sessions SET status='deleted',deleted_at=CURRENT_TIMESTAMP WHERE id=? AND customer_id=?", (session_id, customer)).rowcount == 0:
            raise HTTPException(404, "Không tìm thấy phiên đeo thử.")
    return {"ok": True}
