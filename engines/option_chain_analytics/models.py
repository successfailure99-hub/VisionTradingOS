"""
Immutable Option Chain Analytics Engine V1 models.
"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from core.enums.instrument import Instrument
from engines.option_chain.enums import OptionType
from engines.option_chain.models import OptionChainSnapshot, OptionChainState
from engines.option_chain_analytics.enums import (
    OptionAnalyticsBias,
    OptionBuildUpType,
    OptionLevelMigration,
    OptionPressureType,
    OptionTrendDirection,
)


@dataclass(frozen=True, slots=True)
class OptionLegAnalytics:
    strike: float
    side: OptionType
    current_price: float
    previous_price: float | None
    price_change: float | None
    current_open_interest: int
    previous_open_interest: int | None
    runtime_change_open_interest: int
    open_interest_delta_from_previous_snapshot: int | None
    build_up: OptionBuildUpType

    def __post_init__(self) -> None:
        object.__setattr__(self, "strike", _positive_real(self.strike, "strike"))
        if not isinstance(self.side, OptionType):
            raise TypeError("side must be OptionType")
        object.__setattr__(self, "current_price", _non_negative_real(self.current_price, "current_price"))
        if self.previous_price is not None:
            object.__setattr__(self, "previous_price", _non_negative_real(self.previous_price, "previous_price"))
        if self.price_change is not None:
            object.__setattr__(self, "price_change", _real(self.price_change, "price_change"))
        object.__setattr__(self, "current_open_interest", _non_negative_int(self.current_open_interest, "current_open_interest"))
        if self.previous_open_interest is not None:
            object.__setattr__(
                self,
                "previous_open_interest",
                _non_negative_int(self.previous_open_interest, "previous_open_interest"),
            )
        object.__setattr__(
            self,
            "runtime_change_open_interest",
            _int(self.runtime_change_open_interest, "runtime_change_open_interest"),
        )
        if self.open_interest_delta_from_previous_snapshot is not None:
            object.__setattr__(
                self,
                "open_interest_delta_from_previous_snapshot",
                _int(self.open_interest_delta_from_previous_snapshot, "open_interest_delta_from_previous_snapshot"),
            )
        if not isinstance(self.build_up, OptionBuildUpType):
            raise TypeError("build_up must be OptionBuildUpType")


@dataclass(frozen=True, slots=True)
class OptionStrikeAnalytics:
    strike: float
    call: OptionLegAnalytics | None
    put: OptionLegAnalytics | None
    net_runtime_oi_change: int
    dominant_pressure: OptionPressureType

    def __post_init__(self) -> None:
        object.__setattr__(self, "strike", _positive_real(self.strike, "strike"))
        if self.call is not None and not isinstance(self.call, OptionLegAnalytics):
            raise TypeError("call must be OptionLegAnalytics or None")
        if self.put is not None and not isinstance(self.put, OptionLegAnalytics):
            raise TypeError("put must be OptionLegAnalytics or None")
        object.__setattr__(self, "net_runtime_oi_change", _int(self.net_runtime_oi_change, "net_runtime_oi_change"))
        if not isinstance(self.dominant_pressure, OptionPressureType):
            raise TypeError("dominant_pressure must be OptionPressureType")


@dataclass(frozen=True, slots=True)
class OptionPressureSummary:
    call_writing_oi: int
    put_writing_oi: int
    call_unwinding_oi: int
    put_unwinding_oi: int
    call_short_buildup_count: int
    put_short_buildup_count: int
    call_short_covering_count: int
    put_short_covering_count: int
    pressure_ratio: float | None
    dominant_pressure: OptionPressureType

    def __post_init__(self) -> None:
        for name in (
            "call_writing_oi",
            "put_writing_oi",
            "call_unwinding_oi",
            "put_unwinding_oi",
            "call_short_buildup_count",
            "put_short_buildup_count",
            "call_short_covering_count",
            "put_short_covering_count",
        ):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        if self.pressure_ratio is not None:
            object.__setattr__(self, "pressure_ratio", _non_negative_real(self.pressure_ratio, "pressure_ratio"))
        if not isinstance(self.dominant_pressure, OptionPressureType):
            raise TypeError("dominant_pressure must be OptionPressureType")


@dataclass(frozen=True, slots=True)
class OptionMetricTrend:
    current_value: float | None
    previous_value: float | None
    change: float | None
    direction: OptionTrendDirection

    def __post_init__(self) -> None:
        if self.current_value is not None:
            object.__setattr__(self, "current_value", _real(self.current_value, "current_value"))
        if self.previous_value is not None:
            object.__setattr__(self, "previous_value", _real(self.previous_value, "previous_value"))
        if self.change is not None:
            object.__setattr__(self, "change", _real(self.change, "change"))
        if not isinstance(self.direction, OptionTrendDirection):
            raise TypeError("direction must be OptionTrendDirection")


@dataclass(frozen=True, slots=True)
class OptionChainAnalyticsSnapshot:
    underlying: Instrument
    expiry: date
    timestamp: datetime
    source_snapshot: OptionChainSnapshot
    source_analysis: OptionChainState
    strikes: tuple[OptionStrikeAnalytics, ...]
    pressure: OptionPressureSummary
    pcr_trend: OptionMetricTrend
    change_oi_pcr_trend: OptionMetricTrend
    max_pain_trend: OptionMetricTrend
    support_migration: OptionLevelMigration
    resistance_migration: OptionLevelMigration
    atm_migration: OptionLevelMigration
    previous_support: float | None
    current_support: float | None
    previous_resistance: float | None
    current_resistance: float | None
    previous_atm_strike: float | None
    current_atm_strike: float | None
    bullish_score: int
    bearish_score: int
    bias: OptionAnalyticsBias
    rationale: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.underlying, Instrument):
            raise TypeError("underlying must be Instrument")
        if not isinstance(self.expiry, date) or isinstance(self.expiry, datetime):
            raise TypeError("expiry must be date")
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.source_snapshot, OptionChainSnapshot):
            raise TypeError("source_snapshot must be OptionChainSnapshot")
        if not isinstance(self.source_analysis, OptionChainState):
            raise TypeError("source_analysis must be OptionChainState")
        if self.source_snapshot.expiry_date != self.expiry or self.source_analysis.expiry_date != self.expiry:
            raise ValueError("source expiry must match analytics expiry")
        if self.source_snapshot.symbol != self.underlying.value or self.source_analysis.symbol != self.underlying.value:
            raise ValueError("source underlying must match analytics underlying")
        strikes = tuple(self.strikes)
        for strike in strikes:
            if not isinstance(strike, OptionStrikeAnalytics):
                raise TypeError("strikes must contain OptionStrikeAnalytics")
        object.__setattr__(self, "strikes", strikes)
        if not isinstance(self.pressure, OptionPressureSummary):
            raise TypeError("pressure must be OptionPressureSummary")
        for trend_name in ("pcr_trend", "change_oi_pcr_trend", "max_pain_trend"):
            if not isinstance(getattr(self, trend_name), OptionMetricTrend):
                raise TypeError(f"{trend_name} must be OptionMetricTrend")
        for migration_name in ("support_migration", "resistance_migration", "atm_migration"):
            if not isinstance(getattr(self, migration_name), OptionLevelMigration):
                raise TypeError(f"{migration_name} must be OptionLevelMigration")
        for name in ("previous_support", "current_support", "previous_resistance", "current_resistance", "previous_atm_strike", "current_atm_strike"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive_real(value, name))
        object.__setattr__(self, "bullish_score", _non_negative_int(self.bullish_score, "bullish_score"))
        object.__setattr__(self, "bearish_score", _non_negative_int(self.bearish_score, "bearish_score"))
        if not isinstance(self.bias, OptionAnalyticsBias):
            raise TypeError("bias must be OptionAnalyticsBias")
        rationale = tuple(self.rationale)
        for item in rationale:
            if not isinstance(item, str):
                raise TypeError("rationale must contain strings")
        object.__setattr__(self, "rationale", rationale)


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _positive_real(value: Real, name: str) -> float:
    number = _real(value, name)
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def _non_negative_real(value: Real, name: str) -> float:
    number = _real(value, name)
    if number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be integer")
    return value


def _non_negative_int(value: int, name: str) -> int:
    integer = _int(value, name)
    if integer < 0:
        raise ValueError(f"{name} must be non-negative")
    return integer
