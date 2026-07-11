"""
Immutable Position Management Engine V1 models.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real

from engines.order_management.enums import OrderSide
from engines.position.enums import PositionSide, PositionStatus, PositionUpdateType


def _normalize_required(value: str, name: str, upper: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string.")
    normalized = value.strip()
    if upper:
        normalized = normalized.upper()
    if not normalized:
        raise ValueError(f"{name} cannot be empty.")
    return normalized


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a positive integer.")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def _positive_float(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite positive number.")
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite positive number.")
    return number


@dataclass(frozen=True, slots=True)
class PositionFill:
    execution_id: str
    client_order_id: str
    broker_order_id: str | None

    symbol: str
    exchange: str
    timeframe: str
    timestamp: datetime

    side: OrderSide
    quantity: int
    price: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_id", _normalize_required(self.execution_id, "execution_id"))
        object.__setattr__(self, "client_order_id", _normalize_required(self.client_order_id, "client_order_id"))
        if self.broker_order_id is not None:
            object.__setattr__(self, "broker_order_id", _normalize_required(self.broker_order_id, "broker_order_id"))
        object.__setattr__(self, "symbol", _normalize_required(self.symbol, "symbol", upper=True))
        object.__setattr__(self, "exchange", _normalize_required(self.exchange, "exchange", upper=True))
        object.__setattr__(self, "timeframe", _normalize_required(self.timeframe, "timeframe"))
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime.")
        if not isinstance(self.side, OrderSide):
            raise ValueError("side must be an OrderSide.")
        object.__setattr__(self, "quantity", _positive_int(self.quantity, "quantity"))
        object.__setattr__(self, "price", _positive_float(self.price, "price"))


@dataclass(frozen=True, slots=True)
class PositionMark:
    symbol: str
    exchange: str
    timeframe: str
    timestamp: datetime
    mark_price: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_required(self.symbol, "symbol", upper=True))
        object.__setattr__(self, "exchange", _normalize_required(self.exchange, "exchange", upper=True))
        object.__setattr__(self, "timeframe", _normalize_required(self.timeframe, "timeframe"))
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime.")
        object.__setattr__(self, "mark_price", _positive_float(self.mark_price, "mark_price"))


@dataclass(frozen=True, slots=True)
class PositionState:
    symbol: str
    exchange: str
    timeframe: str

    side: PositionSide
    status: PositionStatus

    opened_at: datetime | None
    updated_at: datetime
    closed_at: datetime | None

    net_quantity: int
    absolute_quantity: int

    average_entry_price: float | None
    mark_price: float | None

    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float

    total_buy_quantity: int
    total_sell_quantity: int

    last_fill_execution_id: str | None
    last_fill_price: float | None
    last_fill_quantity: int | None
    last_update_type: PositionUpdateType

    version: int
