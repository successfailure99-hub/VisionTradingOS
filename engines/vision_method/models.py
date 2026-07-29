"""
Immutable Vision Method V1 model contracts.

VM-01 defines methodology contracts only. These models reference existing
evidence contexts without recalculating indicator values or producing trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame

from .enums import VisionCandidateState, VisionMarketRegime, VisionOpeningLocation


@dataclass(frozen=True, slots=True)
class VisionOpeningContext:
    opening_location: VisionOpeningLocation
    opening_price: float
    cpr_relation: str
    camarilla_relation: str
    gap_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.opening_location, VisionOpeningLocation):
            raise TypeError("opening_location must be VisionOpeningLocation.")
        object.__setattr__(self, "opening_price", _positive_number(self.opening_price, "opening_price"))
        object.__setattr__(self, "cpr_relation", _normalize_text(self.cpr_relation, "cpr_relation"))
        object.__setattr__(self, "camarilla_relation", _normalize_text(self.camarilla_relation, "camarilla_relation"))
        object.__setattr__(self, "gap_type", _normalize_text(self.gap_type, "gap_type"))


@dataclass(frozen=True, slots=True)
class VisionPreviousDayContext:
    previous_high: float
    previous_low: float
    previous_close: float
    virgin_cpr: bool
    distance_previous_high: float
    distance_previous_low: float

    def __post_init__(self) -> None:
        high = _positive_number(self.previous_high, "previous_high")
        low = _positive_number(self.previous_low, "previous_low")
        close = _positive_number(self.previous_close, "previous_close")
        if high < low:
            raise ValueError("previous_high cannot be below previous_low.")
        if close < low or close > high:
            raise ValueError("previous_close must be within the previous day range.")
        if not isinstance(self.virgin_cpr, bool):
            raise TypeError("virgin_cpr must be bool.")
        object.__setattr__(self, "previous_high", high)
        object.__setattr__(self, "previous_low", low)
        object.__setattr__(self, "previous_close", close)
        object.__setattr__(self, "distance_previous_high", _finite_number(self.distance_previous_high, "distance_previous_high"))
        object.__setattr__(self, "distance_previous_low", _finite_number(self.distance_previous_low, "distance_previous_low"))


@dataclass(frozen=True, slots=True)
class VisionLevelContext:
    cpr_context: object
    camarilla_context: object
    adr_context: object
    vwap_context: object

    def __post_init__(self) -> None:
        for field_name in ("cpr_context", "camarilla_context", "adr_context", "vwap_context"):
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} is required.")


@dataclass(frozen=True, slots=True)
class VisionMethodSnapshot:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    timestamp: datetime
    opening_context: VisionOpeningContext
    previous_day_context: VisionPreviousDayContext
    level_context: VisionLevelContext
    market_regime: VisionMarketRegime
    candidate_state: VisionCandidateState
    blocking_reasons: tuple[str, ...]
    supporting_reasons: tuple[str, ...]
    quality: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        _validate_aware(self.timestamp, "timestamp")
        if not isinstance(self.opening_context, VisionOpeningContext):
            raise TypeError("opening_context must be VisionOpeningContext.")
        if not isinstance(self.previous_day_context, VisionPreviousDayContext):
            raise TypeError("previous_day_context must be VisionPreviousDayContext.")
        if not isinstance(self.level_context, VisionLevelContext):
            raise TypeError("level_context must be VisionLevelContext.")
        if not isinstance(self.market_regime, VisionMarketRegime):
            raise TypeError("market_regime must be VisionMarketRegime.")
        if not isinstance(self.candidate_state, VisionCandidateState):
            raise TypeError("candidate_state must be VisionCandidateState.")
        object.__setattr__(self, "blocking_reasons", _normalize_text_tuple(self.blocking_reasons, "blocking_reasons"))
        object.__setattr__(self, "supporting_reasons", _normalize_text_tuple(self.supporting_reasons, "supporting_reasons"))
        object.__setattr__(self, "quality", _normalize_text(self.quality, "quality"))


def _normalize_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple.")
    return tuple(_normalize_text(item, field_name) for item in values)


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text.")
    return value.strip()


def _finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    normalized = float(value)
    if normalized != normalized or normalized in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite.")
    return normalized


def _positive_number(value: float, field_name: str) -> float:
    normalized = _finite_number(value, field_name)
    if normalized <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return normalized


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
