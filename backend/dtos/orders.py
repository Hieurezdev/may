"""Validated orders request and response contracts."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator
from .cart import Quote, QuoteInput
from .returns import ReturnView


class OrderInput(QuoteInput):
    expected_total: int = Field(ge=0, strict=True)
    recipient_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(pattern=r"^(?:0[35789]\d{8}|\+84[35789]\d{8})$")
    address: str = Field(min_length=10, max_length=500)
    payment_method: Literal["cod", "online-demo"]
    idempotency_key: str = Field(min_length=16, max_length=100)

    @field_validator("recipient_name", "address", mode="before")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()


class OrderLine(BaseModel):
    id: str
    variant_id: str
    name: str
    color: str
    size: str
    image: str
    quantity: int
    unit_price: int


class OrderResult(Quote):
    id: str
    recipient_name: str
    phone: str
    address: str
    status: str
    payment_method: str
    payment_status: str
    created_at: str
    items: list[OrderLine]
    shipment: dict[str, str] | None = None
    returns: list[ReturnView] = Field(default_factory=list)


class ShipmentInput(BaseModel):
    provider: str = Field(min_length=2,max_length=100)
    tracking_code: str = Field(min_length=3,max_length=100)


class StatusInput(BaseModel):
    status: Literal["processing", "shipped", "delivered", "cancelled"]
