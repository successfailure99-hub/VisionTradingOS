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

from .enums import (
    VisionBreakDirection,
    VisionCPRRelation,
    VisionCamarillaZone,
    VisionCandidateState,
    VisionGapType,
    VisionLevelQuality,
    VisionMarketRegime,
    VisionOpeningLocation,
    VisionOpeningRangeState,
    VisionPreviousDayRelation,
    VisionRangeLocation,
    VisionVWAPRelation,
)


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
    previous_day_relation: VisionPreviousDayRelation | None = None
    gap_type: VisionGapType | None = None

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
        if self.previous_day_relation is not None and not isinstance(self.previous_day_relation, VisionPreviousDayRelation):
            raise TypeError("previous_day_relation must be VisionPreviousDayRelation or None.")
        if self.gap_type is not None and not isinstance(self.gap_type, VisionGapType):
            raise TypeError("gap_type must be VisionGapType or None.")


@dataclass(frozen=True, slots=True)
class VisionCPRContext:
    relation: VisionCPRRelation
    bc: float
    tc: float
    pivot: float
    width: float
    width_percentage: float

    def __post_init__(self) -> None:
        if not isinstance(self.relation, VisionCPRRelation):
            raise TypeError("relation must be VisionCPRRelation.")
        for field_name in ("bc", "tc", "pivot", "width", "width_percentage"):
            object.__setattr__(self, field_name, _finite_number(getattr(self, field_name), field_name))


@dataclass(frozen=True, slots=True)
class VisionCamarillaContext:
    zone: VisionCamarillaZone
    h3: float
    h4: float
    h5: float
    h6: float
    l3: float
    l4: float
    l5: float
    l6: float

    def __post_init__(self) -> None:
        if not isinstance(self.zone, VisionCamarillaZone):
            raise TypeError("zone must be VisionCamarillaZone.")
        for field_name in ("h3", "h4", "h5", "h6", "l3", "l4", "l5", "l6"):
            object.__setattr__(self, field_name, _finite_number(getattr(self, field_name), field_name))


@dataclass(frozen=True, slots=True)
class VisionADRContext:
    range_consumed_pct: float
    range_remaining_pct: float
    near_adr_resistance: bool
    near_adr_support: bool
    expansion: str
    exhaustion: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "range_consumed_pct", _finite_number(self.range_consumed_pct, "range_consumed_pct"))
        object.__setattr__(self, "range_remaining_pct", _finite_number(self.range_remaining_pct, "range_remaining_pct"))
        if not isinstance(self.near_adr_resistance, bool):
            raise TypeError("near_adr_resistance must be bool.")
        if not isinstance(self.near_adr_support, bool):
            raise TypeError("near_adr_support must be bool.")
        object.__setattr__(self, "expansion", _normalize_text(self.expansion, "expansion"))
        object.__setattr__(self, "exhaustion", _normalize_text(self.exhaustion, "exhaustion"))


@dataclass(frozen=True, slots=True)
class VisionVWAPContext:
    relation: VisionVWAPRelation
    vwap: float
    distance: float
    distance_pct: float

    def __post_init__(self) -> None:
        if not isinstance(self.relation, VisionVWAPRelation):
            raise TypeError("relation must be VisionVWAPRelation.")
        object.__setattr__(self, "vwap", _positive_number(self.vwap, "vwap"))
        object.__setattr__(self, "distance", _finite_number(self.distance, "distance"))
        object.__setattr__(self, "distance_pct", _finite_number(self.distance_pct, "distance_pct"))


@dataclass(frozen=True, slots=True)
class VisionOpeningRangeContext:
    opening_start_time: datetime
    opening_end_time: datetime
    opening_high: float
    opening_low: float
    opening_width: float
    range_complete: bool
    current_location: VisionRangeLocation
    break_direction: VisionBreakDirection
    retest_state: VisionOpeningRangeState
    false_break: bool
    elapsed_minutes: int
    quality: VisionLevelQuality

    def __post_init__(self) -> None:
        _validate_aware(self.opening_start_time, "opening_start_time")
        _validate_aware(self.opening_end_time, "opening_end_time")
        if self.opening_end_time <= self.opening_start_time:
            raise ValueError("opening_end_time must be after opening_start_time.")
        high = _positive_number(self.opening_high, "opening_high")
        low = _positive_number(self.opening_low, "opening_low")
        if high < low:
            raise ValueError("opening_high cannot be below opening_low.")
        width = _finite_number(self.opening_width, "opening_width")
        if width != high - low:
            raise ValueError("opening_width must equal opening_high - opening_low.")
        if not isinstance(self.range_complete, bool):
            raise TypeError("range_complete must be bool.")
        if not isinstance(self.current_location, VisionRangeLocation):
            raise TypeError("current_location must be VisionRangeLocation.")
        if not isinstance(self.break_direction, VisionBreakDirection):
            raise TypeError("break_direction must be VisionBreakDirection.")
        if not isinstance(self.retest_state, VisionOpeningRangeState):
            raise TypeError("retest_state must be VisionOpeningRangeState.")
        if not isinstance(self.false_break, bool):
            raise TypeError("false_break must be bool.")
        if isinstance(self.elapsed_minutes, bool) or not isinstance(self.elapsed_minutes, int):
            raise TypeError("elapsed_minutes must be int.")
        if self.elapsed_minutes < 0:
            raise ValueError("elapsed_minutes cannot be negative.")
        if not isinstance(self.quality, VisionLevelQuality):
            raise TypeError("quality must be VisionLevelQuality.")
        object.__setattr__(self, "opening_high", high)
        object.__setattr__(self, "opening_low", low)


@dataclass(frozen=True, slots=True)
class VisionLevelContext:
    cpr_context: VisionCPRContext
    camarilla_context: VisionCamarillaContext
    previous_day_context: VisionPreviousDayContext
    adr_context: VisionADRContext | None
    vwap_context: VisionVWAPContext | None
    quality: VisionLevelQuality
    missing_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.cpr_context, VisionCPRContext):
            raise TypeError("cpr_context must be VisionCPRContext.")
        if not isinstance(self.camarilla_context, VisionCamarillaContext):
            raise TypeError("camarilla_context must be VisionCamarillaContext.")
        if not isinstance(self.previous_day_context, VisionPreviousDayContext):
            raise TypeError("previous_day_context must be VisionPreviousDayContext.")
        if self.adr_context is not None and not isinstance(self.adr_context, VisionADRContext):
            raise TypeError("adr_context must be VisionADRContext or None.")
        if self.vwap_context is not None and not isinstance(self.vwap_context, VisionVWAPContext):
            raise TypeError("vwap_context must be VisionVWAPContext or None.")
        if not isinstance(self.quality, VisionLevelQuality):
            raise TypeError("quality must be VisionLevelQuality.")
        object.__setattr__(self, "missing_evidence", _normalize_text_tuple(self.missing_evidence, "missing_evidence"))


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
