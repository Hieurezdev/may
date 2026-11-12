"""Validated catalog request and response contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict


class Variant(BaseModel):
    id: str
    color: str
    size: str
    price: int
    stock: int


class Product(BaseModel):
    active: bool = True
    id: str
    name: str
    brand: str
    category: str
    price: int
    original_price: int
    image: str
    rating: float | None
    sold: int | None
    try_on: str | None
    tag: str
    specs: dict[str, str]
    variants: list[Variant]
    source_url: str | None
    collected_at: str | None


class StockInput(BaseModel):
    stock: int = Field(ge=0, le=100000, strict=True)


class ProductUpdate(BaseModel):
    name: str = Field(min_length=2,max_length=200)
    price: int = Field(ge=0,le=100000000,strict=True)
    active: bool
    reason: str = Field(min_length=5,max_length=500)


class VariantCreate(BaseModel):
    color: str = Field(min_length=1,max_length=100)
    size: str = Field(min_length=1,max_length=30)
    price: int = Field(ge=0,le=100000000,strict=True)
    on_hand: int = Field(ge=0,le=100000,strict=True)


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2,max_length=200)
    brand: str = Field(min_length=1,max_length=100)
    category: str
    image: str = Field(pattern=r'^[a-zA-Z0-9_-]+\.(?:jpg|jpeg|png|webp)$')
    variants: list[VariantCreate] = Field(min_length=1,max_length=100)
    specs: dict[str,str] = Field(default_factory=dict,max_length=30)
    reason: str = Field(min_length=5,max_length=500)
