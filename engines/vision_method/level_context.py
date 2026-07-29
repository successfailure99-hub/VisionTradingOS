"""
Vision Method V1 level-context assembly.

This module consumes existing immutable level snapshots and classifies their
relationship to price. It does not recalculate indicator formulas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from application.enums import RuntimeInstrument
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.daily_ohlc import DailyOHLC
from engines.adr.models import ADRSnapshot
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.vwap.levels import VWAPLevels

from .enums import (
    VisionCPRRelation,
    VisionCamarillaZone,
    VisionGapType,
    VisionLevelQuality,
    VisionPreviousDayRelation,
    VisionVWAPRelation,
)
from .models import (
    VisionADRContext,
    VisionCPRContext,
    VisionCamarillaContext,
    VisionLevelContext,
    VisionPreviousDayContext,
    VisionVWAPContext,
)


@dataclass(frozen=True, slots=True)
class VisionLevelContextRequest:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    trading_date: date
    timestamp: datetime
    latest_price: float
    opening_price: float
    previous_day: DailyOHLC
    cpr: CPRLevels
    camarilla: CamarillaLevels
    adr: ADRSnapshot | None = None
    vwap: VWAPLevels | None = None
    previous_price: float | None = None
    virgin_cpr: bool = False
    vwap_rejected: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be a date.")
        _validate_aware(self.timestamp, "timestamp")
        object.__setattr__(self, "latest_price", _positive_number(self.latest_price, "latest_price"))
        object.__setattr__(self, "opening_price", _positive_number(self.opening_price, "opening_price"))
        if not isinstance(self.previous_day, DailyOHLC):
            raise TypeError("previous_day must be DailyOHLC.")
        if not isinstance(self.cpr, CPRLevels):
            raise TypeError("cpr must be CPRLevels.")
        if not isinstance(self.camarilla, CamarillaLevels):
            raise TypeError("camarilla must be CamarillaLevels.")
        if self.adr is not None and not isinstance(self.adr, ADRSnapshot):
            raise TypeError("adr must be ADRSnapshot or None.")
        if self.vwap is not None and not isinstance(self.vwap, VWAPLevels):
            raise TypeError("vwap must be VWAPLevels or None.")
        if self.previous_price is not None:
            object.__setattr__(self, "previous_price", _positive_number(self.previous_price, "previous_price"))
        if not isinstance(self.virgin_cpr, bool):
            raise TypeError("virgin_cpr must be bool.")
        if not isinstance(self.vwap_rejected, bool):
            raise TypeError("vwap_rejected must be bool.")


def assemble_vision_level_context(
    request: VisionLevelContextRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
    max_snapshot_age: timedelta = timedelta(minutes=5),
) -> VisionLevelContext:
    validate_level_context_request(
        request,
        instrument=instrument,
        timeframe=timeframe,
        max_snapshot_age=max_snapshot_age,
    )
    missing = []
    adr_context = None if request.adr is None else _adr_context(request)
    vwap_context = None if request.vwap is None else _vwap_context(request)
    if adr_context is None:
        missing.append("adr")
    if vwap_context is None:
        missing.append("vwap")
    quality = VisionLevelQuality.FULL if not missing else VisionLevelQuality.PARTIAL
    return VisionLevelContext(
        cpr_context=_cpr_context(request),
        camarilla_context=_camarilla_context(request),
        previous_day_context=_previous_day_context(request),
        adr_context=adr_context,
        vwap_context=vwap_context,
        quality=quality,
        missing_evidence=tuple(missing),
    )


def validate_level_context_request(
    request: VisionLevelContextRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
    max_snapshot_age: timedelta = timedelta(minutes=5),
) -> VisionLevelContextRequest:
    if not isinstance(request, VisionLevelContextRequest):
        raise TypeError("request must be VisionLevelContextRequest.")
    if instrument is not None and request.instrument is not instrument:
        raise ValueError("instrument mismatch.")
    if timeframe is not None and request.timeframe is not timeframe:
        raise ValueError("timeframe mismatch.")
    if not isinstance(max_snapshot_age, timedelta) or max_snapshot_age.total_seconds() < 0:
        raise ValueError("max_snapshot_age must be a non-negative timedelta.")
    _validate_required_dates(request)
    _validate_optional_snapshot_identity_and_freshness(request, max_snapshot_age)
    return request


def _cpr_context(request: VisionLevelContextRequest) -> VisionCPRContext:
    lower = min(request.cpr.bc, request.cpr.tc)
    upper = max(request.cpr.bc, request.cpr.tc)
    if request.latest_price > upper:
        relation = VisionCPRRelation.ABOVE_CPR
    elif request.latest_price < lower:
        relation = VisionCPRRelation.BELOW_CPR
    else:
        relation = VisionCPRRelation.INSIDE_CPR
    return VisionCPRContext(
        relation=relation,
        bc=request.cpr.bc,
        tc=request.cpr.tc,
        pivot=request.cpr.pivot,
        width=request.cpr.width,
        width_percentage=request.cpr.width_percentage,
    )


def _camarilla_context(request: VisionLevelContextRequest) -> VisionCamarillaContext:
    price = request.latest_price
    levels = request.camarilla
    if price > levels.h6:
        zone = VisionCamarillaZone.ABOVE_H6
    elif price >= levels.h5:
        zone = VisionCamarillaZone.H5_H6
    elif price >= levels.h4:
        zone = VisionCamarillaZone.H4_H5
    elif price >= levels.h3:
        zone = VisionCamarillaZone.H3_H4
    elif price >= levels.l3:
        zone = VisionCamarillaZone.INSIDE_VALUE
    elif price >= levels.l4:
        zone = VisionCamarillaZone.L3_L4
    elif price >= levels.l5:
        zone = VisionCamarillaZone.L4_L5
    elif price >= levels.l6:
        zone = VisionCamarillaZone.L5_L6
    else:
        zone = VisionCamarillaZone.BELOW_L6
    return VisionCamarillaContext(zone, levels.h3, levels.h4, levels.h5, levels.h6, levels.l3, levels.l4, levels.l5, levels.l6)


def _previous_day_context(request: VisionLevelContextRequest) -> VisionPreviousDayContext:
    previous = request.previous_day
    if request.latest_price > previous.high:
        relation = VisionPreviousDayRelation.ABOVE_PREVIOUS_HIGH
    elif request.latest_price < previous.low:
        relation = VisionPreviousDayRelation.BELOW_PREVIOUS_LOW
    else:
        relation = VisionPreviousDayRelation.INSIDE_PREVIOUS_RANGE
    if request.opening_price > previous.high:
        gap = VisionGapType.GAP_UP
    elif request.opening_price < previous.low:
        gap = VisionGapType.GAP_DOWN
    else:
        gap = VisionGapType.NO_GAP
    return VisionPreviousDayContext(
        previous_high=previous.high,
        previous_low=previous.low,
        previous_close=previous.close,
        virgin_cpr=request.virgin_cpr,
        distance_previous_high=request.latest_price - previous.high,
        distance_previous_low=request.latest_price - previous.low,
        previous_day_relation=relation,
        gap_type=gap,
    )


def _adr_context(request: VisionLevelContextRequest) -> VisionADRContext:
    assert request.adr is not None
    proximity = request.adr.adr_value * 0.1
    return VisionADRContext(
        range_consumed_pct=request.adr.range_consumed_pct,
        range_remaining_pct=request.adr.range_remaining_pct,
        near_adr_resistance=abs(request.adr.adr_high - request.latest_price) <= proximity,
        near_adr_support=abs(request.latest_price - request.adr.adr_low) <= proximity,
        expansion=request.adr.expansion_state.value,
        exhaustion=request.adr.exhaustion_state.value,
    )


def _vwap_context(request: VisionLevelContextRequest) -> VisionVWAPContext:
    assert request.vwap is not None
    distance = request.latest_price - request.vwap.vwap
    distance_pct = 0.0 if request.vwap.vwap == 0 else (distance / request.vwap.vwap) * 100.0
    abs_pct = abs(distance_pct)
    if request.vwap_rejected:
        relation = VisionVWAPRelation.REJECT
    elif request.previous_price is not None and request.previous_price <= request.vwap.vwap < request.latest_price:
        relation = VisionVWAPRelation.CROSS_ABOVE
    elif request.previous_price is not None and request.previous_price >= request.vwap.vwap > request.latest_price:
        relation = VisionVWAPRelation.CROSS_BELOW
    elif abs_pct <= 0.05:
        relation = VisionVWAPRelation.RETEST
    elif distance_pct >= 0.5:
        relation = VisionVWAPRelation.FAR_ABOVE
    elif distance_pct <= -0.5:
        relation = VisionVWAPRelation.FAR_BELOW
    elif distance > 0:
        relation = VisionVWAPRelation.ABOVE_VWAP
    else:
        relation = VisionVWAPRelation.BELOW_VWAP
    return VisionVWAPContext(relation, request.vwap.vwap, distance, distance_pct)


def _validate_required_dates(request: VisionLevelContextRequest) -> None:
    if request.cpr.trading_date != request.trading_date:
        raise ValueError("cpr trading date mismatch.")
    if request.camarilla.trading_date != request.trading_date:
        raise ValueError("camarilla trading date mismatch.")
    if request.previous_day.trading_date >= request.trading_date:
        raise ValueError("previous_day must be before trading_date.")


def _validate_optional_snapshot_identity_and_freshness(
    request: VisionLevelContextRequest,
    max_snapshot_age: timedelta,
) -> None:
    if request.adr is not None:
        if request.adr.instrument != request.instrument.value:
            raise ValueError("adr instrument mismatch.")
        _validate_snapshot_time(request.timestamp, request.adr.timestamp, "adr", max_snapshot_age)
        if request.adr.trading_date != request.trading_date:
            raise ValueError("adr trading date mismatch.")
    if request.vwap is not None:
        if _instrument_to_runtime(request.vwap.symbol) is not request.instrument:
            raise ValueError("vwap instrument mismatch.")
        _validate_snapshot_time(request.timestamp, request.vwap.timestamp, "vwap", max_snapshot_age)
        if request.vwap.trading_date != request.trading_date:
            raise ValueError("vwap trading date mismatch.")


def _validate_snapshot_time(
    request_timestamp: datetime,
    snapshot_timestamp: datetime,
    field_name: str,
    max_snapshot_age: timedelta,
) -> None:
    _validate_aware(snapshot_timestamp, f"{field_name}.timestamp")
    if snapshot_timestamp.utcoffset() != request_timestamp.utcoffset():
        raise ValueError(f"{field_name} timezone mismatch.")
    if snapshot_timestamp > request_timestamp:
        raise ValueError(f"{field_name} snapshot cannot be in the future.")
    if request_timestamp - snapshot_timestamp > max_snapshot_age:
        raise ValueError(f"{field_name} snapshot is stale.")


def _instrument_to_runtime(instrument: Instrument) -> RuntimeInstrument:
    if not isinstance(instrument, Instrument):
        raise TypeError("vwap symbol must be Instrument.")
    return RuntimeInstrument(instrument.value)


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


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
