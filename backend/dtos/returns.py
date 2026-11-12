"""Validated returns request and response contracts."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class ReturnLineInput(BaseModel):
    order_line_id: str
    quantity: int = Field(ge=1,le=99,strict=True)


class ReturnInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    reason: str = Field(min_length=5,max_length=1000)
    evidence: str = Field(default='',max_length=2000)
    lines: list[ReturnLineInput] = Field(min_length=1,max_length=100)


class ReviewInput(BaseModel):
    decision: Literal['approve','reject']
    reason: str = Field(min_length=5,max_length=1000)


class InspectionInput(BaseModel):
    accepted: bool
    restock: bool
    reason: str = Field(min_length=5,max_length=1000)


class ReasonInput(BaseModel):
    reason: str = Field(min_length=5,max_length=1000)


class ReturnLineView(BaseModel):
    order_line_id: str
    quantity: int


class ReturnView(BaseModel):
    id: str
    order_id: str
    reason: str
    status: str
    review_reason: str | None
    evidence: str
    lines: list[ReturnLineView]
    refund_status: str | None = None
    refund_amount: int | None = None
