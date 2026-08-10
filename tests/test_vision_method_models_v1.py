from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.events import (
    VISION_METHOD_FAILED,
    VISION_METHOD_INVALID,
    VISION_METHOD_PARTIAL,
    VISION_METHOD_READY,
    VISION_METHOD_UPDATED,
)
from engines.vision_method import (
    VisionBOS,
    VisionBreakerBlock,
    VisionBreakerBlockState,
    VisionBreakStrength,
    VisionBreakDirection,
    VisionCHoCH,
    VisionADRContext,
    VisionCPRContext,
    VisionCPRRelation,
    VisionCamarillaContext,
    VisionCamarillaZone,
    VisionCandidateState,
    VisionChaseRisk,
    VisionDirectionQuality,
    VisionEntryLocationContext,
    VisionEntryLocationState,
    VisionFairValueGapDirection,
    VisionLevelContext,
    VisionLevelQuality,
    VisionLiquidityContext,
    VisionLiquidityLevel,
    VisionLiquidityPool,
    VisionLiquiditySweep,
    VisionMarketRegime,
    VisionMitigationState,
    VisionMSS,
    VisionMethodSnapshot,
    VisionMoveMaturity,
    VisionOpeningContext,
    VisionOpeningLocation,
    VisionOpeningRangeContext,
    VisionOpeningRangeState,
    VisionOptionConfirmationContext,
    VisionOrderBlockDirection,
    VisionRangeLocation,
    VisionReversalState,
    VisionSetupQuality,
    VisionSetupQualificationContext,
    VisionSetupType,
    VisionStructureContext,
    VisionStructureEventContext,
    VisionStructureEventPhase,
    VisionStructurePattern,
    VisionVWAPContext,
    VisionVWAPRelation,
    VisionOptionConfirmation,
    VisionPreviousDayContext,
    VisionStructureState,
    VisionStructureTrend,
    VisionSweepDirection,
    VisionSwingPoint,
    VisionSwingType,
    validate_vision_method_snapshot,
)


NOW = datetime(2026, 7, 29, 9, 30, tzinfo=timezone.utc)
OPEN_START = datetime(2026, 7, 29, 9, 15, tzinfo=timezone.utc)
OPEN_END = datetime(2026, 7, 29, 9, 30, tzinfo=timezone.utc)


def opening_context() -> VisionOpeningContext:
    return VisionOpeningContext(
        opening_location=VisionOpeningLocation.ABOVE_CPR,
        opening_price=24168.5,
        cpr_relation="above",
        camarilla_relation="near_h3",
        gap_type="gap_up",
    )


def previous_day_context() -> VisionPreviousDayContext:
    return VisionPreviousDayContext(
        previous_high=24310.0,
        previous_low=24107.7,
        previous_close=24168.5,
        virgin_cpr=False,
        distance_previous_high=141.5,
        distance_previous_low=60.8,
    )


def level_context() -> VisionLevelContext:
    return VisionLevelContext(
        cpr_context=VisionCPRContext(VisionCPRRelation.ABOVE_CPR, 100.0, 101.0, 100.5, 1.0, 0.5),
        camarilla_context=VisionCamarillaContext(
            VisionCamarillaZone.H3_H4,
            h3=103.0,
            h4=104.0,
            h5=105.0,
            h6=106.0,
            l3=97.0,
            l4=96.0,
            l5=95.0,
            l6=94.0,
        ),
        previous_day_context=previous_day_context(),
        adr_context=VisionADRContext(50.0, 50.0, False, False, "normal", "not_exhausted"),
        vwap_context=VisionVWAPContext(VisionVWAPRelation.ABOVE_VWAP, 100.0, 1.0, 1.0),
        quality=VisionLevelQuality.FULL,
    )


