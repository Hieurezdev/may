"""Validated cart request and response contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CartInput(BaseModel):
    variant_id: str = Field(max_length=100)
    quantity: int = Field(ge=1, le=99, strict=True)


class CartLine(BaseModel):
    variant_id: str
    product_id: str
    name: str
    image: str
    color: str
    size: str
    price: int
    stock: int
    quantity: int


class Voucher(BaseModel):
    code: str
    title: str
    kind: str
    value: int
    minimum: int
    maximum: int
    expires_at: str


class QuoteInput(BaseModel):
    voucher: str = Field(default="", max_length=40)


class Quote(BaseModel):
    subtotal: int
    discount: int
    shipping: int
    total: int
    voucher: str | None
