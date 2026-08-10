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
    VisionChaseRisk,
    VisionCPRRelation,
    VisionCandidateState,
    VisionCamarillaZone,
    VisionDirectionQuality,
    VisionEntryLocationState,
    VisionLevelQuality,
    VisionMarketRegime,
    VisionMoveMaturity,
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
    VisionContextAssemblyFailure,
    VisionEntryLocationContext,
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
from .pivot_context import VisionPivotFlightPlan
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
    current_price: float | None = None
    pivot_flight_plan: VisionPivotFlightPlan | None = None
    assembly_failures: tuple[VisionContextAssemblyFailure, ...] = ()

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
        if self.current_price is not None:
            object.__setattr__(self, "current_price", _positive_number(self.current_price, "current_price"))
        if self.pivot_flight_plan is not None:
            if not isinstance(self.pivot_flight_plan, VisionPivotFlightPlan):
                raise TypeError("pivot_flight_plan must be VisionPivotFlightPlan or None.")
            if self.pivot_flight_plan.instrument is not self.instrument:
                raise ValueError("pivot_flight_plan instrument mismatch.")
            if self.pivot_flight_plan.trading_date != self.timestamp.date():
                raise ValueError("pivot_flight_plan trading date mismatch.")
        object.__setattr__(self, "assembly_failures", _normalize_assembly_failures(self.assembly_failures))


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
    entry_location = _entry_location_context(request)
    blocking_reasons = _blocking_reasons(request)
    supporting_reasons = _supporting_reasons(request, entry_location)
    candidate_state = _candidate_state(request, blocking_reasons, entry_location)
    quality = _method_quality(request, candidate_state, blocking_reasons, entry_location)

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
        pivot_flight_plan=request.pivot_flight_plan,
        entry_location_context=entry_location,
        assembly_failures=request.assembly_failures,
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


_MIN_REMAINING_ROOM_FRACTION = 0.25
_MATURE_ADR_CONSUMED_PCT = 70.0
_EXTENDED_ADR_CONSUMED_PCT = 90.0


def _candidate_state(
    request: VisionMethodCalculationRequest,
    blocking_reasons: tuple[str, ...],
    entry_location: VisionEntryLocationContext,
) -> VisionCandidateState:
    if _has_insufficient_data(request):
        return VisionCandidateState.INSUFFICIENT_DATA
    if not request.opening_range_context.range_complete:
        return VisionCandidateState.WAIT
    if blocking_reasons or request.setup_qualification_context.setup_quality is VisionSetupQuality.INVALID:
        return VisionCandidateState.AVOID

    direction = _setup_direction(request.setup_qualification_context)
    confirmation = request.option_confirmation_context.confirmation_state
    location_allows_entry = _entry_location_allows_action(entry_location)
    if direction == "bullish":
        if (
            confirmation
            in (VisionOptionConfirmation.CONFIRMS, VisionOptionConfirmation.NEUTRAL, VisionOptionConfirmation.UNAVAILABLE)
            and location_allows_entry
        ):
            return VisionCandidateState.LONG_ELIGIBLE
        if confirmation in (
            VisionOptionConfirmation.CONFIRMS,
            VisionOptionConfirmation.PARTIAL,
            VisionOptionConfirmation.NEUTRAL,
            VisionOptionConfirmation.CONTRADICTS,
            VisionOptionConfirmation.UNAVAILABLE,
        ):
            return VisionCandidateState.PREPARE_LONG
    if direction == "bearish":
        if (
            confirmation
            in (VisionOptionConfirmation.CONFIRMS, VisionOptionConfirmation.NEUTRAL, VisionOptionConfirmation.UNAVAILABLE)
            and location_allows_entry
        ):
            return VisionCandidateState.SHORT_ELIGIBLE
        if confirmation in (
            VisionOptionConfirmation.CONFIRMS,
            VisionOptionConfirmation.PARTIAL,
            VisionOptionConfirmation.NEUTRAL,
            VisionOptionConfirmation.CONTRADICTS,
            VisionOptionConfirmation.UNAVAILABLE,
        ):
            return VisionCandidateState.PREPARE_SHORT
    if request.setup_qualification_context.eligible_for_option_confirmation:
        return VisionCandidateState.OBSERVE
    return VisionCandidateState.AVOID


