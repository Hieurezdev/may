"""Validated payments request and response contracts."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class PaymentInput(BaseModel):
    outcome: Literal["success", "failure", "cancel"]


class CallbackInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str = Field(min_length=1,max_length=100)
    attempt_id: str
    provider_reference: str
    amount: int = Field(ge=0,strict=True)
    currency: Literal['VND']
    outcome: Literal['captured','failed','cancelled']


class RefundInput(BaseModel):
    idempotency_key: str = Field(min_length=16,max_length=100)


class RefundCallback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str = Field(min_length=1,max_length=100)
    refund_id: str
    amount: int = Field(gt=0,strict=True)
    currency: Literal['VND']
    outcome: Literal['succeeded','failed']
