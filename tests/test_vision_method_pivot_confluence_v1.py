from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from application.enums import RuntimeInstrument, RuntimeStatus
from application.models import RuntimeSnapshot
from core.enums.timeframe import TimeFrame
from engines.vision_method import (
    VisionADRContext,
    VisionBOS,
    VisionBreakerBlock,
    VisionBreakerBlockState,
    VisionBreakDirection,
    VisionBreakStrength,
    VisionCHoCH,
    VisionCPRContext,
    VisionCPRRelation,
    VisionCamarillaContext,
    VisionCamarillaZone,
    VisionCandidateState,
    VisionFairValueGap,
    VisionFairValueGapDirection,
    VisionGapType,
    VisionLevelContext,
    VisionLevelQuality,
    VisionLiquidityContext,
    VisionLiquidityLevel,
    VisionLiquidityPool,
    VisionLiquiditySweep,
    VisionMethodCalculationRequest,
    VisionMitigationState,
    VisionMSS,
    VisionOpeningAcceptanceState,
    VisionOpeningActionZone,
    VisionOpeningActionZoneId,
    VisionOpeningActionZoneState,
    VisionOpeningCPRLocation,
    VisionOpeningCamarillaLocation,
    VisionOpeningGapState,
    VisionOpeningPivotValueLocation,
    VisionOpeningPriorRangeLocation,
    VisionOpeningRangeContext,
    VisionOpeningRangeState,
    VisionOpeningScenario,
    VisionOpeningScenarioDirection,
    VisionOpeningScenarioStrength,
    VisionOptionConfirmation,
    VisionOptionConfirmationContext,
    VisionPivotCombinedContext,
    VisionPivotConfluenceConfiguration,
    VisionPivotConfluenceContext,
    VisionPivotConfluenceRequest,
    VisionPivotDirectionalPrior,
    VisionPivotFlightPlan,
    VisionPivotPriceRelation,
    VisionPivotReferenceFamily,
    VisionPivotReferenceKind,
    VisionPivotRelationship,
    VisionPivotTendency,
    VisionPivotWidthState,
    VisionPivotZoneAlignment,
    VisionPivotZoneDirectionalRole,
    VisionPivotZoneQuality,
    VisionPivotZoneStatus,
    VisionPivotZoneType,
    VisionPreviousDayContext,
    VisionPreviousDayRelation,
    VisionRangeLocation,
    VisionReversalState,
    VisionScenarioStatus,
    VisionSetupQualificationContext,
    VisionSetupQuality,
    VisionSetupType,
    VisionStructureContext,
    VisionStructureEventContext,
    VisionStructureEventPhase,
    VisionStructurePattern,
    VisionStructureTrend,
    VisionSweepDirection,
    VisionSwingPoint,
    VisionSwingType,
    VisionVWAPContext,
    VisionVWAPRelation,
    build_pivot_confluence_context,
    calculate_vision_method_snapshot,
)
from tests.test_vision_method_calculator_v1 import trigger
from desktop.vision_method.vision_method_inspector import _pivot_confluence_values
from application.vision_forensics import _pivot_confluence_payload


IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 7, 29, 10, 0, tzinfo=IST)
OPEN_START = datetime(2026, 7, 29, 9, 15, tzinfo=IST)
OPEN_END = datetime(2026, 7, 29, 9, 30, tzinfo=IST)


def previous_day(high: float = 120.0, low: float = 80.0, close: float = 100.0) -> VisionPreviousDayContext:
    return VisionPreviousDayContext(
        previous_high=high,
        previous_low=low,
        previous_close=close,
        virgin_cpr=False,
        distance_previous_high=high - 100.0,
        distance_previous_low=100.0 - low,
        previous_day_relation=VisionPreviousDayRelation.INSIDE_PREVIOUS_RANGE,
        gap_type=VisionGapType.NO_GAP,
    )


