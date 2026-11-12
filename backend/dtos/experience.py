"""Validated experience request and response contracts."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator


class TryOnInput(BaseModel):
    product_id: str = Field(max_length=100)


class ChatInput(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Hãy nhập câu hỏi.")
        return value.strip()


class ChatReply(BaseModel):
    content: str
    product_ids: list[str] = Field(default_factory=list)
    mode: Literal["qwen-proxy"] = "qwen-proxy"
    message_id: int
