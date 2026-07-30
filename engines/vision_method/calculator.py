"""
Vision Method Calculator V1.

VM-09 assembles existing immutable Vision Method contexts into one methodology
snapshot. It does not calculate indicators or generate trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame

from .enums import (
    VisionBOS,
    VisionCHoCH,
    VisionCPRRelation,
    VisionCandidateState,
    VisionCamarillaZone,
    VisionLevelQuality,
    VisionMarketRegime,
    VisionOpeningLocation,
    VisionOpeningRangeState,
    VisionOptionConfirmation,
    VisionSetupQuality,
    VisionSetupType,
    VisionStructureEventPhase,
    VisionStructurePattern,
    VisionStructureTrend,
)
from .models import (
    VisionLevelContext,
    VisionLiquidityContext,
    VisionMethodSnapshot,
    VisionOpeningContext,
    VisionOpeningRangeContext,
    VisionOptionConfirmationContext,
    VisionPreviousDayContext,
    VisionSetupQualificationContext,
    VisionStructureContext,
    VisionStructureEventContext,
)
from .validator import validate_vision_method_snapshot


@dataclass(frozen=True, slots=True)
class VisionMethodCalculationRequest:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    timestamp: datetime
    level_context: VisionLevelContext
    opening_range_context: VisionOpeningRangeContext
    structure_context: VisionStructureContext
    liquidity_context: VisionLiquidityContext
    structure_event_context: VisionStructureEventContext
    setup_qualification_context: VisionSetupQualificationContext
    option_confirmation_context: VisionOptionConfirmationContext

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
        if not isinstance(self.setup_qualification_context, VisionSetupQualificationContext):
            raise TypeError("setup_qualification_context must be VisionSetupQualificationContext.")
        if not isinstance(self.option_confirmation_context, VisionOptionConfirmationContext):
            raise TypeError("option_confirmation_context must be VisionOptionConfirmationContext.")


def calculate_vision_method_snapshot(
    request: VisionMethodCalculationRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionMethodSnapshot:
    """
    Assemble one deterministic Vision Method snapshot from existing contexts.
    """

    validate_vision_method_calculation_request(request, instrument=instrument, timeframe=timeframe)
    blocking_reasons = _blocking_reasons(request)
    supporting_reasons = _supporting_reasons(request)
    candidate_state = _candidate_state(request, blocking_reasons)
    quality = _method_quality(request, candidate_state, blocking_reasons)

    snapshot = VisionMethodSnapshot(
        instrument=request.instrument,
        timeframe=request.timeframe,
        timestamp=request.timestamp,
        opening_context=_opening_context(request),
        previous_day_context=request.level_context.previous_day_context,
        level_context=request.level_context,
        opening_range_context=request.opening_range_context,
        structure_context=request.structure_context,
        liquidity_context=request.liquidity_context,
        structure_event_context=request.structure_event_context,
        setup_qualification_context=request.setup_qualification_context,
        option_confirmation_context=request.option_confirmation_context,
        market_regime=_market_regime(request),
        candidate_state=candidate_state,
        blocking_reasons=blocking_reasons,
        supporting_reasons=supporting_reasons,
        quality=quality,
    )
    return validate_vision_method_snapshot(snapshot, instrument=request.instrument, timeframe=request.timeframe)


def validate_vision_method_calculation_request(
    request: VisionMethodCalculationRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionMethodCalculationRequest:
    if not isinstance(request, VisionMethodCalculationRequest):
        raise TypeError("request must be VisionMethodCalculationRequest.")
    expected_instrument = instrument or request.instrument
    expected_timeframe = timeframe or request.timeframe
    if request.instrument is not expected_instrument:
        raise ValueError("instrument mismatch.")
    if request.timeframe is not expected_timeframe:
        raise ValueError("timeframe mismatch.")
    if request.opening_range_context.opening_end_time > request.timestamp:
        raise ValueError("timestamp inconsistency.")
    if request.option_confirmation_context.timestamp > request.timestamp:
        raise ValueError("timestamp inconsistency.")
    if request.timestamp.utcoffset() != request.opening_range_context.opening_start_time.utcoffset():
        raise ValueError("timezone mismatch.")
    if request.timestamp.utcoffset() != request.option_confirmation_context.timestamp.utcoffset():
        raise ValueError("timezone mismatch.")
    return request


def _opening_context(request: VisionMethodCalculationRequest) -> VisionOpeningContext:
    cpr_relation = request.level_context.cpr_context.relation
    if cpr_relation is VisionCPRRelation.ABOVE_CPR:
        opening_location = VisionOpeningLocation.ABOVE_CPR
    elif cpr_relation is VisionCPRRelation.BELOW_CPR:
        opening_location = VisionOpeningLocation.BELOW_CPR
    else:
        opening_location = VisionOpeningLocation.INSIDE_CPR
    previous = request.level_context.previous_day_context
    return VisionOpeningContext(
        opening_location=opening_location,
        opening_price=request.opening_range_context.opening_high,
        cpr_relation=cpr_relation.value,
        camarilla_relation=request.level_context.camarilla_context.zone.value,
        gap_type=previous.gap_type.value if previous.gap_type is not None else "unknown",
    )


def _market_regime(request: VisionMethodCalculationRequest) -> VisionMarketRegime:
    setup = request.setup_qualification_context.setup_type
    structure = request.structure_context
    event = request.structure_event_context
    if setup in (VisionSetupType.BREAKOUT, VisionSetupType.TREND_CONTINUATION):
        return VisionMarketRegime.TREND_DAY
    if setup is VisionSetupType.RANGE_FADE or structure.trend is VisionStructureTrend.RANGING:
        return VisionMarketRegime.RANGE_DAY
    if setup is VisionSetupType.FAILED_BREAKOUT:
        return VisionMarketRegime.TRANSITION_DAY
    if setup is VisionSetupType.LIQUIDITY_REVERSAL or event.choch is not VisionCHoCH.NONE:
        return VisionMarketRegime.REVERSAL_DAY
    if request.opening_range_context.retest_state in (VisionOpeningRangeState.BREAK_ABOVE, VisionOpeningRangeState.BREAK_BELOW):
        return VisionMarketRegime.EXPANSION_DAY
    if request.level_context.quality is VisionLevelQuality.PARTIAL:
        return VisionMarketRegime.COMPRESSION_DAY
    return VisionMarketRegime.UNKNOWN


def _candidate_state(request: VisionMethodCalculationRequest, blocking_reasons: tuple[str, ...]) -> VisionCandidateState:
    if _has_insufficient_data(request):
        return VisionCandidateState.INSUFFICIENT_DATA
    if not request.opening_range_context.range_complete:
        return VisionCandidateState.WAIT
    if blocking_reasons or request.setup_qualification_context.setup_quality is VisionSetupQuality.INVALID:
        return VisionCandidateState.AVOID

    direction = _setup_direction(request.setup_qualification_context)
    confirmation = request.option_confirmation_context.confirmation_state
    if direction == "bullish":
        if confirmation is VisionOptionConfirmation.CONFIRMS:
            return VisionCandidateState.LONG_ELIGIBLE
        if confirmation in (VisionOptionConfirmation.PARTIAL, VisionOptionConfirmation.NEUTRAL):
            return VisionCandidateState.PREPARE_LONG
    if direction == "bearish":
        if confirmation is VisionOptionConfirmation.CONFIRMS:
            return VisionCandidateState.SHORT_ELIGIBLE
        if confirmation in (VisionOptionConfirmation.PARTIAL, VisionOptionConfirmation.NEUTRAL):
            return VisionCandidateState.PREPARE_SHORT
    if request.setup_qualification_context.eligible_for_option_confirmation:
        return VisionCandidateState.OBSERVE
    return VisionCandidateState.AVOID


def _method_quality(
    request: VisionMethodCalculationRequest,
    candidate_state: VisionCandidateState,
    blocking_reasons: tuple[str, ...],
) -> str:
    if candidate_state is VisionCandidateState.INSUFFICIENT_DATA:
        return "invalid"
    if blocking_reasons or candidate_state is VisionCandidateState.AVOID:
        return "invalid"
    if (
        request.level_context.quality is VisionLevelQuality.FULL
        and request.opening_range_context.quality is VisionLevelQuality.FULL
        and request.structure_context.quality is VisionLevelQuality.FULL
        and request.liquidity_context.quality is VisionLevelQuality.FULL
        and request.structure_event_context.quality is VisionLevelQuality.FULL
        and request.option_confirmation_context.quality is VisionLevelQuality.FULL
        and request.setup_qualification_context.setup_quality is VisionSetupQuality.HIGH
        and request.option_confirmation_context.confirmation_state is VisionOptionConfirmation.CONFIRMS
    ):
        return "high"
    if (
        request.option_confirmation_context.confirmation_state in (VisionOptionConfirmation.PARTIAL, VisionOptionConfirmation.NEUTRAL)
        or request.setup_qualification_context.setup_quality is VisionSetupQuality.MEDIUM
        or request.level_context.quality is VisionLevelQuality.PARTIAL
    ):
        return "medium"
    return "low"


def _blocking_reasons(request: VisionMethodCalculationRequest) -> tuple[str, ...]:
    reasons: list[str] = []
    reasons.extend(request.setup_qualification_context.blocking_reasons)
    confirmation = request.option_confirmation_context
    if confirmation.confirmation_state is VisionOptionConfirmation.CONTRADICTS:
        reasons.extend(confirmation.contradicting_factors)
    if confirmation.confirmation_state is VisionOptionConfirmation.UNAVAILABLE:
        reasons.append("Option chain unavailable")
    if _has_insufficient_data(request):
        reasons.append("Insufficient data")
    return _dedupe(reasons)


def _supporting_reasons(request: VisionMethodCalculationRequest) -> tuple[str, ...]:
    reasons: list[str] = []
    reasons.extend(_level_reasons(request.level_context))
    reasons.extend(_opening_range_reasons(request.opening_range_context))
    reasons.extend(_structure_reasons(request.structure_context))
    reasons.extend(_liquidity_reasons(request.liquidity_context))
    reasons.extend(_structure_event_reasons(request.structure_event_context))
    reasons.extend(request.setup_qualification_context.supporting_reasons)
    reasons.extend(request.option_confirmation_context.supporting_factors)
    reasons.extend(request.option_confirmation_context.neutral_factors)
    return _dedupe(reasons)


def _level_reasons(context: VisionLevelContext) -> tuple[str, ...]:
    reasons = [
        f"CPR {context.cpr_context.relation.value}",
        f"Camarilla {context.camarilla_context.zone.value}",
    ]
    if context.adr_context is not None:
        reasons.append(f"ADR {context.adr_context.range_consumed_pct:.0f}% consumed")
    if context.vwap_context is not None:
        reasons.append(f"VWAP {context.vwap_context.relation.value}")
    return tuple(reasons)


def _opening_range_reasons(context: VisionOpeningRangeContext) -> tuple[str, ...]:
    if not context.range_complete:
        return ("Opening range incomplete",)
    return (f"Opening range {context.retest_state.value}",)


def _structure_reasons(context: VisionStructureContext) -> tuple[str, ...]:
    return (f"Structure {context.structure_state.value}", f"Trend {context.trend.value}")


def _liquidity_reasons(context: VisionLiquidityContext) -> tuple[str, ...]:
    reasons = [f"Liquidity pool {context.liquidity_pool.value}"]
    if context.liquidity_sweep.value != "none":
        reasons.append(f"Liquidity sweep {context.liquidity_sweep.value}")
    return tuple(reasons)


def _structure_event_reasons(context: VisionStructureEventContext) -> tuple[str, ...]:
    reasons: list[str] = []
    if context.bos is not VisionBOS.NONE:
        reasons.append(context.bos.value)
    if context.choch is not VisionCHoCH.NONE:
        reasons.append(context.choch.value)
    if context.continuation is not VisionStructureEventPhase.NONE:
        reasons.append(context.continuation.value)
    return tuple(reasons)


def _has_insufficient_data(request: VisionMethodCalculationRequest) -> bool:
    return (
        request.level_context.quality is VisionLevelQuality.INSUFFICIENT
        or request.opening_range_context.quality is VisionLevelQuality.INSUFFICIENT
        or request.structure_context.quality is VisionLevelQuality.INSUFFICIENT
        or request.liquidity_context.quality is VisionLevelQuality.INSUFFICIENT
        or request.structure_event_context.quality is VisionLevelQuality.INSUFFICIENT
        or request.option_confirmation_context.quality is VisionLevelQuality.INSUFFICIENT
    )


def _setup_direction(setup: VisionSetupQualificationContext) -> str | None:
    text = " ".join(setup.supporting_reasons).casefold()
    bullish = any(token in text for token in ("bullish", "above cpr", "above h3", "cross above"))
    bearish = any(token in text for token in ("bearish", "below cpr", "below l3", "cross below"))
    if bullish and not bearish:
        return "bullish"
    if bearish and not bullish:
        return "bearish"
    return None


def _dedupe(values: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return tuple(result)


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
