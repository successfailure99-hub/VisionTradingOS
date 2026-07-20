"""
Immutable models for the Zerodha read-only connectivity adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from brokers.zerodha.market_data import ZerodhaSubscriptionMode
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument

from .enums import ZerodhaConnectionState


SUPPORTED_INSTRUMENTS = (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be non-empty text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty text")
    return normalized


def _instrument(value: str | Instrument) -> Instrument:
    if isinstance(value, Instrument):
        instrument = value
    elif isinstance(value, str):
        instrument = Instrument.from_symbol(value)
    else:
        raise TypeError("instrument must be Instrument or text")
    if instrument not in SUPPORTED_INSTRUMENTS:
        raise ValueError("unsupported Zerodha read-only instrument")
    return instrument


def _exchange(value: str | Exchange) -> Exchange:
    if isinstance(value, Exchange):
        return value
    if isinstance(value, str):
        return Exchange.from_value(value)
    raise TypeError("exchange must be Exchange or text")


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _aware_or_none(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True, repr=False)
class ZerodhaCredentials:
    api_key: str
    access_token: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "api_key", _text(self.api_key, "api_key"))
        object.__setattr__(self, "access_token", _text(self.access_token, "access_token"))

    def __repr__(self) -> str:
        suffix = self.api_key[-4:] if len(self.api_key) >= 4 else self.api_key
        return f"ZerodhaCredentials(api_key='****{suffix}', access_token='[REDACTED]')"

    __str__ = __repr__


@dataclass(frozen=True, slots=True)
class ZerodhaInstrumentToken:
    instrument: Instrument
    exchange: Exchange
    trading_symbol: str
    instrument_token: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        object.__setattr__(self, "exchange", _exchange(self.exchange))
        object.__setattr__(self, "trading_symbol", _text(self.trading_symbol, "trading_symbol"))
        object.__setattr__(self, "instrument_token", _positive_int(self.instrument_token, "instrument_token"))


@dataclass(frozen=True, slots=True)
class ZerodhaSubscription:
    instrument: Instrument
    instrument_token: int
    mode: str = ZerodhaSubscriptionMode.FULL.value

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        object.__setattr__(self, "instrument_token", _positive_int(self.instrument_token, "instrument_token"))
        mode = _text(self.mode, "mode").lower()
        if mode != ZerodhaSubscriptionMode.FULL.value:
            raise ValueError("Zerodha read-only adapter supports full market-data mode")
        object.__setattr__(self, "mode", mode)


@dataclass(frozen=True, slots=True)
class ZerodhaConnectionSnapshot:
    enabled: bool
    state: ZerodhaConnectionState
    connected: bool
    authenticated: bool
    subscribed_instruments: tuple[Instrument, ...]
    resolved_tokens: tuple[ZerodhaInstrumentToken, ...]
    received_tick_count: int
    published_tick_count: int
    rejected_tick_count: int
    duplicate_tick_count: int
    last_tick_at: datetime | None
    last_connected_at: datetime | None
    last_disconnected_at: datetime | None
    last_error_code: str | None
    broker_order_calls: int = 0
    mutation_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool")
        if not isinstance(self.state, ZerodhaConnectionState):
            raise TypeError("state must be ZerodhaConnectionState")
        if not isinstance(self.connected, bool):
            raise TypeError("connected must be bool")
        if not isinstance(self.authenticated, bool):
            raise TypeError("authenticated must be bool")
        subscribed = tuple(_instrument(instrument) for instrument in self.subscribed_instruments)
        if len(subscribed) != len(set(subscribed)):
            raise ValueError("subscribed_instruments must be unique")
        object.__setattr__(self, "subscribed_instruments", subscribed)
        tokens = tuple(self.resolved_tokens)
        if any(not isinstance(token, ZerodhaInstrumentToken) for token in tokens):
            raise TypeError("resolved_tokens must contain ZerodhaInstrumentToken values")
        if len({token.instrument for token in tokens}) != len(tokens):
            raise ValueError("resolved token instruments must be unique")
        if len({token.instrument_token for token in tokens}) != len(tokens):
            raise ValueError("resolved instrument tokens must be unique")
        object.__setattr__(self, "resolved_tokens", tokens)
        for field_name in (
            "received_tick_count",
            "published_tick_count",
            "rejected_tick_count",
            "duplicate_tick_count",
            "broker_order_calls",
            "mutation_calls",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        _aware_or_none(self.last_tick_at, "last_tick_at")
        _aware_or_none(self.last_connected_at, "last_connected_at")
        _aware_or_none(self.last_disconnected_at, "last_disconnected_at")
        if self.last_error_code is not None:
            object.__setattr__(self, "last_error_code", _text(self.last_error_code, "last_error_code"))
        if self.broker_order_calls != 0:
            raise ValueError("broker_order_calls must remain zero")
        if self.mutation_calls != 0:
            raise ValueError("mutation_calls must remain zero")
        if self.live_order_submission_enabled is not False:
            raise ValueError("live_order_submission_enabled must remain False")
