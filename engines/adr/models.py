"""
Immutable ADR Engine V1 models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from .enums import ADRExpansionState, ADRExhaustionState


@dataclass(frozen=True, slots=True)
class ADRSnapshot:
    trading_date: date
    instrument: str
    adr_period: int
    adr_value: float
    today_high: float
    today_low: float
    today_range: float
    adr_high: float
    adr_low: float
    range_consumed_pct: float
    range_remaining_pct: float
    expansion_state: ADRExpansionState
    exhaustion_state: ADRExhaustionState
    timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be a date.")
        if not isinstance(self.instrument, str) or not self.instrument.strip():
            raise ValueError("instrument must be non-empty text.")
        object.__setattr__(self, "instrument", self.instrument.strip().upper())
        if isinstance(self.adr_period, bool) or not isinstance(self.adr_period, int) or self.adr_period <= 0:
            raise ValueError("adr_period must be a positive integer.")
        for field_name in (
            "adr_value",
            "today_high",
            "today_low",
            "today_range",
            "adr_high",
            "adr_low",
            "range_consumed_pct",
            "range_remaining_pct",
        ):
            _validate_finite_number(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, float(getattr(self, field_name)))
        if self.adr_value <= 0:
            raise ValueError("adr_value must be greater than zero.")
        if self.today_high < self.today_low:
            raise ValueError("today_high must be greater than or equal to today_low.")
        if self.today_range < 0:
            raise ValueError("today_range must be non-negative.")
        if not isinstance(self.expansion_state, ADRExpansionState):
            raise TypeError("expansion_state must be ADRExpansionState.")
        if not isinstance(self.exhaustion_state, ADRExhaustionState):
            raise TypeError("exhaustion_state must be ADRExhaustionState.")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be datetime.")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class ADRRequest:
    trading_date: date
    instrument: str
    daily_history: tuple[object, ...]
    latest_price: float
    session_high: float
    session_low: float
    timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be a date.")
        if not isinstance(self.instrument, str) or not self.instrument.strip():
            raise ValueError("instrument must be non-empty text.")
        object.__setattr__(self, "instrument", self.instrument.strip().upper())
        object.__setattr__(self, "daily_history", tuple(self.daily_history))
        for field_name in ("latest_price", "session_high", "session_low"):
            value = getattr(self, field_name)
            _validate_finite_number(value, field_name)
            if float(value) <= 0:
                raise ValueError(f"{field_name} must be greater than zero.")
            object.__setattr__(self, field_name, float(value))
        if self.session_high < self.session_low:
            raise ValueError("session_high must be greater than or equal to session_low.")
        if not self.session_low <= self.latest_price <= self.session_high:
            raise ValueError("latest_price must be within the session range.")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be datetime.")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class ADRDiagnosticSnapshot:
    enabled: bool
    period: int
    calculation_count: int
    partial_count: int
    invalid_count: int
    last_snapshot: ADRSnapshot | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool.")
        for field_name in ("period", "calculation_count", "partial_count", "invalid_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")
        if self.period <= 0:
            raise ValueError("period must be positive.")
        if self.last_error is not None:
            if not isinstance(self.last_error, str):
                raise TypeError("last_error must be text or None.")
            object.__setattr__(self, "last_error", self.last_error.strip() or None)


def _validate_finite_number(value: Real, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a finite real number.")
    if not isfinite(float(value)):
        raise ValueError(f"{field_name} must be a finite real number.")