def opening_range_context() -> VisionOpeningRangeContext:
    return VisionOpeningRangeContext(
        opening_start_time=OPEN_START,
        opening_end_time=OPEN_END,
        opening_high=102.0,
        opening_low=99.0,
        opening_width=3.0,
        range_complete=True,
        current_location=VisionRangeLocation.ABOVE_RANGE,
        break_direction=VisionBreakDirection.UP,
        retest_state=VisionOpeningRangeState.BREAK_ABOVE,
        false_break=False,
        elapsed_minutes=15,
        quality=VisionLevelQuality.FULL,
    )


def swing(price: float, index: int, type_: VisionSwingType) -> VisionSwingPoint:
    return VisionSwingPoint(price, OPEN_START + timedelta(minutes=5 * index), index, 4, type_)


def structure_context() -> VisionStructureContext:
    return VisionStructureContext(
        current_swing_high=swing(110.0, 5, VisionSwingType.HIGH),
        current_swing_low=swing(100.0, 6, VisionSwingType.LOW),
        previous_swing_high=swing(105.0, 1, VisionSwingType.HIGH),
        previous_swing_low=swing(95.0, 2, VisionSwingType.LOW),
        trend=VisionStructureTrend.BULLISH,
        structure_state=VisionStructurePattern.HH,
        last_confirmed_swing=swing(110.0, 5, VisionSwingType.HIGH),
        quality=VisionLevelQuality.FULL,
    )


def liquidity_context() -> VisionLiquidityContext:
    level = VisionLiquidityLevel(110.0, OPEN_START, OPEN_START + timedelta(minutes=5), (0, 1), VisionSwingType.HIGH, 0.0005)
    return VisionLiquidityContext(
        equal_highs=(level,),
        equal_lows=(),
        liquidity_pool=VisionLiquidityPool.BUY_SIDE,
        liquidity_sweep=VisionLiquiditySweep.BUY_SIDE_SWEEP,
        sweep_direction=VisionSweepDirection.BUY_SIDE,
        fair_value_gap=None,
        order_block=None,
        breaker_block=VisionBreakerBlock(VisionBreakerBlockState.NOT_EVALUATED),
        mitigation=VisionMitigationState.NOT_EVALUATED,
        quality=VisionLevelQuality.FULL,
    )


def structure_event_context() -> VisionStructureEventContext:
    return VisionStructureEventContext(
        bos=VisionBOS.BULLISH_BOS,
        choch=VisionCHoCH.NONE,
        mss=VisionMSS.NONE,
        continuation=VisionStructureEventPhase.CONTINUATION,
        reversal=VisionReversalState.NONE,
        break_strength=VisionBreakStrength.STRONG,
        quality=VisionLevelQuality.FULL,
    )


def setup_qualification_context() -> VisionSetupQualificationContext:
    return VisionSetupQualificationContext(
        setup_type=VisionSetupType.TREND_CONTINUATION,
        setup_quality=VisionSetupQuality.HIGH,
        blocking_reasons=(),
        supporting_reasons=("Above CPR", "Bullish BOS"),
        eligible_for_option_confirmation=True,
    )


def option_confirmation_context() -> VisionOptionConfirmationContext:
    return VisionOptionConfirmationContext(
        confirmation_state=VisionOptionConfirmation.CONFIRMS,
        supporting_factors=("Put writing supports setup",),
        contradicting_factors=(),
        neutral_factors=(),
        quality=VisionLevelQuality.FULL,
        timestamp=NOW,
    )


def snapshot(**overrides) -> VisionMethodSnapshot:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "timestamp": NOW,
        "opening_context": opening_context(),
        "previous_day_context": previous_day_context(),
        "level_context": level_context(),
        "opening_range_context": opening_range_context(),
        "structure_context": structure_context(),
        "liquidity_context": liquidity_context(),
        "structure_event_context": structure_event_context(),
        "setup_qualification_context": setup_qualification_context(),
        "option_confirmation_context": option_confirmation_context(),
        "market_regime": VisionMarketRegime.TREND_DAY,
        "candidate_state": VisionCandidateState.OBSERVE,
        "blocking_reasons": ("wait_for_opening_range",),
        "supporting_reasons": ("opened_above_cpr",),
        "quality": "medium",
    }
    values.update(overrides)
    return VisionMethodSnapshot(**values)


