"""Cookie-based identity and explicit server-side role boundaries."""

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response

from .db import connection, new_id


def customer_id(request: Request, response: Response) -> str:
    digest = hashlib.sha256(request.cookies.get('may_session','').encode()).hexdigest()
    with connection() as db:
        row = db.execute("SELECT customer_id FROM sessions WHERE token_hash=? AND created_at>datetime('now','-30 days')", (digest,)).fetchone()
        if row:
            return str(row['customer_id'])
        customer = new_id()
        db.execute('INSERT INTO customers(id) VALUES (?)', (customer,))
        token = secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions (token_hash,customer_id) VALUES (?,?)', (hashlib.sha256(token.encode()).hexdigest(),customer))
    response.set_cookie('may_session',token,httponly=True,samesite='strict',max_age=30*86400,secure=request.url.scheme == 'https')
    return customer


Customer = Annotated[str, Depends(customer_id)]


def registered_customer_id(customer: Customer) -> str:
    with connection() as db:
        account = db.execute('SELECT email FROM customers WHERE id=?', (customer,)).fetchone()
    if not account or not account['email']:
        raise HTTPException(401,'Bạn cần đăng nhập để mua sắm cùng mây.')
    return customer


RegisteredCustomer = Annotated[str, Depends(registered_customer_id)]


def require_roles(customer: str, roles: tuple[str, ...]) -> None:
    with connection() as db:
        row = db.execute('SELECT role,email FROM customers WHERE id=?', (customer,)).fetchone()
    if not row or not row['email'] or row['role'] not in roles:
        raise HTTPException(403,'Tài khoản không có quyền thực hiện thao tác này.')


def merchant(customer: RegisteredCustomer) -> str:
    require_roles(customer,('merchant',))
    return customer


def support(customer: RegisteredCustomer) -> str:
    require_roles(customer,('support',))
    return customer


def operator(customer: RegisteredCustomer) -> str:
    require_roles(customer,('operator',))
    return customer


Merchant = Annotated[str, Depends(merchant)]
Support = Annotated[str, Depends(support)]
Operator = Annotated[str, Depends(operator)]
