"""
Immutable Order Management Engine V1 models.
"""

from dataclasses import dataclass
from datetime import datetime

from engines.order_management.enums import (
    OrderCommandType,
    OrderRejectionReason,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
)
from engines.risk.models import RiskDecisionState


@dataclass(frozen=True, slots=True)
class OrderRequest:
    client_order_id: str
    symbol: str
    exchange: str
    timeframe: str
    timestamp: datetime

    side: OrderSide
    order_type: OrderType
    product_type: ProductType

    quantity: int

    limit_price: float | None = None
    trigger_price: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.client_order_id, str):
            object.__setattr__(self, "client_order_id", self.client_order_id.strip())
        if isinstance(self.symbol, str):
            object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if isinstance(self.exchange, str):
            object.__setattr__(self, "exchange", self.exchange.strip().upper())
        if isinstance(self.timeframe, str):
            object.__setattr__(self, "timeframe", self.timeframe.strip())


@dataclass(frozen=True, slots=True)
class OrderCommand:
    command_type: OrderCommandType
    client_order_id: str
    timestamp: datetime

    broker_order_id: str | None = None

    new_quantity: int | None = None
    new_limit_price: float | None = None
    new_trigger_price: float | None = None

    fill_quantity: int | None = None
    fill_price: float | None = None

    rejection_message: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.client_order_id, str):
            object.__setattr__(self, "client_order_id", self.client_order_id.strip())
        if isinstance(self.broker_order_id, str):
            object.__setattr__(self, "broker_order_id", self.broker_order_id.strip())
        if isinstance(self.rejection_message, str):
            object.__setattr__(self, "rejection_message", self.rejection_message.strip())


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    symbol: str
    timeframe: str
    timestamp: datetime

    risk: RiskDecisionState
    request: OrderRequest

    def __post_init__(self) -> None:
        if isinstance(self.symbol, str):
            object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if isinstance(self.timeframe, str):
            object.__setattr__(self, "timeframe", self.timeframe.strip())


@dataclass(frozen=True, slots=True)
class OrderState:
    client_order_id: str
    broker_order_id: str | None

    symbol: str
    exchange: str
    timeframe: str

    created_at: datetime
    updated_at: datetime

    side: OrderSide
    order_type: OrderType
    product_type: ProductType

    status: OrderStatus

    quantity: int
    filled_quantity: int
    remaining_quantity: int
    average_fill_price: float | None

    limit_price: float | None
    trigger_price: float | None

    risk_entry_price: float
    risk_stop_price: float
    risk_target_price: float
    estimated_risk_amount: float

    rejection_reason: OrderRejectionReason
    rejection_message: str | None

    version: int
