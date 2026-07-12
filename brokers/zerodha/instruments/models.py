"""
Immutable Zerodha instrument discovery models.
"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite

from brokers.zerodha.instruments.enums import ZerodhaInstrumentDiscoveryStatus, ZerodhaInstrumentType
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


def _require_positive_int(value: int | None, field_name: str, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _require_date(value: date | None, field_name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{field_name} must be a date or None")
    return value


def _require_non_negative_float(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


def _require_positive_float(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{field_name} must be finite and positive")
    return normalized


@dataclass(frozen=True, slots=True)
class ZerodhaInstrumentRecord:
    instrument_token: int
    exchange_token: int | None
    tradingsymbol: str
    name: str
    exchange: Exchange
    segment: str
    instrument_type: ZerodhaInstrumentType
    expiry: date | None
    strike: float | None
    lot_size: int | None
    tick_size: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_token", _require_positive_int(self.instrument_token, "instrument_token"))
        object.__setattr__(self, "exchange_token", _require_positive_int(self.exchange_token, "exchange_token", optional=True))
        object.__setattr__(self, "tradingsymbol", _require_text(self.tradingsymbol, "tradingsymbol"))
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        if not isinstance(self.exchange, Exchange):
            raise TypeError("exchange must be Exchange")
        object.__setattr__(self, "segment", _require_text(self.segment, "segment"))
        if not isinstance(self.instrument_type, ZerodhaInstrumentType):
            raise TypeError("instrument_type must be ZerodhaInstrumentType")
        object.__setattr__(self, "expiry", _require_date(self.expiry, "expiry"))
        object.__setattr__(self, "strike", _require_non_negative_float(self.strike, "strike"))
        object.__setattr__(self, "lot_size", _require_positive_int(self.lot_size, "lot_size", optional=True))
        object.__setattr__(self, "tick_size", _require_positive_float(self.tick_size, "tick_size"))


@dataclass(frozen=True, slots=True)
class ZerodhaInstrumentResolution:
    instrument: Instrument
    record: ZerodhaInstrumentRecord
    subscription: ZerodhaInstrumentSubscription

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be Instrument")
        if not isinstance(self.record, ZerodhaInstrumentRecord):
            raise TypeError("record must be ZerodhaInstrumentRecord")
        if not isinstance(self.subscription, ZerodhaInstrumentSubscription):
            raise TypeError("subscription must be ZerodhaInstrumentSubscription")
        if self.record.instrument_token != self.subscription.instrument_token:
            raise ValueError("record and subscription token must match")
        if self.instrument is not self.subscription.instrument:
            raise ValueError("instrument and subscription instrument must match")
        if self.record.exchange is not self.subscription.exchange:
            raise ValueError("record and subscription exchange must match")


@dataclass(frozen=True, slots=True)
class ZerodhaInstrumentDiscoverySnapshot:
    status: ZerodhaInstrumentDiscoveryStatus
    record_count: int
    index_record_count: int
    supported_resolution_count: int
    loaded_exchanges: tuple[Exchange, ...]
    loaded_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ZerodhaInstrumentDiscoveryStatus):
            raise TypeError("status must be ZerodhaInstrumentDiscoveryStatus")
        for name in ("record_count", "index_record_count", "supported_resolution_count"):
            _require_positive_or_zero(getattr(self, name), name)
        exchanges = tuple(self.loaded_exchanges)
        if any(not isinstance(exchange, Exchange) for exchange in exchanges):
            raise TypeError("loaded_exchanges must contain Exchange values")
        object.__setattr__(self, "loaded_exchanges", exchanges)
        if self.loaded_at is not None:
            if not isinstance(self.loaded_at, datetime):
                raise TypeError("loaded_at must be datetime or None")
            if self.loaded_at.tzinfo is None or self.loaded_at.utcoffset() is None:
                raise ValueError("loaded_at must be timezone-aware")


def _require_positive_or_zero(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
