"""
Immutable Volume Context Engine V1 models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from .enums import (
    VolumeDirection,
    VolumeExhaustionState,
    VolumeExpansionState,
    VolumeStrength,
)


DEFAULT_VOLUME_LOOKBACK = 20


@dataclass(frozen=True, slots=True)
class VolumeContextProfile:
    lookback: int = DEFAULT_VOLUME_LOOKBACK
    stable_threshold_pct: float = 5.0
    low_rvol_threshold: float = 0.75
    high_rvol_threshold: float = 1.50
    extreme_rvol_threshold: float = 2.50

    def __post_init__(self) -> None:
        if isinstance(self.lookback, bool) or not isinstance(self.lookback, int) or self.lookback <= 0:
            raise ValueError("lookback must be a positive integer.")
        for field_name in (
            "stable_threshold_pct",
            "low_rvol_threshold",
            "high_rvol_threshold",
            "extreme_rvol_threshold",
        ):
            _validate_finite_number(getattr(self, field_name), field_name)
            if float(getattr(self, field_name)) < 0:
                raise ValueError(f"{field_name} must be non-negative.")
            object.__setattr__(self, field_name, float(getattr(self, field_name)))
        if not self.low_rvol_threshold < self.high_rvol_threshold < self.extreme_rvol_threshold:
            raise ValueError("volume RVOL thresholds must be increasing.")


@dataclass(frozen=True, slots=True)
class VolumeContextSnapshot:
    trading_date: date
    instrument: str
    timeframe: str
    lookback: int
    average_volume: float
    current_volume: int
    relative_volume: float
    volume_direction: VolumeDirection
    volume_strength: VolumeStrength
    volume_expansion_state: VolumeExpansionState
    volume_exhaustion_state: VolumeExhaustionState
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
        if isinstance(self.lookback, bool) or not isinstance(self.lookback, int) or self.lookback <= 0:
            raise ValueError("lookback must be a positive integer.")
        _validate_finite_number(self.average_volume, "average_volume")
        if float(self.average_volume) <= 0:
            raise ValueError("average_volume must be greater than zero.")
        object.__setattr__(self, "average_volume", float(self.average_volume))
        if isinstance(self.current_volume, bool) or not isinstance(self.current_volume, int) or self.current_volume < 0:
            raise ValueError("current_volume must be a non-negative integer.")
        _validate_finite_number(self.relative_volume, "relative_volume")
        if float(self.relative_volume) < 0:
            raise ValueError("relative_volume must be non-negative.")
        object.__setattr__(self, "relative_volume", float(self.relative_volume))
        if not isinstance(self.volume_direction, VolumeDirection):
            raise TypeError("volume_direction must be VolumeDirection.")
        if not isinstance(self.volume_strength, VolumeStrength):
            raise TypeError("volume_strength must be VolumeStrength.")
        if not isinstance(self.volume_expansion_state, VolumeExpansionState):
            raise TypeError("volume_expansion_state must be VolumeExpansionState.")
        if not isinstance(self.volume_exhaustion_state, VolumeExhaustionState):
            raise TypeError("volume_exhaustion_state must be VolumeExhaustionState.")
        _validate_aware(self.timestamp, "timestamp")


@dataclass(frozen=True, slots=True)
class VolumeContextDiagnosticSnapshot:
    enabled: bool
    lookback: int
    calculation_count: int
    partial_count: int
    invalid_count: int
    failed_count: int
    last_snapshot: VolumeContextSnapshot | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool.")
        if isinstance(self.lookback, bool) or not isinstance(self.lookback, int) or self.lookback <= 0:
            raise ValueError("lookback must be a positive integer.")
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