def level(
    *,
    cpr: tuple[float, float, float] = (99.0, 100.0, 99.5),
    cama: tuple[float, float, float, float, float, float, float, float] = (100.05, 102.0, 104.0, 106.0, 90.05, 88.0, 86.0, 84.0),
    prior: VisionPreviousDayContext | None = None,
    vwap_price: float | None = None,
) -> VisionLevelContext:
    h3, h4, h5, h6, l3, l4, l5, l6 = cama
    return VisionLevelContext(
        cpr_context=VisionCPRContext(VisionCPRRelation.ABOVE_CPR, cpr[0], cpr[1], cpr[2], abs(cpr[1] - cpr[0]), 1.0),
        camarilla_context=VisionCamarillaContext(VisionCamarillaZone.H3_H4, h3, h4, h5, h6, l3, l4, l5, l6),
        previous_day_context=prior or previous_day(),
        adr_context=VisionADRContext(32.0, 68.0, False, False, "normal", "normal"),
        vwap_context=VisionVWAPContext(VisionVWAPRelation.RETEST, vwap_price, 0.0, 0.0) if vwap_price is not None else None,
        quality=VisionLevelQuality.FULL,
    )


def opening(high: float = 102.04, low: float = 90.04) -> VisionOpeningRangeContext:
    return VisionOpeningRangeContext(
        opening_start_time=OPEN_START,
        opening_end_time=OPEN_END,
        opening_high=high,
        opening_low=low,
        opening_width=high - low,
        range_complete=True,
        current_location=VisionRangeLocation.INSIDE_RANGE,
        break_direction=VisionBreakDirection.NONE,
        retest_state=VisionOpeningRangeState.INSIDE_RANGE,
        false_break=False,
        elapsed_minutes=15,
        quality=VisionLevelQuality.FULL,
    )


def swing(price: float, type_: VisionSwingType, index: int) -> VisionSwingPoint:
    return VisionSwingPoint(price, OPEN_START + timedelta(minutes=index), index, 2, type_)


def structure(high: float = 102.03, low: float = 90.03) -> VisionStructureContext:
    return VisionStructureContext(
        current_swing_high=swing(high, VisionSwingType.HIGH, 10),
        current_swing_low=swing(low, VisionSwingType.LOW, 11),
        previous_swing_high=swing(high - 5.0, VisionSwingType.HIGH, 1),
        previous_swing_low=swing(low - 5.0, VisionSwingType.LOW, 2),
        trend=VisionStructureTrend.BULLISH,
        structure_state=VisionStructurePattern.HH,
        last_confirmed_swing=swing(high, VisionSwingType.HIGH, 10),
        quality=VisionLevelQuality.FULL,
    )


def liquidity(*, equal_high: float | None = None, equal_low: float | None = None, swept: VisionLiquiditySweep = VisionLiquiditySweep.NONE) -> VisionLiquidityContext:
    equal_highs = (
        VisionLiquidityLevel(equal_high, OPEN_START, OPEN_START + timedelta(minutes=5), (1, 2), VisionSwingType.HIGH, 0.0005),
    ) if equal_high is not None else ()
    equal_lows = (
        VisionLiquidityLevel(equal_low, OPEN_START, OPEN_START + timedelta(minutes=5), (3, 4), VisionSwingType.LOW, 0.0005),
    ) if equal_low is not None else ()
    pool = VisionLiquidityPool.NONE
    direction = VisionSweepDirection.NONE
    if equal_highs:
        pool = VisionLiquidityPool.BUY_SIDE
    if equal_lows:
        pool = VisionLiquidityPool.SELL_SIDE
    if swept is VisionLiquiditySweep.BUY_SIDE_SWEEP:
        direction = VisionSweepDirection.BUY_SIDE
    if swept is VisionLiquiditySweep.SELL_SIDE_SWEEP:
        direction = VisionSweepDirection.SELL_SIDE
    return VisionLiquidityContext(
        equal_highs=equal_highs,
        equal_lows=equal_lows,
        liquidity_pool=pool,
        liquidity_sweep=swept,
        sweep_direction=direction,
        fair_value_gap=VisionFairValueGap(
            VisionFairValueGapDirection.BULLISH,
            OPEN_START,
            OPEN_START + timedelta(minutes=10),
            90.02,
            90.08,
            (1, 2, 3),
        ),
        order_block=None,
        breaker_block=VisionBreakerBlock(VisionBreakerBlockState.NOT_EVALUATED),
        mitigation=VisionMitigationState.NOT_EVALUATED,
        quality=VisionLevelQuality.FULL,
    )


