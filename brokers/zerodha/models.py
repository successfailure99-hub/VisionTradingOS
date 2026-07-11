"""
Immutable Zerodha Broker Adapter V1 models.
"""

from dataclasses import dataclass
from datetime import datetime

from brokers.zerodha.enums import BrokerAction, BrokerResultStatus, ZerodhaOrderStatus


@dataclass(frozen=True, slots=True)
class BrokerRequest:
    action: BrokerAction
    client_order_id: str
    broker_order_id: str | None
    parameters: tuple[tuple[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return dict(self.parameters)


@dataclass(frozen=True, slots=True)
class BrokerExecutionResult:
    action: BrokerAction
    status: BrokerResultStatus
    client_order_id: str
    broker_order_id: str | None
    request: BrokerRequest
    error_message: str | None


@dataclass(frozen=True, slots=True)
class ZerodhaOrderUpdate:
    order_id: str
    status: ZerodhaOrderStatus
    timestamp: datetime

    filled_quantity: int
    pending_quantity: int
    average_price: float

    status_message: str | None = None
