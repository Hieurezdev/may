"""HTTP route composition for the commercial lifecycle."""

from fastapi import APIRouter
from . import checkout, fulfillment, payments, returns, notifications

router = APIRouter()
for module in (checkout,payments,fulfillment,returns,notifications):
    router.include_router(module.router)
