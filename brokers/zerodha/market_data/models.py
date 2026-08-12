"""
Immutable Zerodha market-data models.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.models.tick import Tick

from brokers.zerodha.market_data.enums import ZerodhaSubscriptionMode, ZerodhaWebSocketStatus


class TickConsumerProtocol(Protocol):
    def __call__(self, tick: Tick) -> object:
        ...


def _require_aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ZerodhaInstrumentSubscription:
    instrument_token: int
    instrument: Instrument
    exchange: Exchange
    mode: ZerodhaSubscriptionMode = ZerodhaSubscriptionMode.FULL

    def __post_init__(self) -> None:
        if isinstance(self.instrument_token, bool) or not isinstance(self.instrument_token, int):
            raise TypeError("instrument_token must be a positive integer")
        if self.instrument_token <= 0:
            raise ValueError("instrument_token must be positive")
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be Instrument")
        if not isinstance(self.exchange, Exchange):
            raise TypeError("exchange must be Exchange")
        if not isinstance(self.mode, ZerodhaSubscriptionMode):
            raise TypeError("mode must be ZerodhaSubscriptionMode")


@dataclass(frozen=True, slots=True)
class ZerodhaWebSocketSnapshot:
    status: ZerodhaWebSocketStatus
    connected: bool
    subscribed_instruments: tuple[ZerodhaInstrumentSubscription, ...]
    connection_count: int
    disconnection_count: int
    reconnect_count: int
    raw_tick_count: int
    normalized_tick_count: int
    delivered_tick_count: int
    rejected_tick_count: int
    last_connected_at: datetime | None
    last_disconnected_at: datetime | None
    last_tick_at: datetime | None
    last_error: str | None
    retry_count: int = 0
    reconnect_delay_seconds: int = 0
    suppressed_error_count: int = 0
    reconnect_due_at: datetime | None = None
    client_instances_created: int = 1
    connect_attempts: int = 0
    successful_connections: int = 0
    disconnect_callbacks: int = 0
    error_callbacks: int = 0
    retry_scheduled: int = 0
    subscriptions_applied: int = 0
    duplicate_callbacks_suppressed: int = 0
    reconnect_owner: str = "on_close"
    broker_received_at: datetime | None = None
    tick_exchange_timestamp: datetime | None = None
    tick_normalized_at: datetime | None = None
    event_published_at: datetime | None = None
    runtime_processed_at: datetime | None = None
    latest_tick_latency_ms: float | None = None
    max_tick_latency_ms: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ZerodhaWebSocketStatus):
            raise TypeError("status must be ZerodhaWebSocketStatus")
        object.__setattr__(self, "subscribed_instruments", tuple(self.subscribed_instruments))
        for name in (
            "connection_count",
            "disconnection_count",
            "reconnect_count",
            "raw_tick_count",
            "normalized_tick_count",
            "delivered_tick_count",
            "rejected_tick_count",
            "retry_count",
            "reconnect_delay_seconds",
            "suppressed_error_count",
            "client_instances_created",
            "connect_attempts",
            "successful_connections",
            "disconnect_callbacks",
            "error_callbacks",
            "retry_scheduled",
            "subscriptions_applied",
            "duplicate_callbacks_suppressed",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        _require_aware(self.last_connected_at, "last_connected_at")
        _require_aware(self.last_disconnected_at, "last_disconnected_at")
        _require_aware(self.reconnect_due_at, "reconnect_due_at")
        _require_aware(self.last_tick_at, "last_tick_at")
        for name in (
            "broker_received_at",
            "tick_exchange_timestamp",
            "tick_normalized_at",
            "event_published_at",
            "runtime_processed_at",
        ):
            _require_aware(getattr(self, name), name)
        for name in ("latest_tick_latency_ms", "max_tick_latency_ms"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, (int, float)) or value < 0):
                raise ValueError(f"{name} must be a non-negative number or None")


@dataclass(frozen=True, slots=True)
class ZerodhaTickBatchResult:
    received_count: int
    normalized_ticks: tuple[Tick, ...]
    delivered_ticks: tuple[Tick, ...]
    rejected_count: int

    def __post_init__(self) -> None:
        for name in ("received_count", "rejected_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        object.__setattr__(self, "normalized_ticks", tuple(self.normalized_ticks))
        object.__setattr__(self, "delivered_ticks", tuple(self.delivered_ticks))
        if any(not _matches_normalized_tick(tick, self.normalized_ticks) for tick in self.delivered_ticks):
            raise ValueError("delivered_ticks must be a subset of normalized_ticks")


def _matches_normalized_tick(delivered: Tick, normalized_ticks: tuple[Tick, ...]) -> bool:
    for normalized in normalized_ticks:
        if (
            delivered.symbol is normalized.symbol
            and delivered.exchange is normalized.exchange
            and delivered.timestamp == normalized.timestamp
            and delivered.last_price == normalized.last_price
            and delivered.bid_price == normalized.bid_price
            and delivered.ask_price == normalized.ask_price
            and delivered.open_interest == normalized.open_interest
        ):
            return True
    return False
