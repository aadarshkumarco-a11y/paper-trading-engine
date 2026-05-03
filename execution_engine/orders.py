"""Order and trade dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

from utils.market_hours import now_ist


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is OrderSide.BUY else -1


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


def _new_id() -> str:
    return uuid4().hex[:12]


@dataclass
class Order:
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    strategy: str = "manual"
    id: str = field(default_factory=_new_id)
    status: OrderStatus = OrderStatus.PENDING
    submitted_at: datetime = field(default_factory=now_ist)
    filled_at: datetime | None = None
    fill_price: float | None = None
    rejected_reason: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Order quantity must be positive")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("Limit orders require a limit_price")

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["side"] = self.side.value
        d["order_type"] = self.order_type.value
        d["status"] = self.status.value
        d["submitted_at"] = self.submitted_at.isoformat()
        d["filled_at"] = self.filled_at.isoformat() if self.filled_at else None
        return d


@dataclass
class Trade:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    brokerage: float
    timestamp: datetime = field(default_factory=now_ist)
    strategy: str = "manual"

    @property
    def gross_value(self) -> float:
        return self.price * self.quantity

    @property
    def cash_delta(self) -> float:
        """Cash impact on the account (negative for buys including brokerage)."""
        return -self.side.sign * self.gross_value - self.brokerage

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["side"] = self.side.value
        d["timestamp"] = self.timestamp.isoformat()
        return d
