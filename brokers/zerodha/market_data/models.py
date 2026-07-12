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
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        _require_aware(self.last_connected_at, "last_connected_at")
        _require_aware(self.last_disconnected_at, "last_disconnected_at")
        _require_aware(self.last_tick_at, "last_tick_at")


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
        normalized = set(self.normalized_ticks)
        if any(tick not in normalized for tick in self.delivered_ticks):
            raise ValueError("delivered_ticks must be a subset of normalized_ticks")
