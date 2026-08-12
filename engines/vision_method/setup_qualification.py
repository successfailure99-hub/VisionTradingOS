"""
Vision Method setup qualification.

VM-07 consumes existing immutable Vision Method contexts and answers only
whether a setup is worth evaluating further. It does not consume option-chain,
AI, strategy, risk, runtime, broker, or execution components.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame

from .enums import (
    VisionBOS,
    VisionBreakDirection,
    VisionBreakStrength,
    VisionCHoCH,
    VisionCPRRelation,
    VisionCamarillaZone,
    VisionLevelQuality,
    VisionLiquiditySweep,
    VisionOpeningRangeState,
    VisionRangeLocation,
    VisionSetupDirection,
    VisionSetupQuality,
    VisionSetupType,
    VisionStructureEventPhase,
    VisionStructurePattern,
    VisionStructureTrend,
    VisionVWAPRelation,
)
from .models import (
    VisionLevelContext,
    VisionLiquidityContext,
    VisionOpeningRangeContext,
    VisionSetupQualificationContext,
    VisionStructureContext,
    VisionStructureEventContext,
)


@dataclass(frozen=True, slots=True)
class VisionSetupQualificationRequest:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    timestamp: datetime
    level_context: VisionLevelContext
    opening_range_context: VisionOpeningRangeContext
    structure_context: VisionStructureContext
    liquidity_context: VisionLiquidityContext
    structure_event_context: VisionStructureEventContext

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        _validate_aware(self.timestamp, "timestamp")
        if not isinstance(self.level_context, VisionLevelContext):
            raise TypeError("level_context must be VisionLevelContext.")
        if not isinstance(self.opening_range_context, VisionOpeningRangeContext):
            raise TypeError("opening_range_context must be VisionOpeningRangeContext.")
        if not isinstance(self.structure_context, VisionStructureContext):
            raise TypeError("structure_context must be VisionStructureContext.")
        if not isinstance(self.liquidity_context, VisionLiquidityContext):
            raise TypeError("liquidity_context must be VisionLiquidityContext.")
        if not isinstance(self.structure_event_context, VisionStructureEventContext):
            raise TypeError("structure_event_context must be VisionStructureEventContext.")


def assemble_vision_setup_qualification_context(
    request: VisionSetupQualificationRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionSetupQualificationContext:
    """
    Qualify whether the existing Vision Method context deserves confirmation.
    """

    validate_setup_qualification_request(request, instrument=instrument, timeframe=timeframe)
    blocking = _blocking_reasons(request)
    supporting = _supporting_reasons(request)
    direction = _setup_direction(request)

    if blocking:
        result = VisionSetupQualificationContext(
            setup_type=VisionSetupType.NO_QUALITY_SETUP,
            setup_quality=VisionSetupQuality.INVALID,
            blocking_reasons=blocking,
            supporting_reasons=supporting,
            eligible_for_option_confirmation=False,
            setup_direction=VisionSetupDirection.UNKNOWN,
        )
        return validate_setup_qualification_context(result)

    setup_type = _classify_setup(request)
    direction = direction if setup_type is not VisionSetupType.NO_QUALITY_SETUP else VisionSetupDirection.UNKNOWN
    if setup_type is VisionSetupType.NO_QUALITY_SETUP:
        result = VisionSetupQualificationContext(
            setup_type=setup_type,
            setup_quality=VisionSetupQuality.LOW,
            blocking_reasons=_no_quality_blocking_reasons(request),
            supporting_reasons=supporting,
            eligible_for_option_confirmation=False,
            setup_direction=VisionSetupDirection.UNKNOWN,
        )
        return validate_setup_qualification_context(result)

    quality = _classify_quality(request, setup_type)
    result = VisionSetupQualificationContext(
        setup_type=setup_type,
        setup_quality=quality,
        blocking_reasons=(),
        supporting_reasons=supporting,
        eligible_for_option_confirmation=quality in (VisionSetupQuality.HIGH, VisionSetupQuality.MEDIUM),
        setup_direction=direction,
    )
    return validate_setup_qualification_context(result)


def validate_setup_qualification_request(
    request: VisionSetupQualificationRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionSetupQualificationRequest:
    if not isinstance(request, VisionSetupQualificationRequest):
        raise TypeError("request must be VisionSetupQualificationRequest.")
    expected_instrument = instrument or request.instrument
    expected_timeframe = timeframe or request.timeframe
    if request.instrument is not expected_instrument:
        raise ValueError("instrument mismatch.")
    if request.timeframe is not expected_timeframe:
        raise ValueError("timeframe mismatch.")
    if request.level_context.quality is VisionLevelQuality.INSUFFICIENT:
        raise ValueError("insufficient level context.")
    if request.opening_range_context.quality is VisionLevelQuality.INSUFFICIENT:
        raise ValueError("insufficient opening range context.")
    if request.structure_context.quality is VisionLevelQuality.INSUFFICIENT:
        raise ValueError("insufficient structure context.")
    if request.structure_event_context.quality is VisionLevelQuality.INSUFFICIENT:
        raise ValueError("insufficient structure event context.")
    return request


def validate_setup_qualification_context(context: VisionSetupQualificationContext) -> VisionSetupQualificationContext:
    if not isinstance(context, VisionSetupQualificationContext):
        raise TypeError("context must be VisionSetupQualificationContext.")
    return context


def _blocking_reasons(request: VisionSetupQualificationRequest) -> tuple[str, ...]:
    reasons: list[str] = []
    if not request.opening_range_context.range_complete:
        reasons.append("Opening range incomplete")
    if request.structure_context.trend is VisionStructureTrend.UNKNOWN:
        reasons.append("Conflicting structure")
    return _dedupe(reasons)


def _supporting_reasons(request: VisionSetupQualificationRequest) -> tuple[str, ...]:
    reasons: list[str] = []
    cpr = request.level_context.cpr_context.relation
    if cpr is VisionCPRRelation.ABOVE_CPR:
        reasons.append("Above CPR")
    elif cpr is VisionCPRRelation.BELOW_CPR:
        reasons.append("Below CPR")
    elif cpr is VisionCPRRelation.INSIDE_CPR:
        reasons.append("Inside CPR")

    zone = request.level_context.camarilla_context.zone
    if zone in (VisionCamarillaZone.H3_H4, VisionCamarillaZone.H4_H5, VisionCamarillaZone.H5_H6, VisionCamarillaZone.ABOVE_H6):
        reasons.append("Above H3")
    elif zone in (VisionCamarillaZone.L3_L4, VisionCamarillaZone.L4_L5, VisionCamarillaZone.L5_L6, VisionCamarillaZone.BELOW_L6):
        reasons.append("Below L3")

    if request.level_context.adr_context is not None:
        reasons.append(f"ADR only {request.level_context.adr_context.range_consumed_pct:.0f}% consumed")
    if _vwap_supportive(request):
        reasons.append("VWAP supportive")

    if request.structure_event_context.bos is VisionBOS.BULLISH_BOS:
        reasons.append("Bullish BOS")
    elif request.structure_event_context.bos is VisionBOS.BEARISH_BOS:
        reasons.append("Bearish BOS")
    elif request.structure_event_context.choch is VisionCHoCH.BULLISH_CHOCH:
        reasons.append("Bullish CHoCH")
    elif request.structure_event_context.choch is VisionCHoCH.BEARISH_CHOCH:
        reasons.append("Bearish CHoCH")

    if request.liquidity_context.liquidity_sweep is not VisionLiquiditySweep.NONE:
        reasons.append("Liquidity sweep completed")
    if request.opening_range_context.false_break:
        reasons.append("Opening range false break")
    elif request.opening_range_context.break_direction is not VisionBreakDirection.NONE:
        reasons.append("Opening range break")
    elif request.opening_range_context.current_location is VisionRangeLocation.INSIDE_RANGE:
        reasons.append("Inside opening range")
    return _dedupe(reasons)


def _no_quality_blocking_reasons(request: VisionSetupQualificationRequest) -> tuple[str, ...]:
    reasons: list[str] = []
    if request.structure_event_context.bos is VisionBOS.NONE and request.structure_event_context.choch is VisionCHoCH.NONE:
        reasons.append("No BOS")
    if request.structure_context.trend is VisionStructureTrend.RANGING and not _is_range_fade(request):
        reasons.append("Range unsuitable")
    if not reasons:
        reasons.append("No quality setup")
    return _dedupe(reasons)


def _classify_setup(request: VisionSetupQualificationRequest) -> VisionSetupType:
    if _is_failed_breakout(request):
        return VisionSetupType.FAILED_BREAKOUT
    if _is_liquidity_reversal(request):
        return VisionSetupType.LIQUIDITY_REVERSAL
    if _is_breakout(request):
        return VisionSetupType.BREAKOUT
    if _is_trend_continuation(request):
        return VisionSetupType.TREND_CONTINUATION
    if _is_pullback_continuation(request):
        return VisionSetupType.PULLBACK_CONTINUATION
    if _is_range_fade(request):
        return VisionSetupType.RANGE_FADE
    return VisionSetupType.NO_QUALITY_SETUP


def _classify_quality(request: VisionSetupQualificationRequest, setup_type: VisionSetupType) -> VisionSetupQuality:
    if setup_type in (VisionSetupType.BREAKOUT, VisionSetupType.TREND_CONTINUATION, VisionSetupType.LIQUIDITY_REVERSAL):
        if request.structure_event_context.break_strength is VisionBreakStrength.STRONG and request.level_context.quality is VisionLevelQuality.FULL:
            return VisionSetupQuality.HIGH
        return VisionSetupQuality.MEDIUM
    if setup_type in (VisionSetupType.PULLBACK_CONTINUATION, VisionSetupType.FAILED_BREAKOUT, VisionSetupType.RANGE_FADE):
        return VisionSetupQuality.MEDIUM
    return VisionSetupQuality.LOW


def _setup_direction(request: VisionSetupQualificationRequest) -> VisionSetupDirection:
    event = request.structure_event_context
    if event.bos is VisionBOS.BULLISH_BOS or event.choch is VisionCHoCH.BULLISH_CHOCH:
        return VisionSetupDirection.BULLISH
    if event.bos is VisionBOS.BEARISH_BOS or event.choch is VisionCHoCH.BEARISH_CHOCH:
        return VisionSetupDirection.BEARISH
    if request.opening_range_context.break_direction is VisionBreakDirection.UP:
        return VisionSetupDirection.BULLISH
    if request.opening_range_context.break_direction is VisionBreakDirection.DOWN:
        return VisionSetupDirection.BEARISH
    if request.structure_context.trend is VisionStructureTrend.BULLISH:
        return VisionSetupDirection.BULLISH
    if request.structure_context.trend is VisionStructureTrend.BEARISH:
        return VisionSetupDirection.BEARISH
    if request.structure_context.trend is VisionStructureTrend.RANGING:
        return VisionSetupDirection.NEUTRAL
    return VisionSetupDirection.UNKNOWN


def _is_trend_continuation(request: VisionSetupQualificationRequest) -> bool:
    return (
        request.structure_context.trend in (VisionStructureTrend.BULLISH, VisionStructureTrend.BEARISH)
        and request.structure_event_context.bos is not VisionBOS.NONE
        and request.structure_event_context.continuation is VisionStructureEventPhase.CONTINUATION
    )


def _is_pullback_continuation(request: VisionSetupQualificationRequest) -> bool:
    maintained_structure = request.structure_context.structure_state in (VisionStructurePattern.HL, VisionStructurePattern.LH)
    pullback_context = (
        request.opening_range_context.retest_state is VisionOpeningRangeState.RETEST
        or (request.level_context.vwap_context is not None and request.level_context.vwap_context.relation is VisionVWAPRelation.RETEST)
    )
    return (
        request.structure_context.trend in (VisionStructureTrend.BULLISH, VisionStructureTrend.BEARISH)
        and maintained_structure
        and pullback_context
        and request.structure_event_context.choch is VisionCHoCH.NONE
    )


def _is_breakout(request: VisionSetupQualificationRequest) -> bool:
    return (
        request.opening_range_context.break_direction is not VisionBreakDirection.NONE
        and request.opening_range_context.retest_state
        in (VisionOpeningRangeState.BREAK_ABOVE, VisionOpeningRangeState.BREAK_BELOW, VisionOpeningRangeState.RETEST)
        and not request.opening_range_context.false_break
        and request.structure_event_context.bos is not VisionBOS.NONE
    )


def _is_failed_breakout(request: VisionSetupQualificationRequest) -> bool:
    return request.opening_range_context.false_break or request.opening_range_context.retest_state is VisionOpeningRangeState.FALSE_BREAK


def _is_liquidity_reversal(request: VisionSetupQualificationRequest) -> bool:
    return request.liquidity_context.liquidity_sweep is not VisionLiquiditySweep.NONE and request.structure_event_context.choch is not VisionCHoCH.NONE


def _is_range_fade(request: VisionSetupQualificationRequest) -> bool:
    near_range_extreme = request.level_context.camarilla_context.zone in (
        VisionCamarillaZone.H3_H4,
        VisionCamarillaZone.H4_H5,
        VisionCamarillaZone.L3_L4,
        VisionCamarillaZone.L4_L5,
    )
    return (
        request.structure_context.trend is VisionStructureTrend.RANGING
        and request.opening_range_context.current_location is VisionRangeLocation.INSIDE_RANGE
        and near_range_extreme
        and request.structure_event_context.bos is VisionBOS.NONE
    )


def _vwap_supportive(request: VisionSetupQualificationRequest) -> bool:
    context = request.level_context.vwap_context
    if context is None:
        return False
    return context.relation in (
        VisionVWAPRelation.ABOVE_VWAP,
        VisionVWAPRelation.BELOW_VWAP,
        VisionVWAPRelation.CROSS_ABOVE,
        VisionVWAPRelation.CROSS_BELOW,
        VisionVWAPRelation.RETEST,
        VisionVWAPRelation.REJECT,
    )


def _dedupe(values: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            result.append(value)
            seen.add(key)
    return tuple(result)


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
