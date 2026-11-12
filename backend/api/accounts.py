"""Accounts HTTP endpoints."""

import hashlib
import hmac
import secrets
import sqlite3

from fastapi import APIRouter, HTTPException, Request, Response

from ..auth import Customer
from ..db import connection, password_hash
from ..dtos.accounts import Credentials

router = APIRouter()


@router.get("/api/me")
def me(customer: Customer) -> dict[str, str | bool | None]:
    with connection() as db:
        row = db.execute("SELECT id,full_name,email,role FROM customers WHERE id=?", (customer,)).fetchone()
        return {**dict(row), "registered": row["email"] is not None}


@router.post("/api/auth/register", status_code=201)
def register(data: Credentials, customer: Customer, request: Request, response: Response) -> dict[str, bool]:
    salt = secrets.token_hex(16)
    with connection() as db:
        if db.execute("SELECT email FROM customers WHERE id=?", (customer,)).fetchone()["email"]:
            raise HTTPException(409, "Bạn đã đăng nhập. Hãy đăng xuất trước khi đăng ký tài khoản khác.")
        try:
            db.execute("UPDATE customers SET email=?,full_name=?,salt=?,password_hash=? WHERE id=?", (data.email, data.full_name, salt, password_hash(data.password, salt), customer))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Email đã được sử dụng.") from exc
        db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(request.cookies.get("may_session", "").encode()).hexdigest(),))
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions(token_hash,customer_id) VALUES (?,?)", (hashlib.sha256(token.encode()).hexdigest(),customer))
    response.set_cookie("may_session",token,httponly=True,samesite="strict",max_age=30*86400,secure=request.url.scheme=="https")
    return {"ok": True}


@router.post("/api/auth/login")
def login(data: Credentials, customer: Customer, request: Request, response: Response) -> dict[str, bool]:
    with connection() as db:
        row = db.execute("SELECT * FROM customers WHERE email=?", (data.email,)).fetchone()
        if row is None or not hmac.compare_digest(password_hash(data.password, row["salt"]), row["password_hash"]):
            raise HTTPException(401, "Email hoặc mật khẩu không đúng.")
        # Rotate the session so knowing an anonymous token cannot grant account access.
        old_token = hashlib.sha256(request.cookies.get("may_session", "").encode()).hexdigest()
        db.execute("DELETE FROM sessions WHERE token_hash=?", (old_token,))
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions (token_hash,customer_id) VALUES (?,?)", (hashlib.sha256(token.encode()).hexdigest(), row["id"]))
    response.set_cookie("may_session", token, httponly=True, samesite="strict", max_age=30 * 86400, secure=request.url.scheme == "https")
    return {"ok": True}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    with connection() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(request.cookies.get("may_session", "").encode()).hexdigest(),))
    response.delete_cookie("may_session")
    return {"ok": True}