def _method_quality(
    request: VisionMethodCalculationRequest,
    candidate_state: VisionCandidateState,
    blocking_reasons: tuple[str, ...],
    entry_location: VisionEntryLocationContext,
) -> str:
    if candidate_state is VisionCandidateState.INSUFFICIENT_DATA:
        return "invalid"
    if blocking_reasons or candidate_state is VisionCandidateState.AVOID:
        return "invalid"
    if entry_location.entry_location_quality is VisionLevelQuality.INSUFFICIENT:
        return "low"
    if (
        request.level_context.quality is VisionLevelQuality.FULL
        and request.opening_range_context.quality is VisionLevelQuality.FULL
        and request.structure_context.quality is VisionLevelQuality.FULL
        and request.liquidity_context.quality is VisionLevelQuality.FULL
        and request.structure_event_context.quality is VisionLevelQuality.FULL
        and request.option_confirmation_context.quality is VisionLevelQuality.FULL
        and request.setup_qualification_context.setup_quality is VisionSetupQuality.HIGH
        and request.option_confirmation_context.confirmation_state is VisionOptionConfirmation.CONFIRMS
        and entry_location.entry_location_state in (VisionEntryLocationState.FAVORABLE, VisionEntryLocationState.ACCEPTABLE)
    ):
        return "high"
    if (
        request.option_confirmation_context.confirmation_state
        in (VisionOptionConfirmation.CONTRADICTS,)
        or request.liquidity_context.quality in (VisionLevelQuality.PARTIAL, VisionLevelQuality.INSUFFICIENT)
        or request.option_confirmation_context.quality is VisionLevelQuality.INSUFFICIENT
        or entry_location.chase_risk is VisionChaseRisk.HIGH
        or entry_location.entry_location_state
        in (VisionEntryLocationState.POOR, VisionEntryLocationState.DO_NOT_CHASE, VisionEntryLocationState.WAIT_FOR_RETEST)
    ):
        return "low"
    if (
        request.option_confirmation_context.confirmation_state
        in (VisionOptionConfirmation.PARTIAL, VisionOptionConfirmation.NEUTRAL, VisionOptionConfirmation.UNAVAILABLE)
        or request.setup_qualification_context.setup_quality is VisionSetupQuality.MEDIUM
        or request.level_context.quality is VisionLevelQuality.PARTIAL
        or entry_location.entry_location_state is VisionEntryLocationState.ACCEPTABLE
    ):
        return "medium"
    return "low"


def _blocking_reasons(request: VisionMethodCalculationRequest) -> tuple[str, ...]:
    reasons: list[str] = []
    reasons.extend(
        f"{failure.stage} {failure.status.value}: {failure.validation_message}"
        for failure in request.assembly_failures
        if _assembly_failure_blocks(failure)
    )
    reasons.extend(request.setup_qualification_context.blocking_reasons)
    if _has_insufficient_data(request):
        reasons.append("Insufficient data")
    return _dedupe(reasons)