def plan(prior: VisionPivotDirectionalPrior = VisionPivotDirectionalPrior.BULLISH) -> VisionPivotFlightPlan:
    return VisionPivotFlightPlan(
        instrument=RuntimeInstrument.NIFTY,
        trading_date=NOW.date(),
        reference_session_date=NOW.date() - timedelta(days=1),
        generated_at=NOW,
        cpr_relationship=VisionPivotRelationship.HIGHER_VALUE,
        cpr_width_state=VisionPivotWidthState.NORMAL,
        cpr_width_value=1.0,
        cpr_directional_prior=prior,
        camarilla_relationship=VisionPivotRelationship.HIGHER_VALUE,
        camarilla_width_state=VisionPivotWidthState.NORMAL,
        camarilla_width_value=10.0,
        camarilla_directional_prior=prior,
        combined_context_state=VisionPivotCombinedContext.BULLISH_ALIGNED if prior is VisionPivotDirectionalPrior.BULLISH else VisionPivotCombinedContext.BEARISH_ALIGNED,
        combined_directional_prior=prior,
        expansion_tendency=VisionPivotTendency.MODERATE,
        balance_tendency=VisionPivotTendency.LOW,
        preferred_bullish_action_zones=(),
        preferred_bearish_action_zones=(),
        bullish_scenario="provisional",
        bearish_scenario="provisional",
        neutral_or_breakout_scenario="provisional",
        scenario_status=VisionScenarioStatus.OPENING_CONFIRMATION_REQUIRED,
        opening_confirmation_required=True,
        supporting_reasons=("Pivot plan ready",),
        conflicting_reasons=(),
        warnings=(),
    )


def assessment(scenario: VisionOpeningScenario = VisionOpeningScenario.BULLISH_CONTINUATION) -> object:
    direction = VisionOpeningScenarioDirection.BULLISH
    if scenario in {VisionOpeningScenario.BEARISH_CONTINUATION, VisionOpeningScenario.BEARISH_BREAKOUT_WATCH}:
        direction = VisionOpeningScenarioDirection.BEARISH
    if scenario is VisionOpeningScenario.BALANCE_RANGE:
        direction = VisionOpeningScenarioDirection.NEUTRAL
    return __import__("engines.vision_method", fromlist=["VisionPivotOpeningAssessment"]).VisionPivotOpeningAssessment(
        instrument=RuntimeInstrument.NIFTY,
        trading_date=NOW.date(),
        flight_plan_reference="test-plan",
        opening_price=100.0,
        opening_timestamp=OPEN_START,
        prior_range_location=VisionOpeningPriorRangeLocation.INSIDE_PRIOR_RANGE,
        pivot_value_location=VisionOpeningPivotValueLocation.IN_RANGE_IN_VALUE,
        cpr_location=VisionOpeningCPRLocation.ABOVE_CPR,
        camarilla_location=VisionOpeningCamarillaLocation.BETWEEN_H3_H4,
        gap_state=VisionOpeningGapState.NO_MEANINGFUL_GAP,
        pre_market_context=VisionPivotCombinedContext.BULLISH_ALIGNED,
        pre_market_directional_prior=VisionPivotDirectionalPrior.BULLISH,
        opening_acceptance_state=VisionOpeningAcceptanceState.ACCEPTED,
        active_scenario=scenario,
        scenario_direction=direction,
        scenario_strength=VisionOpeningScenarioStrength.STRONG,
        activated_action_zones=(
            VisionOpeningActionZone(
                VisionOpeningActionZoneId.H3_PULLBACK_LONG_ZONE,
                VisionOpeningActionZoneState.ACTIVE,
                direction,
                "test",
                "test zone",
            ),
        ),
        deactivated_action_zones=(),
        supporting_reasons=("Opening accepted",),
        contradicting_reasons=(),
        warnings=(),
        assessment_complete=True,
    )


