"""Chat HTTP endpoints."""

import json

from fastapi import APIRouter, HTTPException, Response

from ..assistant import AssistantContext, AssistantOrder, AssistantProduct, AssistantVoucher, ChatTurn, complete
from ..auth import Customer
from ..db import connection
from ..dtos.experience import ChatInput, ChatReply
from ..speech import synthesize

router = APIRouter()


@router.get("/api/chat")
def chat_history(customer: Customer) -> list[dict[str, str | int]]:
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT id,sender,content,created_at FROM (SELECT * FROM chat_messages WHERE customer_id=? ORDER BY id DESC LIMIT 50) ORDER BY id", (customer,))]


@router.delete("/api/chat")
def clear_chat(customer: Customer) -> dict[str, bool]:
    with connection() as db:
        db.execute("DELETE FROM chat_messages WHERE customer_id=?", (customer,))
        db.execute("UPDATE customers SET chat_revision=chat_revision+1 WHERE id=?", (customer,))
    return {"ok": True}


@router.post("/api/chat", response_model=ChatReply)
async def chat(data: ChatInput, customer: Customer) -> ChatReply:
    with connection() as db:
        revision = db.execute("SELECT chat_revision FROM customers WHERE id=?", (customer,)).fetchone()["chat_revision"]
        history = [ChatTurn(role=row["sender"], content=row["content"]) for row in db.execute(
            "SELECT sender,content FROM (SELECT id,sender,content FROM chat_messages WHERE customer_id=? ORDER BY id DESC LIMIT 12) ORDER BY id", (customer,),
        )]
        catalog: list[AssistantProduct] = []
        for row in db.execute("SELECT id,name,brand,category,price,specs FROM products WHERE active=1"):
            variants = db.execute("SELECT v.color,v.size,CASE WHEN v.sellable=1 THEN i.on_hand-i.reserved ELSE 0 END AS stock FROM variants v JOIN inventory_positions i ON i.variant_id=v.id WHERE v.product_id=?", (row["id"],)).fetchall()
            values = dict(row)
            values["specs"] = json.loads(values["specs"])
            catalog.append(AssistantProduct(
                **values, available=any(v["stock"] > 0 for v in variants),
                stock=sum(v["stock"] for v in variants),
                colors=list(dict.fromkeys(v["color"] for v in variants if v["stock"] > 0)),
                sizes=list(dict.fromkeys(v["size"] for v in variants if v["stock"] > 0)),
            ))
        vouchers = [AssistantVoucher.model_validate(dict(row)) for row in db.execute(
            "SELECT code,kind,value,minimum,maximum FROM vouchers WHERE active=1 AND used_count<usage_limit AND expires_at>=date('now')"
        )]
        orders = [AssistantOrder.model_validate(dict(row)) for row in db.execute(
            "SELECT id,status,payment_status,total FROM orders WHERE customer_id=? ORDER BY rowid DESC LIMIT 5", (customer,),
        )]
    answer = await complete(data.content, history, AssistantContext(products=catalog, vouchers=vouchers, orders=orders))
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        current_revision = db.execute("SELECT chat_revision FROM customers WHERE id=?", (customer,)).fetchone()["chat_revision"]
        if revision != current_revision:
            raise HTTPException(409, "Hội thoại đã thay đổi. Hãy gửi lại câu hỏi.")
        db.execute("INSERT INTO chat_messages (customer_id,sender,content) VALUES (?,'user',?)", (customer, data.content))
        message_id = db.execute("INSERT INTO chat_messages (customer_id,sender,content) VALUES (?,'assistant',?)", (customer, answer.content)).lastrowid
        db.execute("UPDATE customers SET chat_revision=chat_revision+1 WHERE id=?", (customer,))
    return ChatReply(content=answer.content, product_ids=answer.product_ids, message_id=message_id)


@router.post("/api/chat/{message_id}/speech")
async def chat_speech(message_id: int, customer: Customer) -> Response:
    with connection() as db:
        row = db.execute("SELECT content FROM chat_messages WHERE id=? AND customer_id=? AND sender='assistant'", (message_id, customer)).fetchone()
        if row is None:
            raise HTTPException(404, "Không tìm thấy câu trả lời thuộc hội thoại của bạn.")
    audio = await synthesize(row["content"])
    return Response(audio, media_type="audio/mpeg")