def test_enum_contracts_and_serialization_are_deterministic():
    assert VisionOpeningLocation.ABOVE_CPR.value == "above_cpr"
    assert VisionOpeningLocation.INSIDE_CPR.value == "inside_cpr"
    assert VisionOpeningLocation.BELOW_CPR.value == "below_cpr"
    assert VisionMarketRegime.UNKNOWN.value == "unknown"
    assert VisionStructureState.BULLISH.value == "bullish"
    assert VisionOptionConfirmation.CONTRADICTS.value == "contradicts"
    assert VisionCandidateState.PREPARE_LONG.value == "prepare_long"
    assert VisionCandidateState.INSUFFICIENT_DATA.value == "insufficient_data"
    assert VisionEntryLocationState.ACCEPTABLE.value == "acceptable"
    assert VisionMoveMaturity.MATURE.value == "mature"
    assert VisionChaseRisk.HIGH.value == "high"
    assert VisionOpeningRangeState.WAITING.value == "waiting"
    assert VisionOpeningRangeState.FALSE_BREAK.value == "false_break"
    assert VisionBreakDirection.UP.value == "up"
    assert VisionRangeLocation.INSIDE_RANGE.value == "inside_range"
    assert VisionSwingType.HIGH.value == "high"
    assert VisionStructureTrend.BEARISH.value == "bearish"


def test_entry_location_context_is_immutable_and_validated():
    context = VisionEntryLocationContext(
        direction="Bullish",
        direction_quality=VisionDirectionQuality.HIGH,
        entry_location_state=VisionEntryLocationState.ACCEPTABLE,
        entry_location_quality=VisionLevelQuality.FULL,
        remaining_room=2.5,
        nearest_target_or_destination="H4",
        nearest_invalidation="Below Swing Low",
        move_maturity=VisionMoveMaturity.DEVELOPING,
        retest_state="break_above",
        chase_risk=VisionChaseRisk.LOW,
        location_supporting_reasons=("Direction confirmed",),
        location_warning_reasons=(),
        location_blocking_reasons=(),
    )

    assert context.direction == "bullish"
    assert context.remaining_room == 2.5
    with pytest.raises(FrozenInstanceError):
        context.direction = "bearish"
    with pytest.raises(ValueError, match="direction"):
        VisionEntryLocationContext(
            direction="sideways",
            direction_quality=VisionDirectionQuality.HIGH,
            entry_location_state=VisionEntryLocationState.ACCEPTABLE,
            entry_location_quality=VisionLevelQuality.FULL,
            remaining_room=1.0,
            nearest_target_or_destination="H4",
            nearest_invalidation="Below Swing Low",
            move_maturity=VisionMoveMaturity.EARLY,
            retest_state="break_above",
            chase_risk=VisionChaseRisk.LOW,
            location_supporting_reasons=(),
            location_warning_reasons=(),
            location_blocking_reasons=(),
        )
    assert VisionStructurePattern.HH.value == "hh"
    assert VisionStructurePattern.UNKNOWN.value == "unknown"
    assert VisionLiquidityPool.BUY_SIDE.value == "buy_side"
    assert VisionLiquiditySweep.SELL_SIDE_SWEEP.value == "sell_side_sweep"
    assert VisionSweepDirection.NONE.value == "none"
    assert VisionFairValueGapDirection.BULLISH.value == "bullish"
    assert VisionOrderBlockDirection.BEARISH.value == "bearish"
    assert VisionBreakerBlockState.NOT_EVALUATED.value == "not_evaluated"
    assert VisionMitigationState.NOT_EVALUATED.value == "not_evaluated"
    assert VisionBOS.BULLISH_BOS.value == "bullish_bos"
    assert VisionCHoCH.BEARISH_CHOCH.value == "bearish_choch"
    assert VisionMSS.MARKET_STRUCTURE_SHIFT.value == "market_structure_shift"
    assert VisionStructureEventPhase.CONTINUATION.value == "continuation"
    assert VisionReversalState.BULLISH_REVERSAL.value == "bullish_reversal"
    assert VisionBreakStrength.STRONG.value == "strong"
    assert VisionSetupType.TREND_CONTINUATION.value == "trend_continuation"
    assert VisionSetupType.LIQUIDITY_REVERSAL.value == "liquidity_reversal"
    assert VisionSetupQuality.HIGH.value == "high"
    assert VisionSetupQuality.INVALID.value == "invalid"


