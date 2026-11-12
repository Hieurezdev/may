"""Validated accounts request and response contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, ConfigDict


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="Khách", min_length=2, max_length=100)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return value.lower().strip()


class AddressInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    recipient_name: str = Field(min_length=2,max_length=100)
    phone: str = Field(pattern=r'^(?:0[35789]\d{8}|\+84[35789]\d{8})$')
    address: str = Field(min_length=10,max_length=500)
