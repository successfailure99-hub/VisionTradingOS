from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from application.enums import RuntimeInstrument
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
    VisionChaseRisk,
    VisionLevelContext,
    VisionLevelQuality,
    VisionLiquidityContext,
    VisionLiquidityLevel,
    VisionLiquidityPool,
    VisionLiquiditySweep,
    VisionMethodCalculationRequest,
    VisionMitigationState,
    VisionMSS,
    VisionOpeningRangeContext,
    VisionOpeningRangeState,
    VisionOptionConfirmation,
    VisionOptionConfirmationContext,
    VisionPreviousDayContext,
    VisionPreviousDayRelation,
    VisionRangeLocation,
    VisionReversalState,
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
    VisionCandidateState,
    VisionDirectionQuality,
    VisionEntryLocationState,
    VisionCandlestickPattern,
    VisionMoveMaturity,
    VisionPivotZoneDirectionalRole,
    VisionPivotZoneQuality,
    VisionPriceActionTrigger,
    VisionPriceActionTriggerContext,
    VisionTriggerAcceptanceState,
    VisionTriggerAlignment,
    VisionTriggerBreakState,
    VisionTriggerDirection,
    VisionTriggerInteractionState,
    VisionTriggerQuality,
    VisionTriggerRetestState,
    VisionTriggerType,
    calculate_vision_method_snapshot,
)


IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 7, 29, 10, 30, tzinfo=IST)
OPEN_START = datetime(2026, 7, 29, 9, 15, tzinfo=IST)
OPEN_END = datetime(2026, 7, 29, 9, 30, tzinfo=IST)


def previous_day() -> VisionPreviousDayContext:
    return VisionPreviousDayContext(
        previous_high=110.0,
        previous_low=90.0,
        previous_close=100.0,
        virgin_cpr=False,
        distance_previous_high=-5.0,
        distance_previous_low=15.0,
        previous_day_relation=VisionPreviousDayRelation.INSIDE_PREVIOUS_RANGE,
    )