def test_vision_method_snapshot_construction_equality_and_validation():
    first = snapshot()
    second = snapshot()

    assert first == second
    assert first.instrument is RuntimeInstrument.NIFTY
    assert first.timeframe is TimeFrame.FIVE_MINUTES
    assert validate_vision_method_snapshot(
        first,
        instrument=RuntimeInstrument.NIFTY,
        timeframe=TimeFrame.FIVE_MINUTES,
    ) is first


def test_models_are_immutable():
    result = snapshot()

    with pytest.raises(FrozenInstanceError):
        result.quality = "high"
    with pytest.raises(FrozenInstanceError):
        result.opening_context.opening_price = 1.0


def test_timezone_aware_timestamp_is_required():
    with pytest.raises(ValueError, match="timezone-aware"):
        snapshot(timestamp=datetime(2026, 7, 29, 9, 30))


def test_missing_mandatory_context_is_rejected():
    with pytest.raises(TypeError, match="opening_context"):
        snapshot(opening_context=None)
    with pytest.raises(TypeError, match="previous_day_context"):
        snapshot(previous_day_context=None)
    with pytest.raises(TypeError, match="level_context"):
        snapshot(level_context=None)
    with pytest.raises(TypeError, match="adr_context"):
        VisionLevelContext(
            cpr_context=level_context().cpr_context,
            camarilla_context=level_context().camarilla_context,
            previous_day_context=level_context().previous_day_context,
            adr_context=("adr",),
            vwap_context=level_context().vwap_context,
            quality=VisionLevelQuality.FULL,
        )


def test_invalid_instrument_and_timeframe_are_rejected():
    with pytest.raises(TypeError, match="instrument"):
        snapshot(instrument="NIFTY")
    with pytest.raises(TypeError, match="timeframe"):
        snapshot(timeframe="5m")
    with pytest.raises(ValueError, match="instrument mismatch"):
        validate_vision_method_snapshot(snapshot(), instrument=RuntimeInstrument.BANKNIFTY)
    with pytest.raises(ValueError, match="timeframe mismatch"):
        validate_vision_method_snapshot(snapshot(), timeframe=TimeFrame.ONE_MINUTE)


def test_previous_day_contract_rejects_invalid_ranges():
    with pytest.raises(ValueError, match="previous_high"):
        VisionPreviousDayContext(
            previous_high=100.0,
            previous_low=110.0,
            previous_close=105.0,
            virgin_cpr=False,
            distance_previous_high=1.0,
            distance_previous_low=1.0,
        )
    with pytest.raises(ValueError, match="previous_close"):
        VisionPreviousDayContext(
            previous_high=110.0,
            previous_low=100.0,
            previous_close=120.0,
            virgin_cpr=False,
            distance_previous_high=1.0,
            distance_previous_low=1.0,
        )


def test_reason_fields_are_immutable_tuples_and_normalized():
    result = snapshot(blocking_reasons=("  wait  ",), supporting_reasons=(" opened above cpr ",))

    assert result.blocking_reasons == ("wait",)
    assert result.supporting_reasons == ("opened above cpr",)
    with pytest.raises(TypeError, match="blocking_reasons"):
        snapshot(blocking_reasons=["wait"])


def test_vision_method_events_are_declared_without_runtime_publishing():
    assert VISION_METHOD_UPDATED == "vision_method_updated"
    assert VISION_METHOD_PARTIAL == "vision_method_partial"
    assert VISION_METHOD_INVALID == "vision_method_invalid"
    assert VISION_METHOD_FAILED == "vision_method_failed"
    assert VISION_METHOD_READY == "vision_method_ready"
