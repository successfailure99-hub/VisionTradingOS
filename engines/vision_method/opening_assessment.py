"""
Opening acceptance/rejection assessment for the Vision Pivot Method.

VPM_OPENING_1 confirms, rejects, or leaves unresolved the provisional Pivot
Flight Plan from the official session opening observation. It never creates
trade candidates, entries, OSE requests, or broker actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import RuntimeInstrument

from .enums import (
    VisionOpeningAcceptanceState,
    VisionOpeningActionZoneId,
    VisionOpeningActionZoneState,
    VisionOpeningCPRLocation,
    VisionOpeningCamarillaLocation,
    VisionOpeningGapState,
    VisionOpeningPivotValueLocation,
    VisionOpeningPriorRangeLocation,
    VisionOpeningScenario,
    VisionOpeningScenarioDirection,
    VisionOpeningScenarioStrength,
    VisionPivotCombinedContext,
    VisionPivotDirectionalPrior,
    VisionPivotRelationship,
    VisionPivotWidthState,
)
from .models import VisionLevelContext
from .pivot_context import VisionPivotFlightPlan


@dataclass(frozen=True, slots=True)
class VisionOpeningActionZone:
    zone_id: VisionOpeningActionZoneId
    state: VisionOpeningActionZoneState
    direction: VisionOpeningScenarioDirection
    source: str
    reason: str

    def __post_init__(self) -> None:
        _require_enum(self.zone_id, VisionOpeningActionZoneId, "zone_id")
        if not isinstance(self.state, VisionOpeningActionZoneState):
            raise TypeError("state must be VisionOpeningActionZoneState.")
        if not isinstance(self.direction, VisionOpeningScenarioDirection):
            raise TypeError("direction must be VisionOpeningScenarioDirection.")
        object.__setattr__(self, "source", _normalize_text(self.source, "source"))
        object.__setattr__(self, "reason", _normalize_text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class VisionPivotOpeningAssessment:
    instrument: RuntimeInstrument
    trading_date: date
    flight_plan_reference: str
    opening_price: float
    opening_timestamp: datetime
    prior_range_location: VisionOpeningPriorRangeLocation
    pivot_value_location: VisionOpeningPivotValueLocation
    cpr_location: VisionOpeningCPRLocation
    camarilla_location: VisionOpeningCamarillaLocation
    gap_state: VisionOpeningGapState
    pre_market_context: VisionPivotCombinedContext
    pre_market_directional_prior: VisionPivotDirectionalPrior
    opening_acceptance_state: VisionOpeningAcceptanceState
    active_scenario: VisionOpeningScenario
    scenario_direction: VisionOpeningScenarioDirection
    scenario_strength: VisionOpeningScenarioStrength
    activated_action_zones: tuple[VisionOpeningActionZone, ...]
    deactivated_action_zones: tuple[VisionOpeningActionZone, ...]
    supporting_reasons: tuple[str, ...]
    contradicting_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    assessment_complete: bool

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date.")
        object.__setattr__(self, "flight_plan_reference", _normalize_text(self.flight_plan_reference, "flight_plan_reference"))
        object.__setattr__(self, "opening_price", _positive_number(self.opening_price, "opening_price"))
        _validate_aware(self.opening_timestamp, "opening_timestamp")
        if self.opening_timestamp.date() != self.trading_date:
            raise ValueError("opening_timestamp trading date mismatch.")
        _require_enum(self.prior_range_location, VisionOpeningPriorRangeLocation, "prior_range_location")
        _require_enum(self.pivot_value_location, VisionOpeningPivotValueLocation, "pivot_value_location")
        _require_enum(self.cpr_location, VisionOpeningCPRLocation, "cpr_location")
        _require_enum(self.camarilla_location, VisionOpeningCamarillaLocation, "camarilla_location")
        _require_enum(self.gap_state, VisionOpeningGapState, "gap_state")
        _require_enum(self.pre_market_context, VisionPivotCombinedContext, "pre_market_context")
        _require_enum(self.pre_market_directional_prior, VisionPivotDirectionalPrior, "pre_market_directional_prior")
        _require_enum(self.opening_acceptance_state, VisionOpeningAcceptanceState, "opening_acceptance_state")
        _require_enum(self.active_scenario, VisionOpeningScenario, "active_scenario")
        _require_enum(self.scenario_direction, VisionOpeningScenarioDirection, "scenario_direction")
        _require_enum(self.scenario_strength, VisionOpeningScenarioStrength, "scenario_strength")
        object.__setattr__(self, "activated_action_zones", _normalize_zones(self.activated_action_zones, "activated_action_zones"))
        object.__setattr__(self, "deactivated_action_zones", _normalize_zones(self.deactivated_action_zones, "deactivated_action_zones"))
        object.__setattr__(self, "supporting_reasons", _normalize_unique_text_tuple(self.supporting_reasons, "supporting_reasons"))
        object.__setattr__(self, "contradicting_reasons", _normalize_unique_text_tuple(self.contradicting_reasons, "contradicting_reasons"))
        object.__setattr__(self, "warnings", _normalize_unique_text_tuple(self.warnings, "warnings"))
        if not isinstance(self.assessment_complete, bool):
            raise TypeError("assessment_complete must be bool.")


@dataclass(frozen=True, slots=True)
class VisionPivotOpeningAssessmentRequest:
    instrument: RuntimeInstrument
    trading_date: date
    opening_price: float
    opening_timestamp: datetime
    flight_plan: VisionPivotFlightPlan
    level_context: VisionLevelContext

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date.")
        object.__setattr__(self, "opening_price", _positive_number(self.opening_price, "opening_price"))
        _validate_aware(self.opening_timestamp, "opening_timestamp")
        if self.opening_timestamp.date() != self.trading_date:
            raise ValueError("opening_timestamp trading date mismatch.")
        if not isinstance(self.flight_plan, VisionPivotFlightPlan):
            raise TypeError("flight_plan must be VisionPivotFlightPlan.")
        if not isinstance(self.level_context, VisionLevelContext):
            raise TypeError("level_context must be VisionLevelContext.")


def assess_pivot_opening(request: VisionPivotOpeningAssessmentRequest) -> VisionPivotOpeningAssessment:
    validate_pivot_opening_assessment_request(request)
    prior_location = classify_open_vs_prior_range(request.opening_price, request.level_context)
    cpr_location = classify_open_vs_cpr(request.opening_price, request.level_context)
    camarilla_location = classify_open_vs_camarilla(request.opening_price, request.level_context)
    value_location = classify_opening_value_location(prior_location, cpr_location)
    gap_state = classify_opening_gap(request.opening_price, request.level_context)
    acceptance, scenario, direction, strength, supporting, contradicting, warnings = _resolve_opening(
        request.flight_plan,
        prior_location,
        cpr_location,
        camarilla_location,
        value_location,
        gap_state,
    )
    active_zones, deactivated_zones = _action_zones(
        request.flight_plan,
        camarilla_location,
        prior_location,
        scenario,
        direction,
        acceptance,
    )
    return VisionPivotOpeningAssessment(
        instrument=request.instrument,
        trading_date=request.trading_date,
        flight_plan_reference=_flight_plan_reference(request.flight_plan),
        opening_price=request.opening_price,
        opening_timestamp=request.opening_timestamp,
        prior_range_location=prior_location,
        pivot_value_location=value_location,
        cpr_location=cpr_location,
        camarilla_location=camarilla_location,
        gap_state=gap_state,
        pre_market_context=request.flight_plan.combined_context_state,
        pre_market_directional_prior=request.flight_plan.combined_directional_prior,
        opening_acceptance_state=acceptance,
        active_scenario=scenario,
        scenario_direction=direction,
        scenario_strength=strength,
        activated_action_zones=active_zones,
        deactivated_action_zones=deactivated_zones,
        supporting_reasons=supporting,
        contradicting_reasons=contradicting,
        warnings=warnings,
        assessment_complete=acceptance
        in {
            VisionOpeningAcceptanceState.ACCEPTED,
            VisionOpeningAcceptanceState.PARTIALLY_ACCEPTED,
            VisionOpeningAcceptanceState.REJECTED,
        },
    )


def validate_pivot_opening_assessment_request(
    request: VisionPivotOpeningAssessmentRequest,
) -> VisionPivotOpeningAssessmentRequest:
    if not isinstance(request, VisionPivotOpeningAssessmentRequest):
        raise TypeError("request must be VisionPivotOpeningAssessmentRequest.")
    if request.flight_plan.instrument is not request.instrument:
        raise ValueError("flight_plan instrument mismatch.")
    if request.flight_plan.trading_date != request.trading_date:
        raise ValueError("flight_plan trading date mismatch.")
    if not request.flight_plan.opening_confirmation_required:
        raise ValueError("flight_plan must require opening confirmation.")
    return request


def classify_open_vs_prior_range(
    opening_price: float,
    level_context: VisionLevelContext,
) -> VisionOpeningPriorRangeLocation:
    price = _positive_number(opening_price, "opening_price")
    previous = level_context.previous_day_context
    if price > previous.previous_high:
        return VisionOpeningPriorRangeLocation.ABOVE_PRIOR_HIGH
    if price < previous.previous_low:
        return VisionOpeningPriorRangeLocation.BELOW_PRIOR_LOW
    return VisionOpeningPriorRangeLocation.INSIDE_PRIOR_RANGE


def classify_open_vs_cpr(
    opening_price: float,
    level_context: VisionLevelContext,
) -> VisionOpeningCPRLocation:
    price = _positive_number(opening_price, "opening_price")
    cpr = level_context.cpr_context
    low = min(cpr.bc, cpr.tc)
    high = max(cpr.bc, cpr.tc)
    if price > high:
        return VisionOpeningCPRLocation.ABOVE_CPR
    if price < low:
        return VisionOpeningCPRLocation.BELOW_CPR
    return VisionOpeningCPRLocation.INSIDE_CPR


def classify_open_vs_camarilla(
    opening_price: float,
    level_context: VisionLevelContext,
) -> VisionOpeningCamarillaLocation:
    price = _positive_number(opening_price, "opening_price")
    cama = level_context.camarilla_context
    if price > cama.h4:
        return VisionOpeningCamarillaLocation.ABOVE_H4
    if price > cama.h3:
        return VisionOpeningCamarillaLocation.BETWEEN_H3_H4
    if price >= cama.l3:
        return VisionOpeningCamarillaLocation.BETWEEN_L3_H3
    if price >= cama.l4:
        return VisionOpeningCamarillaLocation.BETWEEN_L4_L3
    return VisionOpeningCamarillaLocation.BELOW_L4


def classify_opening_value_location(
    prior_location: VisionOpeningPriorRangeLocation,
    cpr_location: VisionOpeningCPRLocation,
) -> VisionOpeningPivotValueLocation:
    if (
        prior_location is VisionOpeningPriorRangeLocation.INSUFFICIENT_DATA
        or cpr_location is VisionOpeningCPRLocation.INSUFFICIENT_DATA
    ):
        return VisionOpeningPivotValueLocation.INSUFFICIENT_DATA
    in_range = prior_location is VisionOpeningPriorRangeLocation.INSIDE_PRIOR_RANGE
    in_value = cpr_location is VisionOpeningCPRLocation.INSIDE_CPR
    if in_range and in_value:
        return VisionOpeningPivotValueLocation.IN_RANGE_IN_VALUE
    if in_range:
        return VisionOpeningPivotValueLocation.IN_RANGE_OUT_OF_VALUE
    return VisionOpeningPivotValueLocation.OUT_OF_RANGE_OUT_OF_VALUE


def classify_opening_gap(opening_price: float, level_context: VisionLevelContext) -> VisionOpeningGapState:
    price = _positive_number(opening_price, "opening_price")
    previous = level_context.previous_day_context
    if price > previous.previous_high or price > previous.previous_close:
        return VisionOpeningGapState.GAP_UP
    if price < previous.previous_low or price < previous.previous_close:
        return VisionOpeningGapState.GAP_DOWN
    return VisionOpeningGapState.NO_MEANINGFUL_GAP


def _resolve_opening(
    plan: VisionPivotFlightPlan,
    prior_location: VisionOpeningPriorRangeLocation,
    cpr_location: VisionOpeningCPRLocation,
    camarilla_location: VisionOpeningCamarillaLocation,
    value_location: VisionOpeningPivotValueLocation,
    gap_state: VisionOpeningGapState,
) -> tuple[
    VisionOpeningAcceptanceState,
    VisionOpeningScenario,
    VisionOpeningScenarioDirection,
    VisionOpeningScenarioStrength,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    supporting = [
        f"Pre-market context {plan.combined_context_state.value}",
        f"Opening prior range location {prior_location.value}",
        f"Opening CPR location {cpr_location.value}",
        f"Opening Camarilla location {camarilla_location.value}",
        f"Opening gap {gap_state.value}",
    ]
    contradicting: list[str] = []
    warnings: list[str] = []

    bullish_support = _bullish_open(prior_location, cpr_location, camarilla_location)
    bearish_support = _bearish_open(prior_location, cpr_location, camarilla_location)
    bullish_plan = plan.combined_directional_prior in {
        VisionPivotDirectionalPrior.BULLISH,
        VisionPivotDirectionalPrior.MODERATELY_BULLISH,
    } or plan.combined_context_state is VisionPivotCombinedContext.BULLISH_ALIGNED
    bearish_plan = plan.combined_directional_prior in {
        VisionPivotDirectionalPrior.BEARISH,
        VisionPivotDirectionalPrior.MODERATELY_BEARISH,
    } or plan.combined_context_state is VisionPivotCombinedContext.BEARISH_ALIGNED
    inside_breakout_plan = (
        plan.combined_context_state is VisionPivotCombinedContext.BREAKOUT_POTENTIAL
        or plan.cpr_relationship is VisionPivotRelationship.INSIDE_VALUE
        or plan.camarilla_relationship is VisionPivotRelationship.INSIDE_VALUE
    )
    balance_plan = plan.combined_context_state in {
        VisionPivotCombinedContext.BALANCE_RANGE,
        VisionPivotCombinedContext.NEUTRAL,
    } or plan.cpr_relationship in {
        VisionPivotRelationship.OUTSIDE_VALUE,
        VisionPivotRelationship.UNCHANGED_VALUE,
    }
    conflicted_plan = plan.combined_context_state is VisionPivotCombinedContext.CONFLICTED

    if plan.combined_context_state is VisionPivotCombinedContext.INSUFFICIENT_DATA:
        return (
            VisionOpeningAcceptanceState.INSUFFICIENT_DATA,
            VisionOpeningScenario.NO_ACTIVE_SCENARIO,
            VisionOpeningScenarioDirection.NONE,
            VisionOpeningScenarioStrength.INSUFFICIENT_DATA,
            tuple(supporting),
            (),
            ("Opening assessment requires a complete Pivot Flight Plan",),
        )

    if conflicted_plan:
        if bullish_support and not bearish_support:
            supporting.append("Conflicted plan resolved bullish by opening location")
            return _resolved(
                VisionOpeningAcceptanceState.PARTIALLY_ACCEPTED,
                VisionOpeningScenario.BULLISH_CONTINUATION,
                VisionOpeningScenarioDirection.BULLISH,
                VisionOpeningScenarioStrength.MODERATE,
                supporting,
                contradicting,
                warnings,
            )
        if bearish_support and not bullish_support:
            supporting.append("Conflicted plan resolved bearish by opening location")
            return _resolved(
                VisionOpeningAcceptanceState.PARTIALLY_ACCEPTED,
                VisionOpeningScenario.BEARISH_CONTINUATION,
                VisionOpeningScenarioDirection.BEARISH,
                VisionOpeningScenarioStrength.MODERATE,
                supporting,
                contradicting,
                warnings,
            )
        warnings.append("Conflicted pivot plan remains unresolved after opening")
        return _resolved(
            VisionOpeningAcceptanceState.UNRESOLVED,
            VisionOpeningScenario.CONFLICTED,
            VisionOpeningScenarioDirection.CONFLICTED,
            VisionOpeningScenarioStrength.WEAK,
            supporting,
            contradicting,
            warnings,
        )

    if inside_breakout_plan:
        if _upside_breakout_open(prior_location, camarilla_location):
            supporting.append("Inside/narrow pivot plan resolved to upside breakout watch")
            return _resolved(
                VisionOpeningAcceptanceState.PARTIALLY_ACCEPTED,
                VisionOpeningScenario.BULLISH_BREAKOUT_WATCH,
                VisionOpeningScenarioDirection.BULLISH,
                VisionOpeningScenarioStrength.MODERATE,
                supporting,
                contradicting,
                warnings,
            )
        if _downside_breakout_open(prior_location, camarilla_location):
            supporting.append("Inside/narrow pivot plan resolved to downside breakout watch")
            return _resolved(
                VisionOpeningAcceptanceState.PARTIALLY_ACCEPTED,
                VisionOpeningScenario.BEARISH_BREAKOUT_WATCH,
                VisionOpeningScenarioDirection.BEARISH,
                VisionOpeningScenarioStrength.MODERATE,
                supporting,
                contradicting,
                warnings,
            )
        return _resolved(
            VisionOpeningAcceptanceState.UNRESOLVED,
            VisionOpeningScenario.BALANCE_RANGE if value_location is VisionOpeningPivotValueLocation.IN_RANGE_IN_VALUE else VisionOpeningScenario.UNRESOLVED,
            VisionOpeningScenarioDirection.NEUTRAL,
            VisionOpeningScenarioStrength.WEAK,
            supporting,
            contradicting,
            warnings,
        )

    if bullish_plan:
        if bullish_support:
            supporting.append("Bullish pivot plan accepted by supportive opening location")
            return _resolved(
                VisionOpeningAcceptanceState.ACCEPTED,
                VisionOpeningScenario.BULLISH_CONTINUATION,
                VisionOpeningScenarioDirection.BULLISH,
                VisionOpeningScenarioStrength.STRONG if plan.combined_context_state is VisionPivotCombinedContext.BULLISH_ALIGNED else VisionOpeningScenarioStrength.MODERATE,
                supporting,
                contradicting,
                warnings,
            )
        if bearish_support:
            contradicting.append("Opening location opposes bullish pre-market plan")
            return _resolved(
                VisionOpeningAcceptanceState.REJECTED,
                VisionOpeningScenario.BEARISH_BREAKOUT_WATCH,
                VisionOpeningScenarioDirection.BEARISH,
                VisionOpeningScenarioStrength.WEAK,
                supporting,
                contradicting,
                warnings,
            )
        return _resolved(
            VisionOpeningAcceptanceState.PARTIALLY_ACCEPTED,
            VisionOpeningScenario.UNRESOLVED,
            VisionOpeningScenarioDirection.NEUTRAL,
            VisionOpeningScenarioStrength.WEAK,
            supporting,
            contradicting,
            warnings,
        )

    if bearish_plan:
        if bearish_support:
            supporting.append("Bearish pivot plan accepted by supportive opening location")
            return _resolved(
                VisionOpeningAcceptanceState.ACCEPTED,
                VisionOpeningScenario.BEARISH_CONTINUATION,
                VisionOpeningScenarioDirection.BEARISH,
                VisionOpeningScenarioStrength.STRONG if plan.combined_context_state is VisionPivotCombinedContext.BEARISH_ALIGNED else VisionOpeningScenarioStrength.MODERATE,
                supporting,
                contradicting,
                warnings,
            )
        if bullish_support:
            contradicting.append("Opening location opposes bearish pre-market plan")
            return _resolved(
                VisionOpeningAcceptanceState.REJECTED,
                VisionOpeningScenario.BULLISH_BREAKOUT_WATCH,
                VisionOpeningScenarioDirection.BULLISH,
                VisionOpeningScenarioStrength.WEAK,
                supporting,
                contradicting,
                warnings,
            )
        return _resolved(
            VisionOpeningAcceptanceState.PARTIALLY_ACCEPTED,
            VisionOpeningScenario.UNRESOLVED,
            VisionOpeningScenarioDirection.NEUTRAL,
            VisionOpeningScenarioStrength.WEAK,
            supporting,
            contradicting,
            warnings,
        )

    if balance_plan:
        if value_location is VisionOpeningPivotValueLocation.IN_RANGE_IN_VALUE:
            supporting.append("Opening inside prior range and CPR value reinforces balance")
            return _resolved(
                VisionOpeningAcceptanceState.ACCEPTED,
                VisionOpeningScenario.BALANCE_RANGE,
                VisionOpeningScenarioDirection.NEUTRAL,
                VisionOpeningScenarioStrength.MODERATE,
                supporting,
                contradicting,
                warnings,
            )
        if bullish_support:
            return _resolved(
                VisionOpeningAcceptanceState.PARTIALLY_ACCEPTED,
                VisionOpeningScenario.BULLISH_BREAKOUT_WATCH,
                VisionOpeningScenarioDirection.BULLISH,
                VisionOpeningScenarioStrength.WEAK,
                supporting,
                contradicting,
                warnings,
            )
        if bearish_support:
            return _resolved(
                VisionOpeningAcceptanceState.PARTIALLY_ACCEPTED,
                VisionOpeningScenario.BEARISH_BREAKOUT_WATCH,
                VisionOpeningScenarioDirection.BEARISH,
                VisionOpeningScenarioStrength.WEAK,
                supporting,
                contradicting,
                warnings,
            )

    return _resolved(
        VisionOpeningAcceptanceState.UNRESOLVED,
        VisionOpeningScenario.NO_ACTIVE_SCENARIO,
        VisionOpeningScenarioDirection.NONE,
        VisionOpeningScenarioStrength.WEAK,
        supporting,
        contradicting,
        warnings,
    )


def _action_zones(
    plan: VisionPivotFlightPlan,
    camarilla_location: VisionOpeningCamarillaLocation,
    prior_location: VisionOpeningPriorRangeLocation,
    scenario: VisionOpeningScenario,
    direction: VisionOpeningScenarioDirection,
    acceptance: VisionOpeningAcceptanceState,
) -> tuple[tuple[VisionOpeningActionZone, ...], tuple[VisionOpeningActionZone, ...]]:
    active: list[VisionOpeningActionZone] = []
    inactive: list[VisionOpeningActionZone] = []
    if acceptance is VisionOpeningAcceptanceState.INSUFFICIENT_DATA:
        return (), ()

    bullish_invalid = direction is VisionOpeningScenarioDirection.BEARISH and acceptance is VisionOpeningAcceptanceState.REJECTED
    bearish_invalid = direction is VisionOpeningScenarioDirection.BULLISH and acceptance is VisionOpeningAcceptanceState.REJECTED

    if plan.camarilla_directional_prior in {VisionPivotDirectionalPrior.BULLISH, VisionPivotDirectionalPrior.MODERATELY_BULLISH}:
        if camarilla_location in {VisionOpeningCamarillaLocation.ABOVE_H4, VisionOpeningCamarillaLocation.BETWEEN_H3_H4}:
            active.append(_zone(VisionOpeningActionZoneId.H3_PULLBACK_LONG_ZONE, VisionOpeningScenarioDirection.BULLISH, "Opening accepted above H3"))
        elif camarilla_location is VisionOpeningCamarillaLocation.BETWEEN_L3_H3:
            active.append(_zone(VisionOpeningActionZoneId.L3_RESPONSIVE_LONG_ZONE, VisionOpeningScenarioDirection.BULLISH, "Opening accepted inside L3-H3"))
        elif camarilla_location in {VisionOpeningCamarillaLocation.BETWEEN_L4_L3, VisionOpeningCamarillaLocation.BELOW_L4} or bullish_invalid:
            inactive.append(_deactivated_zone(VisionOpeningActionZoneId.H3_PULLBACK_LONG_ZONE, VisionOpeningScenarioDirection.BULLISH, "Opening rejected bullish H3 plan"))
            inactive.append(_deactivated_zone(VisionOpeningActionZoneId.L3_RESPONSIVE_LONG_ZONE, VisionOpeningScenarioDirection.BULLISH, "Opening rejected bullish L3 plan"))

    if plan.camarilla_directional_prior in {VisionPivotDirectionalPrior.BEARISH, VisionPivotDirectionalPrior.MODERATELY_BEARISH}:
        if camarilla_location in {VisionOpeningCamarillaLocation.BELOW_L4, VisionOpeningCamarillaLocation.BETWEEN_L4_L3}:
            active.append(_zone(VisionOpeningActionZoneId.L3_PULLBACK_SHORT_ZONE, VisionOpeningScenarioDirection.BEARISH, "Opening accepted below L3"))
        elif camarilla_location is VisionOpeningCamarillaLocation.BETWEEN_L3_H3:
            active.append(_zone(VisionOpeningActionZoneId.H3_RESPONSIVE_SHORT_ZONE, VisionOpeningScenarioDirection.BEARISH, "Opening accepted inside L3-H3"))
        elif camarilla_location in {VisionOpeningCamarillaLocation.BETWEEN_H3_H4, VisionOpeningCamarillaLocation.ABOVE_H4} or bearish_invalid:
            inactive.append(_deactivated_zone(VisionOpeningActionZoneId.L3_PULLBACK_SHORT_ZONE, VisionOpeningScenarioDirection.BEARISH, "Opening rejected bearish L3 plan"))
            inactive.append(_deactivated_zone(VisionOpeningActionZoneId.H3_RESPONSIVE_SHORT_ZONE, VisionOpeningScenarioDirection.BEARISH, "Opening rejected bearish H3 plan"))

    if (
        plan.camarilla_relationship is VisionPivotRelationship.INSIDE_VALUE
        or plan.camarilla_width_state is VisionPivotWidthState.NARROW
        or scenario in {VisionOpeningScenario.BULLISH_BREAKOUT_WATCH, VisionOpeningScenario.BEARISH_BREAKOUT_WATCH}
    ):
        if scenario is VisionOpeningScenario.BULLISH_BREAKOUT_WATCH or (
            prior_location is VisionOpeningPriorRangeLocation.ABOVE_PRIOR_HIGH
            and camarilla_location is VisionOpeningCamarillaLocation.ABOVE_H4
        ):
            active.append(_zone(VisionOpeningActionZoneId.H4_BULLISH_BREAKOUT_WATCH_ZONE, VisionOpeningScenarioDirection.BULLISH, "Opening resolved inside/narrow plan upward"))
        elif scenario is VisionOpeningScenario.BEARISH_BREAKOUT_WATCH or (
            prior_location is VisionOpeningPriorRangeLocation.BELOW_PRIOR_LOW
            and camarilla_location is VisionOpeningCamarillaLocation.BELOW_L4
        ):
            active.append(_zone(VisionOpeningActionZoneId.L4_BEARISH_BREAKOUT_WATCH_ZONE, VisionOpeningScenarioDirection.BEARISH, "Opening resolved inside/narrow plan downward"))

    return _dedupe_zones(active), _dedupe_zones(inactive)


def _bullish_open(
    prior_location: VisionOpeningPriorRangeLocation,
    cpr_location: VisionOpeningCPRLocation,
    camarilla_location: VisionOpeningCamarillaLocation,
) -> bool:
    return (
        prior_location is VisionOpeningPriorRangeLocation.ABOVE_PRIOR_HIGH
        or cpr_location is VisionOpeningCPRLocation.ABOVE_CPR
        or camarilla_location in {VisionOpeningCamarillaLocation.ABOVE_H4, VisionOpeningCamarillaLocation.BETWEEN_H3_H4}
    )


def _bearish_open(
    prior_location: VisionOpeningPriorRangeLocation,
    cpr_location: VisionOpeningCPRLocation,
    camarilla_location: VisionOpeningCamarillaLocation,
) -> bool:
    return (
        prior_location is VisionOpeningPriorRangeLocation.BELOW_PRIOR_LOW
        or cpr_location is VisionOpeningCPRLocation.BELOW_CPR
        or camarilla_location in {VisionOpeningCamarillaLocation.BELOW_L4, VisionOpeningCamarillaLocation.BETWEEN_L4_L3}
    )


def _upside_breakout_open(
    prior_location: VisionOpeningPriorRangeLocation,
    camarilla_location: VisionOpeningCamarillaLocation,
) -> bool:
    return prior_location is VisionOpeningPriorRangeLocation.ABOVE_PRIOR_HIGH or camarilla_location is VisionOpeningCamarillaLocation.ABOVE_H4


def _downside_breakout_open(
    prior_location: VisionOpeningPriorRangeLocation,
    camarilla_location: VisionOpeningCamarillaLocation,
) -> bool:
    return prior_location is VisionOpeningPriorRangeLocation.BELOW_PRIOR_LOW or camarilla_location is VisionOpeningCamarillaLocation.BELOW_L4


def _resolved(
    acceptance: VisionOpeningAcceptanceState,
    scenario: VisionOpeningScenario,
    direction: VisionOpeningScenarioDirection,
    strength: VisionOpeningScenarioStrength,
    supporting: list[str],
    contradicting: list[str],
    warnings: list[str],
):
    return (
        acceptance,
        scenario,
        direction,
        strength,
        _normalize_unique_text_tuple(tuple(supporting), "supporting_reasons"),
        _normalize_unique_text_tuple(tuple(contradicting), "contradicting_reasons") if contradicting else (),
        _normalize_unique_text_tuple(tuple(warnings), "warnings") if warnings else (),
    )


def _zone(zone_id: VisionOpeningActionZoneId, direction: VisionOpeningScenarioDirection, reason: str) -> VisionOpeningActionZone:
    return VisionOpeningActionZone(zone_id, VisionOpeningActionZoneState.ACTIVE, direction, "VPM_OPENING_1", reason)


def _deactivated_zone(zone_id: VisionOpeningActionZoneId, direction: VisionOpeningScenarioDirection, reason: str) -> VisionOpeningActionZone:
    return VisionOpeningActionZone(zone_id, VisionOpeningActionZoneState.DEACTIVATED, direction, "VPM_OPENING_1", reason)


def _dedupe_zones(zones: list[VisionOpeningActionZone]) -> tuple[VisionOpeningActionZone, ...]:
    result: list[VisionOpeningActionZone] = []
    seen: set[VisionOpeningActionZoneId] = set()
    for zone in zones:
        if zone.zone_id in seen:
            continue
        seen.add(zone.zone_id)
        result.append(zone)
    return tuple(result)


def _flight_plan_reference(plan: VisionPivotFlightPlan) -> str:
    return f"VisionPivotFlightPlan:{plan.instrument.value}:{plan.trading_date.isoformat()}:{plan.reference_session_date.isoformat()}"


def _normalize_zones(values: tuple[VisionOpeningActionZone, ...], field_name: str) -> tuple[VisionOpeningActionZone, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple.")
    seen: set[VisionOpeningActionZoneId] = set()
    for value in values:
        if not isinstance(value, VisionOpeningActionZone):
            raise TypeError(f"{field_name} must contain VisionOpeningActionZone values.")
        if value.zone_id in seen:
            raise ValueError(f"{field_name} contains duplicate zone ids.")
        seen.add(value.zone_id)
    return values


def _normalize_unique_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple.")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_text(value, field_name)
        key = normalized.casefold()
        if key in seen:
            raise ValueError(f"{field_name} cannot contain duplicate values.")
        seen.add(key)
        result.append(normalized)
    return tuple(result)


def _require_enum(value, expected_type, field_name: str) -> None:
    if not isinstance(value, expected_type):
        raise TypeError(f"{field_name} must be {expected_type.__name__}.")


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text.")
    return value.strip()


def _positive_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    normalized = float(value)
    if normalized != normalized or normalized in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite.")
    if normalized <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return normalized


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