def request(**overrides) -> VisionPivotConfluenceRequest:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "trading_date": NOW.date(),
        "timestamp": NOW,
        "current_price": 100.0,
        "level_context": level(),
        "opening_range_context": opening(),
        "structure_context": structure(),
        "liquidity_context": liquidity(equal_high=102.02, equal_low=90.02),
        "pivot_flight_plan": plan(),
        "pivot_opening_assessment": assessment(),
    }
    values.update(overrides)
    return VisionPivotConfluenceRequest(**values)


def test_cpr_h3_creates_resistance_hot_zone_without_trade_signal():
    context = build_pivot_confluence_context(request())

    zone = next(
        item
        for item in context.hot_zones
        if VisionPivotReferenceKind.CAMARILLA_H3 in {member.kind for member in item.member_references}
        and VisionPivotReferenceFamily.CPR in item.reference_families
    )
    assert zone.directional_role is VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE
    assert zone.zone_type is VisionPivotZoneType.RESISTANCE_HOT_ZONE
    assert zone.independent_family_count >= 2
    assert {member.kind for member in zone.member_references} & {VisionPivotReferenceKind.CAMARILLA_H3}
    assert context.quality in {VisionLevelQuality.FULL, VisionLevelQuality.PARTIAL}


def test_cpr_l3_creates_bullish_support_hot_zone():
    context = build_pivot_confluence_context(
        request(
            current_price=90.0,
            level_context=level(cpr=(90.0, 91.0, 90.5), cama=(103.0, 104.0, 105.0, 106.0, 90.05, 88.0, 86.0, 84.0)),
            pivot_opening_assessment=assessment(VisionOpeningScenario.BULLISH_CONTINUATION),
        )
    )

    zone = next(item for item in context.hot_zones if item.directional_role is VisionPivotZoneDirectionalRole.BULLISH_SUPPORT)
    assert zone.zone_type is VisionPivotZoneType.SUPPORT_HOT_ZONE
    assert zone.current_price_relation in {VisionPivotPriceRelation.INSIDE, VisionPivotPriceRelation.APPROACHING}


def test_same_family_members_do_not_create_confluence():
    context = build_pivot_confluence_context(
        request(
            level_context=level(cpr=(70.0, 71.0, 70.5), cama=(100.0, 100.05, 100.1, 100.15, 60.0, 59.0, 58.0, 57.0), prior=previous_day(130, 50, 90)),
            opening_range_context=None,
            structure_context=None,
            liquidity_context=None,
            pivot_flight_plan=None,
            pivot_opening_assessment=None,
        )
    )

    assert context.hot_zones == ()
    assert context.quality is VisionLevelQuality.INSUFFICIENT


def test_prior_high_opening_range_structure_and_liquidity_rank_as_breakout_zone():
    context = build_pivot_confluence_context(
        request(
            current_price=102.03,
            level_context=level(prior=previous_day(102.04, 80.0, 95.0), cama=(100.0, 102.02, 104.0, 106.0, 90.0, 88.0, 86.0, 84.0), vwap_price=102.01),
            opening_range_context=opening(high=102.04, low=90.0),
            structure_context=structure(high=102.03, low=89.5),
            liquidity_context=liquidity(equal_high=102.02),
            pivot_opening_assessment=assessment(VisionOpeningScenario.BULLISH_BREAKOUT_WATCH),
        )
    )

    zone = context.hot_zones[0]
    assert zone.directional_role in {VisionPivotZoneDirectionalRole.BREAKOUT_UPSIDE, VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE}
    assert zone.independent_family_count >= 3
    assert zone.active_scenario_alignment in {VisionPivotZoneAlignment.ALIGNED, VisionPivotZoneAlignment.PARTIAL}
    assert zone.quality in {VisionPivotZoneQuality.HIGH, VisionPivotZoneQuality.VERY_HIGH}


def test_consumed_liquidity_does_not_improperly_boost_zone_quality():
    context = build_pivot_confluence_context(
        request(liquidity_context=liquidity(equal_high=100.04, swept=VisionLiquiditySweep.BUY_SIDE_SWEEP))
    )

    consumed = [zone for zone in context.hot_zones if any(member.status is VisionPivotZoneStatus.CONSUMED for member in zone.member_references)]
    assert consumed
    assert all(zone.quality is VisionPivotZoneQuality.LOW for zone in consumed)
    assert all("Consumed liquidity" in " ".join(zone.warnings) for zone in consumed)


