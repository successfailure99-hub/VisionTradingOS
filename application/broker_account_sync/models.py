"""
Immutable read-only broker account synchronization models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .enums import (
    BrokerConnectionState,
    BrokerMutationMode,
    BrokerReconciliationStatus,
    BrokerRuntimeStatus,
    BrokerSessionState,
)

SENSITIVE_FIELD_NAMES = ("access_token", "request_token", "api_secret", "password", "pin", "totp", "totp_seed")


def _text(value: str, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must be non-empty text")
    _reject_secret_text(normalized, field_name)
    return normalized or "-"


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _number(value, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    return float(value)


def _non_negative_number(value, field_name: str) -> float:
    numeric = _number(value, field_name)
    if numeric < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return numeric


def _int(value, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    return value


def _non_negative_int(value, field_name: str) -> int:
    numeric = _int(value, field_name)
    if numeric < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return numeric


def _aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _reject_secret_text(value: str, field_name: str) -> None:
    lowered_name = field_name.casefold()
    if any(secret in lowered_name for secret in SENSITIVE_FIELD_NAMES):
        raise ValueError(f"{field_name} is not allowed in broker account snapshots")
    lowered = value.casefold()
    if any(secret in lowered for secret in ("access_token", "api_secret", "request_token", "totp_seed")):
        raise ValueError(f"{field_name} appears to contain sensitive broker material")


def mask_account_id(value: str | None) -> str:
    if value is None or not str(value).strip():
        return "-"
    raw = str(value).strip()
    _reject_secret_text(raw, "account_id")
    if len(raw) <= 4:
        return "*" * len(raw)
    return f"****{raw[-4:]}"


@dataclass(frozen=True, slots=True)
class BrokerPositionSnapshot:
    instrument: str
    exchange: str
    product: str
    quantity: int
    overnight_quantity: int
    average_price: float
    last_price: float
    unrealized_pnl: float
    realized_pnl: float
    buy_quantity: int
    sell_quantity: int

    def __post_init__(self) -> None:
        for name in ("instrument", "exchange", "product"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("quantity", "overnight_quantity", "buy_quantity", "sell_quantity"):
            object.__setattr__(self, name, _int(getattr(self, name), name))
        for name in ("average_price", "last_price", "unrealized_pnl", "realized_pnl"):
            object.__setattr__(self, name, _number(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class BrokerHoldingSnapshot:
    instrument: str
    exchange: str
    quantity: int
    t1_quantity: int
    average_price: float
    last_price: float
    pnl: float
    collateral_quantity: int

    def __post_init__(self) -> None:
        for name in ("instrument", "exchange"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("quantity", "t1_quantity", "collateral_quantity"):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        for name in ("average_price", "last_price", "pnl"):
            object.__setattr__(self, name, _number(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class BrokerOrderStatusSnapshot:
    order_id: str
    instrument: str
    exchange: str
    transaction_type: str
    order_type: str
    product: str
    quantity: int
    filled_quantity: int
    pending_quantity: int
    average_price: float
    status: str
    status_message: str | None
    created_at: datetime | None
    updated_at: datetime | None

    def __post_init__(self) -> None:
        for name in ("order_id", "instrument", "exchange", "transaction_type", "order_type", "product", "status"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "status_message", _optional_text(self.status_message, "status_message"))
        for name in ("quantity", "filled_quantity", "pending_quantity"):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        if self.filled_quantity + self.pending_quantity > self.quantity:
            raise ValueError("filled and pending quantities cannot exceed order quantity")
        object.__setattr__(self, "average_price", _number(self.average_price, "average_price"))
        object.__setattr__(self, "created_at", _aware(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _aware(self.updated_at, "updated_at"))


@dataclass(frozen=True, slots=True)
class BrokerReconciliationSnapshot:
    paper_position_present: bool
    broker_position_present: bool
    instrument_match: bool
    quantity_match: bool
    direction_match: bool
    reconciliation_status: BrokerReconciliationStatus
    blocking_reason: str = "-"

    def __post_init__(self) -> None:
        for name in ("paper_position_present", "broker_position_present", "instrument_match", "quantity_match", "direction_match"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
        if not isinstance(self.reconciliation_status, BrokerReconciliationStatus):
            raise TypeError("reconciliation_status must be BrokerReconciliationStatus")
        object.__setattr__(self, "blocking_reason", _text(self.blocking_reason, "blocking_reason"))


@dataclass(frozen=True, slots=True)
class BrokerAccountSnapshot:
    broker: str
    account_id_masked: str
    timestamp: datetime
    session_state: BrokerSessionState
    connection_state: BrokerConnectionState
    authentication_state: BrokerSessionState
    equity_available: float
    equity_used: float
    commodity_available: float
    commodity_used: float
    total_available_margin: float
    positions: tuple[BrokerPositionSnapshot, ...]
    holdings: tuple[BrokerHoldingSnapshot, ...]
    orders: tuple[BrokerOrderStatusSnapshot, ...]
    latest_refresh_timestamp: datetime | None
    data_age: float | None
    is_stale: bool
    blocking_reason: str
    mutation_mode: BrokerMutationMode = BrokerMutationMode.DISABLED
    reconciliation: BrokerReconciliationSnapshot | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "broker", _text(self.broker, "broker"))
        object.__setattr__(self, "account_id_masked", _text(self.account_id_masked, "account_id_masked"))
        object.__setattr__(self, "timestamp", _aware(self.timestamp, "timestamp"))
        if not isinstance(self.session_state, BrokerSessionState):
            raise TypeError("session_state must be BrokerSessionState")
        if not isinstance(self.connection_state, BrokerConnectionState):
            raise TypeError("connection_state must be BrokerConnectionState")
        if not isinstance(self.authentication_state, BrokerSessionState):
            raise TypeError("authentication_state must be BrokerSessionState")
        for name in ("equity_available", "equity_used", "commodity_available", "commodity_used", "total_available_margin"):
            object.__setattr__(self, name, _non_negative_number(getattr(self, name), name))
        positions = tuple(self.positions)
        holdings = tuple(self.holdings)
        orders = tuple(self.orders)
        if any(not isinstance(item, BrokerPositionSnapshot) for item in positions):
            raise TypeError("positions must contain BrokerPositionSnapshot values")
        if any(not isinstance(item, BrokerHoldingSnapshot) for item in holdings):
            raise TypeError("holdings must contain BrokerHoldingSnapshot values")
        if any(not isinstance(item, BrokerOrderStatusSnapshot) for item in orders):
            raise TypeError("orders must contain BrokerOrderStatusSnapshot values")
        object.__setattr__(self, "positions", positions)
        object.__setattr__(self, "holdings", holdings)
        object.__setattr__(self, "orders", orders)
        object.__setattr__(self, "latest_refresh_timestamp", _aware(self.latest_refresh_timestamp, "latest_refresh_timestamp"))
        if self.data_age is not None:
            object.__setattr__(self, "data_age", _non_negative_number(self.data_age, "data_age"))
        if not isinstance(self.is_stale, bool):
            raise TypeError("is_stale must be bool")
        object.__setattr__(self, "blocking_reason", _text(self.blocking_reason, "blocking_reason"))
        if not isinstance(self.mutation_mode, BrokerMutationMode):
            raise TypeError("mutation_mode must be BrokerMutationMode")
        if self.mutation_mode is not BrokerMutationMode.DISABLED:
            raise ValueError("broker mutation mode must remain DISABLED")
        if self.reconciliation is not None and not isinstance(self.reconciliation, BrokerReconciliationSnapshot):
            raise TypeError("reconciliation must be BrokerReconciliationSnapshot or None")


@dataclass(frozen=True, slots=True)
class BrokerRuntimeVerificationStage:
    stage: str
    owner: str
    producer: str
    consumer: str
    timestamp: datetime | None
    status: BrokerRuntimeStatus
    data_age: float | None
    recovery_state: str
    blocking_reason: str

    def __post_init__(self) -> None:
        for name in ("stage", "owner", "producer", "consumer", "recovery_state", "blocking_reason"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "timestamp", _aware(self.timestamp, "timestamp"))
        if not isinstance(self.status, BrokerRuntimeStatus):
            raise TypeError("status must be BrokerRuntimeStatus")
        if self.data_age is not None:
            object.__setattr__(self, "data_age", _non_negative_number(self.data_age, "data_age"))