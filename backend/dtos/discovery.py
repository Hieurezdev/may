"""Validated discovery request and response contracts."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class ConsentInput(BaseModel):
    consent: bool


class TrainInput(BaseModel):
    eps: float = Field(gt=0,le=20)
    min_samples: int = Field(ge=2,le=100,strict=True)
    cutoff_at: str


class SearchInput(BaseModel):
    query: str = Field(default='',max_length=200)
    category: str = Field(default='',max_length=100)
    image_base64: str | None = Field(default=None,max_length=7000000)
    media_consent: bool = False
    semantic: bool = True
    limit: int = Field(default=20,ge=1,le=100)


class EmbeddingResponse(BaseModel):
    model_revision: str = Field(min_length=1)
    vector: list[float] = Field(min_length=2,max_length=4096)


class IndexInput(BaseModel):
    kind: Literal['text','image']