def test_confluence_is_immutable_and_rejects_mismatched_contracts():
    context = build_pivot_confluence_context(request())

    with pytest.raises(FrozenInstanceError):
        context.hot_zones = ()
    with pytest.raises(ValueError, match="trading date mismatch"):
        VisionPivotConfluenceContext(
            instrument=RuntimeInstrument.NIFTY,
            timeframe=TimeFrame.FIVE_MINUTES,
            trading_date=NOW.date() - timedelta(days=1),
            timestamp=NOW,
            hot_zones=context.hot_zones,
            top_bullish_interest_zones=(),
            top_bearish_interest_zones=(),
            top_breakout_decision_zones=(),
            top_neutral_or_target_zones=(),
            quality=VisionLevelQuality.FULL,
            status=VisionPivotZoneStatus.ACTIVE,
            warnings=(),
        )


def test_calculator_carries_confluence_without_changing_candidate_state():
    confluence = build_pivot_confluence_context(request())
    base = calculate_vision_method_snapshot(method_request())
    with_confluence = calculate_vision_method_snapshot(method_request(pivot_confluence_context=confluence))

    assert with_confluence.candidate_state is base.candidate_state
    assert with_confluence.pivot_confluence_context is confluence
    assert any(reason.startswith("Pivot confluence") for reason in with_confluence.supporting_reasons)


def test_runtime_snapshot_inspector_and_forensics_expose_confluence(tmp_path):
    confluence = build_pivot_confluence_context(request())
    runtime = RuntimeSnapshot(
        symbol=RuntimeInstrument.NIFTY,
        timeframe=TimeFrame.FIVE_MINUTES.value,
        status=RuntimeStatus.RUNNING,
        latest_tick=None,
        latest_candle=None,
        vwap=None,
        cpr=None,
        camarilla=None,
        price_action=None,
        option_chain=None,
        market_context=None,
        ai_reasoning=None,
        strategy=None,
        risk=None,
        latest_order=None,
        position=None,
        latest_journal_record=None,
        updated_at=NOW,
        pivot_confluence_context=confluence,
    )
    assert runtime.pivot_confluence_context is confluence

    values = _pivot_confluence_values(confluence)
    assert values["Top Hot Zone"] != "none"
    assert values["Hot Zone Families"] != "none"

    payload = _pivot_confluence_payload(confluence)
    assert payload is not None
    assert payload["zones"]
    assert payload["zones"][0]["member_references"]


def method_request(**overrides) -> VisionMethodCalculationRequest:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "timestamp": NOW,
        "level_context": level(),
        "opening_range_context": opening(),
        "structure_context": structure(),
        "liquidity_context": liquidity(equal_high=102.02, equal_low=90.02),
        "structure_event_context": VisionStructureEventContext(
            bos=VisionBOS.BULLISH_BOS,
            choch=VisionCHoCH.NONE,
            mss=VisionMSS.NONE,
            continuation=VisionStructureEventPhase.CONTINUATION,
            reversal=VisionReversalState.NONE,
            break_strength=VisionBreakStrength.STRONG,
            quality=VisionLevelQuality.FULL,
        ),
        "setup_qualification_context": VisionSetupQualificationContext(
            setup_type=VisionSetupType.TREND_CONTINUATION,
            setup_quality=VisionSetupQuality.HIGH,
            blocking_reasons=(),
            supporting_reasons=("Above CPR", "Above H3", "Bullish BOS"),
            eligible_for_option_confirmation=True,
        ),
        "option_confirmation_context": VisionOptionConfirmationContext(
            confirmation_state=VisionOptionConfirmation.CONFIRMS,
            supporting_factors=("Put writing supports setup",),
            contradicting_factors=(),
            neutral_factors=(),
            quality=VisionLevelQuality.FULL,
            timestamp=NOW,
        ),
        "price_action_trigger_context": trigger(timestamp=NOW),
        "current_price": 100.0,
    }
    values.update(overrides)
    return VisionMethodCalculationRequest(**values)