def _supporting_reasons(
    request: VisionMethodCalculationRequest,
    entry_location: VisionEntryLocationContext,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if request.pivot_flight_plan is not None:
        reasons.extend(_pivot_flight_plan_reasons(request.pivot_flight_plan))
    reasons.extend(_level_reasons(request.level_context))
    reasons.extend(_opening_range_reasons(request.opening_range_context))
    reasons.extend(_structure_reasons(request.structure_context))
    reasons.extend(_liquidity_reasons(request.liquidity_context))
    reasons.extend(_structure_event_reasons(request.structure_event_context))
    reasons.extend(request.setup_qualification_context.supporting_reasons)
    reasons.extend(request.option_confirmation_context.supporting_factors)
    reasons.extend(f"Option contradiction: {factor}" for factor in request.option_confirmation_context.contradicting_factors)
    reasons.extend(request.option_confirmation_context.neutral_factors)
    reasons.extend(entry_location.location_supporting_reasons)
    reasons.extend(entry_location.location_warning_reasons)
    return _dedupe(reasons)


def _pivot_flight_plan_reasons(plan: VisionPivotFlightPlan) -> tuple[str, ...]:
    reasons = [
        f"Pivot context {plan.combined_context_state.value}",
        f"Pivot prior {plan.combined_directional_prior.value}",
        f"CPR relationship {plan.cpr_relationship.value}",
        f"CPR width {plan.cpr_width_state.value}",
        f"Camarilla relationship {plan.camarilla_relationship.value}",
        f"Camarilla width {plan.camarilla_width_state.value}",
        "Opening confirmation required",
    ]
    reasons.extend(f"Pivot conflict: {item}" for item in plan.conflicting_reasons)
    reasons.extend(f"Pivot warning: {item}" for item in plan.warnings)
    return tuple(reasons)


def _entry_location_context(request: VisionMethodCalculationRequest) -> VisionEntryLocationContext:
    direction = _setup_direction(request.setup_qualification_context) or "unknown"
    direction_quality = _direction_quality(request, direction)
    current_price = _current_price(request, direction)
    destination, remaining_room = _destination_and_room(request, direction, current_price)
    maturity = _move_maturity(request, remaining_room)
    chase_risk = _chase_risk(request, remaining_room, maturity)
    state = _entry_state(direction_quality, remaining_room, maturity, chase_risk, request)
    supporting: list[str] = []
    warnings: list[str] = []
    blocking: list[str] = []
    if direction in {"bullish", "bearish"}:
        supporting.append(f"{direction.title()} thesis identified")
    if remaining_room is not None:
        supporting.append(f"Remaining room {remaining_room:.2f}")
    if state in (VisionEntryLocationState.FAVORABLE, VisionEntryLocationState.ACCEPTABLE):
        supporting.append("Entry location supports new entry")
    if request.opening_range_context.retest_state is VisionOpeningRangeState.RETEST:
        supporting.append("Retest improves entry location")
    if state in (VisionEntryLocationState.POOR, VisionEntryLocationState.DO_NOT_CHASE, VisionEntryLocationState.WAIT_FOR_RETEST):
        warnings.append("Wait for retest")
        blocking.append("Entry location is not suitable for a fresh entry")
    if chase_risk is VisionChaseRisk.HIGH:
        warnings.append("High chase risk")
    if remaining_room is None:
        warnings.append("Remaining room unavailable")
    quality = VisionLevelQuality.FULL if state in (VisionEntryLocationState.FAVORABLE, VisionEntryLocationState.ACCEPTABLE) else VisionLevelQuality.PARTIAL
    if state is VisionEntryLocationState.INSUFFICIENT_DATA:
        quality = VisionLevelQuality.INSUFFICIENT
    return VisionEntryLocationContext(
        direction=direction,
        direction_quality=direction_quality,
        entry_location_state=state,
        entry_location_quality=quality,
        remaining_room=remaining_room,
        nearest_target_or_destination=destination,
        nearest_invalidation=_invalidation_reference(request, direction),
        move_maturity=maturity,
        retest_state=request.opening_range_context.retest_state.value,
        chase_risk=chase_risk,
        location_supporting_reasons=_dedupe(supporting),
        location_warning_reasons=_dedupe(warnings),
        location_blocking_reasons=_dedupe(blocking),
    )


def _direction_quality(request: VisionMethodCalculationRequest, direction: str) -> VisionDirectionQuality:
    if direction not in {"bullish", "bearish"}:
        return VisionDirectionQuality.INVALID
    if request.setup_qualification_context.setup_quality is VisionSetupQuality.HIGH:
        return VisionDirectionQuality.HIGH
    if request.setup_qualification_context.setup_quality is VisionSetupQuality.MEDIUM:
        return VisionDirectionQuality.MEDIUM
    if request.setup_qualification_context.setup_quality is VisionSetupQuality.LOW:
        return VisionDirectionQuality.LOW
    return VisionDirectionQuality.INVALID


def _current_price(request: VisionMethodCalculationRequest, direction: str) -> float:
    if request.current_price is not None:
        return request.current_price
    if direction == "bearish":
        return request.opening_range_context.opening_low
    return request.opening_range_context.opening_high


def _destination_and_room(
    request: VisionMethodCalculationRequest,
    direction: str,
    current_price: float,
) -> tuple[str, float | None]:
    levels = request.level_context.camarilla_context
    if direction == "bullish":
        name, target = _bullish_destination(levels, current_price)
        return name, max(0.0, target - current_price)
    if direction == "bearish":
        name, target = _bearish_destination(levels, current_price)
        return name, max(0.0, current_price - target)
    return "unknown", None


def _bullish_destination(levels, current_price: float) -> tuple[str, float]:
    if current_price < levels.h3:
        return "H3", levels.h3
    if current_price < levels.h4:
        return "H4", levels.h4
    if current_price < levels.h5:
        return "H5", levels.h5
    return "H6", levels.h6


def _bearish_destination(levels, current_price: float) -> tuple[str, float]:
    if current_price > levels.l3:
        return "L3", levels.l3
    if current_price > levels.l4:
        return "L4", levels.l4
    if current_price > levels.l5:
        return "L5", levels.l5
    return "L6", levels.l6


def _invalidation_reference(request: VisionMethodCalculationRequest, direction: str) -> str:
    structure = request.structure_context
    if direction == "bullish":
        return "Below Swing Low" if structure.current_swing_low is not None else "Below Opening Range"
    if direction == "bearish":
        return "Above Swing High" if structure.current_swing_high is not None else "Above Opening Range"
    return "unknown"


def _move_maturity(request: VisionMethodCalculationRequest, remaining_room: float | None) -> VisionMoveMaturity:
    adr = request.level_context.adr_context
    consumed = adr.range_consumed_pct if adr is not None else 0.0
    if consumed >= _EXTENDED_ADR_CONSUMED_PCT:
        return VisionMoveMaturity.EXTENDED
    if remaining_room is not None and remaining_room <= _minimum_remaining_room(request):
        return VisionMoveMaturity.MATURE
    if consumed >= _MATURE_ADR_CONSUMED_PCT:
        return VisionMoveMaturity.MATURE
    if consumed >= 40.0:
        return VisionMoveMaturity.DEVELOPING
    return VisionMoveMaturity.EARLY


def _chase_risk(
    request: VisionMethodCalculationRequest,
    remaining_room: float | None,
    maturity: VisionMoveMaturity,
) -> VisionChaseRisk:
    if remaining_room is None:
        return VisionChaseRisk.MEDIUM
    if remaining_room <= _minimum_remaining_room(request) and maturity in (VisionMoveMaturity.MATURE, VisionMoveMaturity.EXTENDED):
        return VisionChaseRisk.HIGH
    if remaining_room <= _minimum_remaining_room(request):
        return VisionChaseRisk.MEDIUM
    if maturity is VisionMoveMaturity.EXTENDED:
        return VisionChaseRisk.HIGH
    if maturity is VisionMoveMaturity.MATURE:
        return VisionChaseRisk.MEDIUM
    return VisionChaseRisk.LOW


def _entry_state(
    direction_quality: VisionDirectionQuality,
    remaining_room: float | None,
    maturity: VisionMoveMaturity,
    chase_risk: VisionChaseRisk,
    request: VisionMethodCalculationRequest,
) -> VisionEntryLocationState:
    if direction_quality is VisionDirectionQuality.INVALID or remaining_room is None:
        return VisionEntryLocationState.INSUFFICIENT_DATA
    if chase_risk is VisionChaseRisk.HIGH:
        return VisionEntryLocationState.WAIT_FOR_RETEST
    if remaining_room <= _minimum_remaining_room(request):
        return VisionEntryLocationState.POOR
    if request.opening_range_context.retest_state is VisionOpeningRangeState.RETEST:
        return VisionEntryLocationState.FAVORABLE
    if maturity in (VisionMoveMaturity.EARLY, VisionMoveMaturity.DEVELOPING):
        return VisionEntryLocationState.ACCEPTABLE
    return VisionEntryLocationState.POOR


def _entry_location_allows_action(entry_location: VisionEntryLocationContext) -> bool:
    return (
        entry_location.direction_quality in (VisionDirectionQuality.HIGH, VisionDirectionQuality.MEDIUM)
        and entry_location.entry_location_state in (VisionEntryLocationState.FAVORABLE, VisionEntryLocationState.ACCEPTABLE)
    )


def _minimum_remaining_room(request: VisionMethodCalculationRequest) -> float:
    levels = request.level_context.camarilla_context
    upper_band = abs(levels.h4 - levels.h3)
    lower_band = abs(levels.l3 - levels.l4)
    reference_band = max(upper_band, lower_band, request.opening_range_context.opening_width, 1.0)
    return reference_band * _MIN_REMAINING_ROOM_FRACTION


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
        any(_assembly_failure_blocks(failure) for failure in request.assembly_failures)
        or
        request.level_context.quality is VisionLevelQuality.INSUFFICIENT
        or request.opening_range_context.quality is VisionLevelQuality.INSUFFICIENT
        or request.structure_context.quality is VisionLevelQuality.INSUFFICIENT
        or request.structure_event_context.quality is VisionLevelQuality.INSUFFICIENT
    )


def _assembly_failure_blocks(failure: VisionContextAssemblyFailure) -> bool:
    stage = failure.stage.strip().casefold().replace("_", " ")
    supporting_stages = {
        "adr",
        "vwap",
        "liquidity",
        "option confirmation",
        "option chain",
        "momentum",
        "volume",
    }
    return stage not in supporting_stages


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


def _normalize_assembly_failures(
    values: tuple[VisionContextAssemblyFailure, ...],
) -> tuple[VisionContextAssemblyFailure, ...]:
    if not isinstance(values, tuple):
        raise TypeError("assembly_failures must be a tuple.")
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, VisionContextAssemblyFailure):
            raise TypeError("assembly_failures must contain VisionContextAssemblyFailure objects.")
        key = value.stage.casefold()
        if key in seen:
            raise ValueError("assembly_failures cannot contain duplicate stages.")
        seen.add(key)
    return values


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _positive_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    normalized = float(value)
    if normalized != normalized or normalized in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite.")
    if normalized <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return normalized
