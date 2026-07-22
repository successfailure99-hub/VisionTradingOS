"""
Immutable Momentum Context Engine V1 models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from .enums import (
    MomentumAcceleration,
    MomentumDirection,
    MomentumState,
    MomentumStrength,
)


DEFAULT_MOMENTUM_PERIOD = 14


@dataclass(frozen=True, slots=True)
class MomentumContextProfile:
    period: int = DEFAULT_MOMENTUM_PERIOD
    flat_threshold: float = 0.01
    weak_threshold_pct: float = 0.10
    strong_threshold_pct: float = 0.75
    extreme_threshold_pct: float = 1.50

    def __post_init__(self) -> None:
        if isinstance(self.period, bool) or not isinstance(self.period, int) or self.period <= 0:
            raise ValueError("period must be a positive integer.")
        for field_name in (
            "flat_threshold",
            "weak_threshold_pct",
            "strong_threshold_pct",
            "extreme_threshold_pct",
        ):
            _validate_finite_number(getattr(self, field_name), field_name)
            if float(getattr(self, field_name)) < 0:
                raise ValueError(f"{field_name} must be non-negative.")
            object.__setattr__(self, field_name, float(getattr(self, field_name)))
        if not self.weak_threshold_pct < self.strong_threshold_pct < self.extreme_threshold_pct:
            raise ValueError("momentum strength thresholds must be increasing.")


@dataclass(frozen=True, slots=True)
class MomentumContextSnapshot:
    trading_date: date
    instrument: str
    timeframe: str
    momentum_period: int
    momentum_value: float
    momentum_direction: MomentumDirection
    momentum_strength: MomentumStrength
    momentum_acceleration: MomentumAcceleration
    momentum_state: MomentumState
    timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be a date.")
        if not isinstance(self.instrument, str) or not self.instrument.strip():
            raise ValueError("instrument must be non-empty text.")
        object.__setattr__(self, "instrument", self.instrument.strip().upper())
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must be non-empty text.")
        object.__setattr__(self, "timeframe", self.timeframe.strip())
        if isinstance(self.momentum_period, bool) or not isinstance(self.momentum_period, int) or self.momentum_period <= 0:
            raise ValueError("momentum_period must be a positive integer.")
        _validate_finite_number(self.momentum_value, "momentum_value")
        object.__setattr__(self, "momentum_value", float(self.momentum_value))
        if not isinstance(self.momentum_direction, MomentumDirection):
            raise TypeError("momentum_direction must be MomentumDirection.")
        if not isinstance(self.momentum_strength, MomentumStrength):
            raise TypeError("momentum_strength must be MomentumStrength.")
        if not isinstance(self.momentum_acceleration, MomentumAcceleration):
            raise TypeError("momentum_acceleration must be MomentumAcceleration.")
        if not isinstance(self.momentum_state, MomentumState):
            raise TypeError("momentum_state must be MomentumState.")
        _validate_aware(self.timestamp, "timestamp")


@dataclass(frozen=True, slots=True)
class MomentumContextDiagnosticSnapshot:
    enabled: bool
    period: int
    calculation_count: int
    partial_count: int
    invalid_count: int
    failed_count: int
    last_snapshot: MomentumContextSnapshot | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool.")
        if isinstance(self.period, bool) or not isinstance(self.period, int) or self.period <= 0:
            raise ValueError("period must be a positive integer.")
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
