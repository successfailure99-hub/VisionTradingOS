"""
Immutable models for live option-chain runtime state.
"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from application.live_option_chain.enums import LiveOptionChainStatus
from brokers.zerodha.options import ZerodhaOptionRight
from brokers.zerodha.options.models import require_supported_underlying
from core.enums.instrument import Instrument
from engines.option_chain.models import OptionChainSnapshot, OptionChainState


def _require_positive_token(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("instrument_token must be positive integer")
    return value


def _require_real(value: Real, field_name: str, *, allow_zero: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be finite real")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{field_name} must be finite real")
    if allow_zero:
        if number < 0:
            raise ValueError(f"{field_name} must be non-negative")
    elif number <= 0:
        raise ValueError(f"{field_name} must be positive")
    return number


def _require_optional_non_negative(value: Real | None, field_name: str) -> float | None:
    if value is None:
        return None
    return _require_real(value, field_name, allow_zero=True)


def _require_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be non-negative integer")
    return value


def _require_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be integer")
    return value


def _require_date(value: date, field_name: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{field_name} must be date")
    return value


def _require_aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ZerodhaLiveOptionQuote:
    instrument_token: int
    underlying: Instrument
    expiry: date
    strike: float
    right: ZerodhaOptionRight
    last_price: float
    volume: int
    open_interest: int
    runtime_change_open_interest: int
    bid_price: float | None
    ask_price: float | None
    exchange_timestamp: datetime
    received_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_token", _require_positive_token(self.instrument_token))
        object.__setattr__(self, "underlying", require_supported_underlying(self.underlying))
        object.__setattr__(self, "expiry", _require_date(self.expiry, "expiry"))
        object.__setattr__(self, "strike", _require_real(self.strike, "strike", allow_zero=False))
        if not isinstance(self.right, ZerodhaOptionRight):
            raise TypeError("right must be ZerodhaOptionRight")
        object.__setattr__(self, "last_price", _require_real(self.last_price, "last_price", allow_zero=True))
        object.__setattr__(self, "volume", _require_non_negative_int(self.volume, "volume"))
        object.__setattr__(self, "open_interest", _require_non_negative_int(self.open_interest, "open_interest"))
        object.__setattr__(
            self,
            "runtime_change_open_interest",
            _require_int(self.runtime_change_open_interest, "runtime_change_open_interest"),
        )
        bid = _require_optional_non_negative(self.bid_price, "bid_price")
        ask = _require_optional_non_negative(self.ask_price, "ask_price")
        if bid is not None and ask is not None and bid > ask:
            raise ValueError("bid_price cannot exceed ask_price")
        object.__setattr__(self, "bid_price", bid)
        object.__setattr__(self, "ask_price", ask)
        _require_aware(self.exchange_timestamp, "exchange_timestamp")
        _require_aware(self.received_at, "received_at")


@dataclass(frozen=True, slots=True)
class LiveOptionQuoteBatchResult:
    received_count: int
    accepted_quotes: tuple[ZerodhaLiveOptionQuote, ...]
    duplicate_count: int
    stale_count: int
    rejected_count: int
    assembled: bool
    engine_updated: bool

    def __post_init__(self) -> None:
        accepted = tuple(self.accepted_quotes)
        for quote in accepted:
            if not isinstance(quote, ZerodhaLiveOptionQuote):
                raise TypeError("accepted_quotes must contain ZerodhaLiveOptionQuote values")
        object.__setattr__(self, "accepted_quotes", accepted)
        for name in ("received_count", "duplicate_count", "stale_count", "rejected_count"):
            _require_non_negative_int(getattr(self, name), name)
        if type(self.assembled) is not bool or type(self.engine_updated) is not bool:
            raise TypeError("assembled and engine_updated must be bool")
        if self.received_count != len(accepted) + self.duplicate_count + self.stale_count + self.rejected_count:
            raise ValueError("batch result counts are inconsistent")


@dataclass(frozen=True, slots=True)
class LiveOptionChainSnapshot:
    status: LiveOptionChainStatus
    underlying: Instrument
    expiry: date
    configured_token_count: int
    quoted_token_count: int
    fresh_token_count: int
    complete_pair_count: int
    expected_pair_count: int
    received_tick_count: int
    accepted_tick_count: int
    duplicate_tick_count: int
    stale_tick_count: int
    rejected_tick_count: int
    assembly_count: int
    engine_update_count: int
    underlying_price: float | None
    latest_quotes: tuple[ZerodhaLiveOptionQuote, ...]
    latest_option_chain_snapshot: OptionChainSnapshot | None
    latest_option_chain_analysis: OptionChainState | None
    last_batch_result: LiveOptionQuoteBatchResult | None
    last_received_at: datetime | None
    last_assembled_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LiveOptionChainStatus):
            raise TypeError("status must be LiveOptionChainStatus")
        object.__setattr__(self, "underlying", require_supported_underlying(self.underlying))
        object.__setattr__(self, "expiry", _require_date(self.expiry, "expiry"))
        for name in (
            "configured_token_count",
            "quoted_token_count",
            "fresh_token_count",
            "complete_pair_count",
            "expected_pair_count",
            "received_tick_count",
            "accepted_tick_count",
            "duplicate_tick_count",
            "stale_tick_count",
            "rejected_tick_count",
            "assembly_count",
            "engine_update_count",
        ):
            _require_non_negative_int(getattr(self, name), name)
        if self.underlying_price is not None:
            object.__setattr__(
                self,
                "underlying_price",
                _require_real(self.underlying_price, "underlying_price", allow_zero=False),
            )
        latest = tuple(self.latest_quotes)
        for quote in latest:
            if not isinstance(quote, ZerodhaLiveOptionQuote):
                raise TypeError("latest_quotes must contain ZerodhaLiveOptionQuote values")
        object.__setattr__(self, "latest_quotes", latest)
        if self.latest_option_chain_snapshot is not None and not isinstance(
            self.latest_option_chain_snapshot,
            OptionChainSnapshot,
        ):
            raise TypeError("latest_option_chain_snapshot must be OptionChainSnapshot or None")
        if self.latest_option_chain_analysis is not None and not isinstance(
            self.latest_option_chain_analysis,
            OptionChainState,
        ):
            raise TypeError("latest_option_chain_analysis must be OptionChainState or None")
        if self.last_batch_result is not None and not isinstance(self.last_batch_result, LiveOptionQuoteBatchResult):
            raise TypeError("last_batch_result must be LiveOptionQuoteBatchResult or None")
        if self.last_received_at is not None:
            _require_aware(self.last_received_at, "last_received_at")
        if self.last_assembled_at is not None:
            _require_aware(self.last_assembled_at, "last_assembled_at")
        if self.last_error is not None and not isinstance(self.last_error, str):
            raise TypeError("last_error must be str or None")