def level(
    *,
    cpr: VisionCPRRelation = VisionCPRRelation.ABOVE_CPR,
    zone: VisionCamarillaZone = VisionCamarillaZone.H3_H4,
    vwap: VisionVWAPRelation = VisionVWAPRelation.ABOVE_VWAP,
    adr_used: float = 32.0,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionLevelContext:
    return VisionLevelContext(
        cpr_context=VisionCPRContext(cpr, 99.0, 101.0, 100.0, 2.0, 2.0),
        camarilla_context=VisionCamarillaContext(zone, 103.0, 104.0, 105.0, 106.0, 97.0, 96.0, 95.0, 94.0),
        previous_day_context=previous_day(),
        adr_context=VisionADRContext(adr_used, max(0.0, 100.0 - adr_used), False, False, "normal", "normal"),
        vwap_context=VisionVWAPContext(vwap, 100.0, 1.0, 1.0),
        quality=quality,
    )


def opening(
    *,
    complete: bool = True,
    state: VisionOpeningRangeState = VisionOpeningRangeState.BREAK_ABOVE,
    direction: VisionBreakDirection = VisionBreakDirection.UP,
    location: VisionRangeLocation = VisionRangeLocation.ABOVE_RANGE,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionOpeningRangeContext:
    return VisionOpeningRangeContext(
        opening_start_time=OPEN_START,
        opening_end_time=OPEN_END,
        opening_high=102.0,
        opening_low=99.0,
        opening_width=3.0,
        range_complete=complete,
        current_location=location,
        break_direction=direction,
        retest_state=state,
        false_break=state is VisionOpeningRangeState.FALSE_BREAK,
        elapsed_minutes=15 if complete else 10,
        quality=quality,
    )


def swing(price: float, index: int, type_: VisionSwingType) -> VisionSwingPoint:
    return VisionSwingPoint(price, OPEN_START + timedelta(minutes=5 * index), index, 4, type_)


def structure(
    *,
    trend: VisionStructureTrend = VisionStructureTrend.BULLISH,
    pattern: VisionStructurePattern = VisionStructurePattern.HH,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionStructureContext:
    return VisionStructureContext(
        current_swing_high=swing(110.0, 5, VisionSwingType.HIGH),
        current_swing_low=swing(100.0, 6, VisionSwingType.LOW),
        previous_swing_high=swing(105.0, 1, VisionSwingType.HIGH),
        previous_swing_low=swing(95.0, 2, VisionSwingType.LOW),
        trend=trend,
        structure_state=pattern,
        last_confirmed_swing=swing(110.0, 5, VisionSwingType.HIGH),
        quality=quality,
    )


def liquidity(
    *,
    sweep: VisionLiquiditySweep = VisionLiquiditySweep.NONE,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionLiquidityContext:
    equal_highs = ()
    pool = VisionLiquidityPool.NONE
    direction = VisionSweepDirection.NONE
    if sweep is VisionLiquiditySweep.BUY_SIDE_SWEEP:
        equal_highs = (VisionLiquidityLevel(110.0, OPEN_START, OPEN_START + timedelta(minutes=5), (0, 1), VisionSwingType.HIGH, 0.0005),)
        pool = VisionLiquidityPool.BUY_SIDE
        direction = VisionSweepDirection.BUY_SIDE
    return VisionLiquidityContext(
        equal_highs=equal_highs,
        equal_lows=(),
        liquidity_pool=pool,
        liquidity_sweep=sweep,
        sweep_direction=direction,
        fair_value_gap=None,
        order_block=None,
        breaker_block=VisionBreakerBlock(VisionBreakerBlockState.NOT_EVALUATED),
        mitigation=VisionMitigationState.NOT_EVALUATED,
        quality=quality,
    )


def event(
    *,
    bos: VisionBOS = VisionBOS.BULLISH_BOS,
    choch: VisionCHoCH = VisionCHoCH.NONE,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionStructureEventContext:
    if choch is not VisionCHoCH.NONE:
        return VisionStructureEventContext(
            bos=VisionBOS.NONE,
            choch=choch,
            mss=VisionMSS.MARKET_STRUCTURE_SHIFT,
            continuation=VisionStructureEventPhase.REVERSAL,
            reversal=VisionReversalState.BULLISH_REVERSAL if choch is VisionCHoCH.BULLISH_CHOCH else VisionReversalState.BEARISH_REVERSAL,
            break_strength=VisionBreakStrength.STRONG,
            quality=quality,
        )
    return VisionStructureEventContext(
        bos=bos,
        choch=VisionCHoCH.NONE,
        mss=VisionMSS.NONE,
        continuation=VisionStructureEventPhase.CONTINUATION if bos is not VisionBOS.NONE else VisionStructureEventPhase.NONE,
        reversal=VisionReversalState.NONE,
        break_strength=VisionBreakStrength.STRONG if bos is not VisionBOS.NONE else VisionBreakStrength.NONE,
        quality=quality,
    )


def setup(
    *,
    setup_type: VisionSetupType = VisionSetupType.TREND_CONTINUATION,
    quality: VisionSetupQuality = VisionSetupQuality.HIGH,
    supporting: tuple[str, ...] = ("Above CPR", "Above H3", "Bullish BOS"),
    blocking: tuple[str, ...] = (),
    eligible: bool = True,
) -> VisionSetupQualificationContext:
    return VisionSetupQualificationContext(
        setup_type=setup_type,
        setup_quality=quality,
        blocking_reasons=blocking,
        supporting_reasons=supporting,
        eligible_for_option_confirmation=eligible,
    )


def option(
    *,
    state: VisionOptionConfirmation = VisionOptionConfirmation.CONFIRMS,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
    supporting: tuple[str, ...] = ("Put writing supports setup",),
    contradicting: tuple[str, ...] = (),
    neutral: tuple[str, ...] = (),
    timestamp: datetime = NOW,
) -> VisionOptionConfirmationContext:
    if state is VisionOptionConfirmation.CONTRADICTS and not contradicting:
        contradicting = ("Call writing contradicts setup",)
        supporting = ()
    if state is VisionOptionConfirmation.PARTIAL and not contradicting:
        contradicting = ("Option analytics bias bearish",)
    if state is VisionOptionConfirmation.NEUTRAL and not neutral:
        neutral = ("Option analytics bias neutral",)
        supporting = ()
    if state is VisionOptionConfirmation.UNAVAILABLE:
        quality = VisionLevelQuality.INSUFFICIENT
        supporting = ()
        neutral = ("Option chain unavailable",)
    return VisionOptionConfirmationContext(
        confirmation_state=state,
        supporting_factors=supporting,
        contradicting_factors=contradicting,
        neutral_factors=neutral,
        quality=quality,
        timestamp=timestamp,
    )


def trigger(
    *,
    direction: VisionTriggerDirection = VisionTriggerDirection.BULLISH,
    trigger_type: VisionTriggerType = VisionTriggerType.BULLISH_INITIATIVE_BREAKOUT,
    quality: VisionTriggerQuality = VisionTriggerQuality.HIGH,
    interaction: VisionTriggerInteractionState = VisionTriggerInteractionState.ACCEPTED,
    timestamp: datetime = NOW,
) -> VisionPriceActionTriggerContext:
    return VisionPriceActionTriggerContext(
        instrument=RuntimeInstrument.NIFTY,
        trading_date=timestamp.date(),
        timeframe=TimeFrame.FIVE_MINUTES,
        timestamp=timestamp,
        trigger=VisionPriceActionTrigger(
            instrument=RuntimeInstrument.NIFTY,
            trading_date=timestamp.date(),
            timeframe=TimeFrame.FIVE_MINUTES,
            decision_timestamp=timestamp,
            zone_reference="H3-H4",
            zone_role=VisionPivotZoneDirectionalRole.BULLISH_SUPPORT
            if direction is VisionTriggerDirection.BULLISH
            else VisionPivotZoneDirectionalRole.BEARISH_RESISTANCE,
            zone_quality=VisionPivotZoneQuality.HIGH,
            interaction_state=interaction,
            trigger_type=trigger_type,
            trigger_direction=direction,
            trigger_quality=quality,
            break_state=VisionTriggerBreakState.BROKEN_UP
            if direction is VisionTriggerDirection.BULLISH
            else VisionTriggerBreakState.BROKEN_DOWN,
            acceptance_state=VisionTriggerAcceptanceState.ACCEPTED_UP
            if direction is VisionTriggerDirection.BULLISH
            else VisionTriggerAcceptanceState.ACCEPTED_DOWN,
            retest_state=VisionTriggerRetestState.NONE,
            candlestick_pattern=VisionCandlestickPattern.NONE,
            structure_alignment=VisionTriggerAlignment.ALIGNED,
            liquidity_alignment=VisionTriggerAlignment.SUPPORTING,
            opening_range_alignment=VisionTriggerAlignment.ALIGNED,
            scenario_alignment=VisionTriggerAlignment.ALIGNED,
            supporting_reasons=("Accepted price-action trigger",),
            contradicting_reasons=(),
            warnings=(),
            blocking_reasons=(),
            source_candle_reference="2026-07-29T10:30:00+05:30",
            prior_event_reference="none",
        ),
        event_history=(),
        quality=VisionLevelQuality.FULL,
        status=interaction,
        warnings=(),
    )


def request(**overrides) -> VisionMethodCalculationRequest:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "timestamp": NOW,
        "level_context": level(),
        "opening_range_context": opening(),
        "structure_context": structure(),
        "liquidity_context": liquidity(),
        "structure_event_context": event(),
        "setup_qualification_context": setup(),
        "option_confirmation_context": option(),
        "price_action_trigger_context": trigger(),
    }
    values.update(overrides)
    return VisionMethodCalculationRequest(**values)


def test_complete_bullish_methodology_produces_long_eligible_high_quality_snapshot():
    result = calculate_vision_method_snapshot(request())

    assert result.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert result.quality == "high"
    assert result.opening_range_context.range_complete is True
    assert result.setup_qualification_context.setup_type is VisionSetupType.TREND_CONTINUATION
    assert result.option_confirmation_context.confirmation_state is VisionOptionConfirmation.CONFIRMS
    assert result.entry_location_context.direction == "bullish"
    assert result.entry_location_context.direction_quality is VisionDirectionQuality.HIGH
    assert result.entry_location_context.entry_location_state is VisionEntryLocationState.ACCEPTABLE
    assert "Above CPR" in result.supporting_reasons
    assert "Put writing supports setup" in result.supporting_reasons


def test_complete_bearish_methodology_produces_short_eligible_snapshot():
    result = calculate_vision_method_snapshot(
        request(
            level_context=level(cpr=VisionCPRRelation.BELOW_CPR, zone=VisionCamarillaZone.L3_L4, vwap=VisionVWAPRelation.BELOW_VWAP),
            opening_range_context=opening(state=VisionOpeningRangeState.BREAK_BELOW, direction=VisionBreakDirection.DOWN, location=VisionRangeLocation.BELOW_RANGE),
            structure_context=structure(trend=VisionStructureTrend.BEARISH, pattern=VisionStructurePattern.LL),
            structure_event_context=event(bos=VisionBOS.BEARISH_BOS),
            setup_qualification_context=setup(supporting=("Below CPR", "Below L3", "Bearish BOS")),
            option_confirmation_context=option(supporting=("Call writing supports setup",)),
            price_action_trigger_context=trigger(
                direction=VisionTriggerDirection.BEARISH,
                trigger_type=VisionTriggerType.BEARISH_INITIATIVE_BREAKOUT,
            ),
        )
    )

    assert result.candidate_state is VisionCandidateState.SHORT_ELIGIBLE
    assert result.quality == "high"
    assert "Bearish BOS" in result.supporting_reasons
    assert "Call writing supports setup" in result.supporting_reasons


def test_observe_wait_prepare_avoid_and_insufficient_states_are_deterministic():
    observe = calculate_vision_method_snapshot(
        request(
            setup_qualification_context=setup(
                setup_type=VisionSetupType.RANGE_FADE,
                quality=VisionSetupQuality.MEDIUM,
                supporting=("Inside CPR",),
                eligible=True,
            ),
            option_confirmation_context=option(state=VisionOptionConfirmation.NEUTRAL),
        )
    )
    assert observe.candidate_state is VisionCandidateState.OBSERVE

    wait = calculate_vision_method_snapshot(
        request(
            opening_range_context=opening(
                complete=False,
                state=VisionOpeningRangeState.WAITING,
                direction=VisionBreakDirection.NONE,
                location=VisionRangeLocation.INSIDE_RANGE,
                quality=VisionLevelQuality.PARTIAL,
            )
        )
    )
    assert wait.candidate_state is VisionCandidateState.WAIT

    prepare = calculate_vision_method_snapshot(request(option_confirmation_context=option(state=VisionOptionConfirmation.PARTIAL)))
    assert prepare.candidate_state is VisionCandidateState.PREPARE_LONG
    assert prepare.quality == "medium"

    contradicted = calculate_vision_method_snapshot(request(option_confirmation_context=option(state=VisionOptionConfirmation.CONTRADICTS)))
    assert contradicted.candidate_state is VisionCandidateState.PREPARE_LONG
    assert contradicted.quality == "low"
    assert contradicted.blocking_reasons == ()
    assert "Option contradiction: Call writing contradicts setup" in contradicted.supporting_reasons

    insufficient = calculate_vision_method_snapshot(request(option_confirmation_context=option(state=VisionOptionConfirmation.UNAVAILABLE)))
    assert insufficient.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert insufficient.quality == "low"
    assert insufficient.blocking_reasons == ()


def test_supporting_evidence_never_blocks_candidate_evaluation():
    missing_liquidity = calculate_vision_method_snapshot(
        request(liquidity_context=liquidity(quality=VisionLevelQuality.INSUFFICIENT))
    )
    assert missing_liquidity.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert missing_liquidity.quality == "low"
    assert missing_liquidity.blocking_reasons == ()

    missing_option = calculate_vision_method_snapshot(request(option_confirmation_context=option(state=VisionOptionConfirmation.UNAVAILABLE)))
    assert missing_option.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert missing_option.blocking_reasons == ()


def test_neutral_or_unavailable_option_does_not_veto_good_direction_and_location():
    neutral = calculate_vision_method_snapshot(request(option_confirmation_context=option(state=VisionOptionConfirmation.NEUTRAL)))
    unavailable = calculate_vision_method_snapshot(request(option_confirmation_context=option(state=VisionOptionConfirmation.UNAVAILABLE)))

    assert neutral.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert neutral.quality == "medium"
    assert unavailable.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert unavailable.quality == "low"
    assert unavailable.entry_location_context.entry_location_state is VisionEntryLocationState.ACCEPTABLE


def test_poor_late_entry_location_preserves_direction_without_creating_fresh_entry():
    result = calculate_vision_method_snapshot(
        request(
            current_price=103.9,
            level_context=level(adr_used=88.0),
            option_confirmation_context=option(state=VisionOptionConfirmation.NEUTRAL),
        )
    )

    assert result.candidate_state is VisionCandidateState.PREPARE_LONG
    assert result.entry_location_context.entry_location_state is VisionEntryLocationState.WAIT_FOR_RETEST
    assert result.entry_location_context.move_maturity is VisionMoveMaturity.MATURE
    assert result.entry_location_context.chase_risk is VisionChaseRisk.HIGH
    assert "Entry location is not suitable for a fresh entry" in result.entry_location_context.location_blocking_reasons


def test_bearish_retest_with_neutral_options_can_be_short_eligible():
    result = calculate_vision_method_snapshot(
        request(
            current_price=99.0,
            level_context=level(cpr=VisionCPRRelation.BELOW_CPR, zone=VisionCamarillaZone.L3_L4, vwap=VisionVWAPRelation.BELOW_VWAP),
            opening_range_context=opening(state=VisionOpeningRangeState.RETEST, direction=VisionBreakDirection.DOWN, location=VisionRangeLocation.BELOW_RANGE),
            structure_context=structure(trend=VisionStructureTrend.BEARISH, pattern=VisionStructurePattern.LL),
            structure_event_context=event(bos=VisionBOS.BEARISH_BOS),
            setup_qualification_context=setup(supporting=("Below CPR", "Below L3", "Bearish BOS")),
            option_confirmation_context=option(state=VisionOptionConfirmation.NEUTRAL),
            price_action_trigger_context=trigger(
                direction=VisionTriggerDirection.BEARISH,
                trigger_type=VisionTriggerType.BEARISH_RETEST_HOLD,
                interaction=VisionTriggerInteractionState.HOLDING,
            ),
        )
    )

    assert result.candidate_state is VisionCandidateState.SHORT_ELIGIBLE
    assert result.entry_location_context.direction == "bearish"
    assert result.entry_location_context.entry_location_state is VisionEntryLocationState.FAVORABLE


def test_duplicate_reasons_are_suppressed_preserving_first_seen_order():
    result = calculate_vision_method_snapshot(
        request(
            setup_qualification_context=setup(supporting=("Above CPR", "Bullish BOS")),
            option_confirmation_context=option(supporting=("Bullish BOS", "Put writing supports setup")),
        )
    )

    lowered = [reason.casefold() for reason in result.supporting_reasons]
    assert lowered.count("above cpr") == 1
    assert lowered.count("bullish bos") == 1
    assert result.supporting_reasons.index("Above CPR") < result.supporting_reasons.index("Bullish BOS")


def test_price_action_trigger_is_required_for_final_eligibility():
    result = calculate_vision_method_snapshot(request(price_action_trigger_context=None))

    assert result.candidate_state is VisionCandidateState.PREPARE_LONG
    assert result.quality == "low"
    assert "Final trigger gate: valid 5-minute price-action trigger is unavailable" in result.supporting_reasons
    assert result.blocking_reasons == ()


def test_no_trigger_and_testing_states_remain_non_actionable():
    no_trigger = trigger(
        direction=VisionTriggerDirection.NONE,
        trigger_type=VisionTriggerType.NO_TRIGGER,
        quality=VisionTriggerQuality.INVALID,
        interaction=VisionTriggerInteractionState.NO_INTERACTION,
    )
    testing = trigger(
        trigger_type=VisionTriggerType.BULLISH_REJECTION,
        quality=VisionTriggerQuality.MEDIUM,
        interaction=VisionTriggerInteractionState.TESTING,
    )

    no_trigger_result = calculate_vision_method_snapshot(request(price_action_trigger_context=no_trigger))
    testing_result = calculate_vision_method_snapshot(request(price_action_trigger_context=testing))

    assert no_trigger_result.candidate_state is VisionCandidateState.PREPARE_LONG
    assert testing_result.candidate_state is VisionCandidateState.PREPARE_LONG
    assert "Final trigger gate: no_trigger cannot promote eligibility" in no_trigger_result.supporting_reasons
    assert "Final trigger gate: testing is observational only" in testing_result.supporting_reasons


def test_trigger_direction_must_match_final_direction():
    bearish_trigger = trigger(
        direction=VisionTriggerDirection.BEARISH,
        trigger_type=VisionTriggerType.BEARISH_INITIATIVE_BREAKOUT,
    )

    result = calculate_vision_method_snapshot(request(price_action_trigger_context=bearish_trigger))

    assert result.candidate_state is VisionCandidateState.PREPARE_LONG
    assert "Final trigger gate: price-action trigger direction does not align" in result.supporting_reasons


def test_stale_trigger_cannot_promote_eligibility():
    stale_timestamp = NOW - timedelta(minutes=5)
    stale_trigger = trigger(timestamp=stale_timestamp)

    result = calculate_vision_method_snapshot(request(price_action_trigger_context=stale_trigger))

    assert result.candidate_state is VisionCandidateState.PREPARE_LONG
    assert "Final trigger gate: price-action trigger is stale" in result.supporting_reasons


def test_option_neutral_and_unavailable_remain_modifiers_when_trigger_and_location_are_valid():
    neutral = calculate_vision_method_snapshot(request(option_confirmation_context=option(state=VisionOptionConfirmation.NEUTRAL)))
    unavailable = calculate_vision_method_snapshot(request(option_confirmation_context=option(state=VisionOptionConfirmation.UNAVAILABLE)))

    assert neutral.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert unavailable.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert "Option state is a quality modifier, not a hard veto" in neutral.supporting_reasons
    assert "Option state is a quality modifier, not a hard veto" in unavailable.supporting_reasons


def test_wait_for_retest_remains_first_class_non_actionable_state():
    result = calculate_vision_method_snapshot(
        request(
            current_price=103.9,
            level_context=level(adr_used=88.0),
            option_confirmation_context=option(state=VisionOptionConfirmation.CONFIRMS),
        )
    )

    assert result.candidate_state is VisionCandidateState.PREPARE_LONG
    assert result.entry_location_context.entry_location_state is VisionEntryLocationState.WAIT_FOR_RETEST
    assert "Final location gate: wait_for_retest" in result.supporting_reasons


def test_snapshot_is_immutable_and_validator_rejects_bad_inputs():
    result = calculate_vision_method_snapshot(request())

    with pytest.raises(FrozenInstanceError):
        result.candidate_state = VisionCandidateState.AVOID
    with pytest.raises(ValueError, match="instrument mismatch"):
        calculate_vision_method_snapshot(request(), instrument=RuntimeInstrument.BANKNIFTY)
    with pytest.raises(ValueError, match="timeframe mismatch"):
        calculate_vision_method_snapshot(request(), timeframe=TimeFrame.ONE_MINUTE)
    with pytest.raises(ValueError, match="timezone-aware"):
        request(timestamp=datetime(2026, 7, 29, 10, 30))
    with pytest.raises(ValueError, match="timestamp inconsistency"):
        calculate_vision_method_snapshot(request(option_confirmation_context=option(timestamp=NOW + timedelta(seconds=1))))


def test_vm09_boundary_creates_calculator_without_runtime_ai_strategy_dashboard_or_execution_code():
    package = Path("engines/vision_method")
    source = (package / "calculator.py").read_text(encoding="utf-8").lower()

    assert (package / "calculator.py").exists()
    assert not (package / "engine.py").exists()
    assert "strategydecision" not in source
    assert "aireasoning" not in source
    assert "riskmanagement" not in source
    assert "dashboard" not in source
    assert "paper" not in source
    assert "broker" not in source
    assert "eventbus" not in source
