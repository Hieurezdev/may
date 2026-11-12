"""Domain values shared by services; amounts use integer VND minor units."""

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    CUSTOMER = "customer"
    MERCHANT = "merchant"
    SUPPORT = "support"
    OPERATOR = "operator"


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PAYMENT_FAILED = "payment_failed"
    RECONCILIATION = "reconciliation"


class ReservationState(StrEnum):
    HELD = "held"
    COMMITTED = "committed"
    RELEASED = "released"
    DISPATCHED = "dispatched"


@dataclass(frozen=True)
class InventoryPosition:
    id: str
    on_hand: int
    reserved: int

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


@dataclass(frozen=True)
class OrderLine:
    id: str
    variant_id: str
    quantity: int
    unit_price: int
    discount_minor: int

    @property
    def refundable_minor(self) -> int:
        return self.quantity * self.unit_price - self.discount_minor


@dataclass(frozen=True)
class Order:
    id: str
    customer_id: str
    status: OrderStatus
    total: int
    lines: tuple[OrderLine, ...]

    @property
    def can_cancel(self) -> bool:
        return self.status in {OrderStatus.PENDING_PAYMENT,OrderStatus.CONFIRMED,OrderStatus.PAID,
                               OrderStatus.PROCESSING,OrderStatus.PAYMENT_FAILED,OrderStatus.EXPIRED}


@dataclass(frozen=True)
class CustomerFeatures:
    customer_id: str
    values: tuple[float, ...]
