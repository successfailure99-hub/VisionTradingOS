"""
Immutable Moving Average Context Engine V1 models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from .enums import (
    MovingAverageAlignment,
    MovingAverageCompressionState,
    MovingAverageExpansionState,
    MovingAverageSlope,
)


DEFAULT_EMA_PERIODS = (20, 50, 200)


@dataclass(frozen=True, slots=True)
class MovingAverageContextProfile:
    periods: tuple[int, ...] = DEFAULT_EMA_PERIODS

    def __post_init__(self) -> None:
        periods = tuple(self.periods)
        if not periods:
            raise ValueError("periods must be non-empty.")
        normalized = []
        for period in periods:
            if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
                raise ValueError("periods must contain positive integers.")
            if period not in normalized:
                normalized.append(period)
        for required in DEFAULT_EMA_PERIODS:
            if required not in normalized:
                raise ValueError("Moving Average Context V1 requires EMA 20, EMA 50 and EMA 200.")
        object.__setattr__(self, "periods", tuple(sorted(normalized)))


@dataclass(frozen=True, slots=True)
class MovingAverageValue:
    name: str
    period: int
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be non-empty text.")
        object.__setattr__(self, "name", self.name.strip().upper())
        if isinstance(self.period, bool) or not isinstance(self.period, int) or self.period <= 0:
            raise ValueError("period must be a positive integer.")
        _validate_finite_number(self.value, "value")
        object.__setattr__(self, "value", float(self.value))


@dataclass(frozen=True, slots=True)
class MovingAverageContextSnapshot:
    trading_date: date
    instrument: str
    timeframe: str
    ema20: float
    ema50: float
    ema200: float
    price_above_ema20: bool
    price_above_ema50: bool
    price_above_ema200: bool
    ema_alignment: MovingAverageAlignment
    ema_slope: MovingAverageSlope
    compression_state: MovingAverageCompressionState
    expansion_state: MovingAverageExpansionState
    timestamp: datetime
    ema_values: tuple[MovingAverageValue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be a date.")
        if not isinstance(self.instrument, str) or not self.instrument.strip():
            raise ValueError("instrument must be non-empty text.")
        object.__setattr__(self, "instrument", self.instrument.strip().upper())
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must be non-empty text.")
        object.__setattr__(self, "timeframe", self.timeframe.strip())
        for field_name in ("ema20", "ema50", "ema200"):
            _validate_finite_number(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, float(getattr(self, field_name)))
        for field_name in ("price_above_ema20", "price_above_ema50", "price_above_ema200"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be bool.")
        if not isinstance(self.ema_alignment, MovingAverageAlignment):
            raise TypeError("ema_alignment must be MovingAverageAlignment.")
        if not isinstance(self.ema_slope, MovingAverageSlope):
            raise TypeError("ema_slope must be MovingAverageSlope.")
        if not isinstance(self.compression_state, MovingAverageCompressionState):
            raise TypeError("compression_state must be MovingAverageCompressionState.")
        if not isinstance(self.expansion_state, MovingAverageExpansionState):
            raise TypeError("expansion_state must be MovingAverageExpansionState.")
        _validate_aware(self.timestamp, "timestamp")
        object.__setattr__(self, "ema_values", tuple(self.ema_values))
        for item in self.ema_values:
            if not isinstance(item, MovingAverageValue):
                raise TypeError("ema_values must contain MovingAverageValue values.")


@dataclass(frozen=True, slots=True)
class MovingAverageContextDiagnosticSnapshot:
    enabled: bool
    periods: tuple[int, ...]
    calculation_count: int
    partial_count: int
    invalid_count: int
    failed_count: int
    last_snapshot: MovingAverageContextSnapshot | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool.")
        object.__setattr__(self, "periods", tuple(self.periods))
        for period in self.periods:
            if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
                raise ValueError("periods must contain positive integers.")
        for field_name in ("calculation_count", "partial_count", "invalid_count", "failed_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")
        if self.last_error is not None:
            if not isinstance(self.last_error, str):
                raise TypeError("last_error must be text or None.")
            object.__setattr__(self, "last_error", self.last_error.strip() or None)


def _validate_finite_number(value: Real, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a finite real number.")
    if not isfinite(float(value)):
        raise ValueError(f"{field_name} must be a finite real number.")


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
