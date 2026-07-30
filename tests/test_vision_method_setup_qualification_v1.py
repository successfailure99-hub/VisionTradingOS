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
    VisionLevelContext,
    VisionLevelQuality,
    VisionLiquidityContext,
    VisionLiquidityLevel,
    VisionLiquidityPool,
    VisionLiquiditySweep,
    VisionMSS,
    VisionMitigationState,
    VisionOpeningRangeContext,
    VisionOpeningRangeState,
    VisionPreviousDayContext,
    VisionPreviousDayRelation,
    VisionRangeLocation,
    VisionReversalState,
    VisionSetupQualificationContext,
    VisionSetupQualificationRequest,
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
    assemble_vision_setup_qualification_context,
)


IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 7, 29, 10, 30, tzinfo=IST)
OPEN_START = datetime(2026, 7, 29, 9, 15, tzinfo=IST)
OPEN_END = datetime(2026, 7, 29, 9, 30, tzinfo=IST)


def level(
    *,
    cpr: VisionCPRRelation = VisionCPRRelation.ABOVE_CPR,
    zone: VisionCamarillaZone = VisionCamarillaZone.H3_H4,
    vwap: VisionVWAPRelation | None = VisionVWAPRelation.ABOVE_VWAP,
    adr_pct: float | None = 32.0,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionLevelContext:
    return VisionLevelContext(
        cpr_context=VisionCPRContext(cpr, 99.0, 101.0, 100.0, 2.0, 2.0),
        camarilla_context=VisionCamarillaContext(zone, 103.0, 104.0, 105.0, 106.0, 97.0, 96.0, 95.0, 94.0),
        previous_day_context=VisionPreviousDayContext(
            previous_high=110.0,
            previous_low=90.0,
            previous_close=100.0,
            virgin_cpr=False,
            distance_previous_high=-5.0,
            distance_previous_low=15.0,
            previous_day_relation=VisionPreviousDayRelation.INSIDE_PREVIOUS_RANGE,
        ),
        adr_context=None
        if adr_pct is None
        else VisionADRContext(
            range_consumed_pct=adr_pct,
            range_remaining_pct=100.0 - adr_pct,
            near_adr_resistance=False,
            near_adr_support=False,
            expansion="normal",
            exhaustion="normal",
        ),
        vwap_context=None if vwap is None else VisionVWAPContext(vwap, 100.0, 1.0, 1.0),
        quality=quality,
        missing_evidence=() if quality is VisionLevelQuality.FULL else ("adr",),
    )


def opening(
    *,
    complete: bool = True,
    state: VisionOpeningRangeState = VisionOpeningRangeState.BREAK_ABOVE,
    direction: VisionBreakDirection = VisionBreakDirection.UP,
    location: VisionRangeLocation = VisionRangeLocation.ABOVE_RANGE,
    false_break: bool = False,
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
        false_break=false_break,
        elapsed_minutes=15 if complete else 10,
        quality=VisionLevelQuality.FULL if complete else VisionLevelQuality.PARTIAL,
    )


def swing(price: float, index: int, type_: VisionSwingType) -> VisionSwingPoint:
    return VisionSwingPoint(price, OPEN_START + timedelta(minutes=5 * index), index, 4, type_)


def structure(
    *,
    trend: VisionStructureTrend = VisionStructureTrend.BULLISH,
    state: VisionStructurePattern = VisionStructurePattern.HH,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionStructureContext:
    return VisionStructureContext(
        current_swing_high=swing(110.0, 5, VisionSwingType.HIGH),
        current_swing_low=swing(100.0, 6, VisionSwingType.LOW),
        previous_swing_high=swing(105.0, 1, VisionSwingType.HIGH),
        previous_swing_low=swing(95.0, 2, VisionSwingType.LOW),
        trend=trend,
        structure_state=state,
        last_confirmed_swing=swing(110.0, 5, VisionSwingType.HIGH),
        quality=quality,
    )


def liquidity(
    *,
    sweep: VisionLiquiditySweep = VisionLiquiditySweep.NONE,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionLiquidityContext:
    equal_highs = ()
    equal_lows = ()
    pool = VisionLiquidityPool.NONE
    direction = VisionSweepDirection.NONE
    if sweep is VisionLiquiditySweep.BUY_SIDE_SWEEP:
        equal_highs = (VisionLiquidityLevel(110.0, OPEN_START, OPEN_START + timedelta(minutes=5), (0, 1), VisionSwingType.HIGH, 0.0005),)
        pool = VisionLiquidityPool.BUY_SIDE
        direction = VisionSweepDirection.BUY_SIDE
    elif sweep is VisionLiquiditySweep.SELL_SIDE_SWEEP:
        equal_lows = (VisionLiquidityLevel(100.0, OPEN_START, OPEN_START + timedelta(minutes=5), (0, 1), VisionSwingType.LOW, 0.0005),)
        pool = VisionLiquidityPool.SELL_SIDE
        direction = VisionSweepDirection.SELL_SIDE
    return VisionLiquidityContext(
        equal_highs=equal_highs,
        equal_lows=equal_lows,
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
    strength: VisionBreakStrength = VisionBreakStrength.STRONG,
    quality: VisionLevelQuality = VisionLevelQuality.FULL,
) -> VisionStructureEventContext:
    if choch is VisionCHoCH.BULLISH_CHOCH:
        return VisionStructureEventContext(
            bos=VisionBOS.NONE,
            choch=choch,
            mss=VisionMSS.MARKET_STRUCTURE_SHIFT,
            continuation=VisionStructureEventPhase.REVERSAL,
            reversal=VisionReversalState.BULLISH_REVERSAL,
            break_strength=strength,
            quality=quality,
        )
    if choch is VisionCHoCH.BEARISH_CHOCH:
        return VisionStructureEventContext(
            bos=VisionBOS.NONE,
            choch=choch,
            mss=VisionMSS.MARKET_STRUCTURE_SHIFT,
            continuation=VisionStructureEventPhase.REVERSAL,
            reversal=VisionReversalState.BEARISH_REVERSAL,
            break_strength=strength,
            quality=quality,
        )
    return VisionStructureEventContext(
        bos=bos,
        choch=VisionCHoCH.NONE,
        mss=VisionMSS.NONE,
        continuation=VisionStructureEventPhase.CONTINUATION if bos is not VisionBOS.NONE else VisionStructureEventPhase.NONE,
        reversal=VisionReversalState.NONE,
        break_strength=strength if bos is not VisionBOS.NONE else VisionBreakStrength.NONE,
        quality=quality,
    )


def request(**overrides) -> VisionSetupQualificationRequest:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "timestamp": NOW,
        "level_context": level(),
        "opening_range_context": opening(),
        "structure_context": structure(),
        "liquidity_context": liquidity(),
        "structure_event_context": event(),
    }
    values.update(overrides)
    return VisionSetupQualificationRequest(**values)


def test_trend_continuation_qualifies_with_supporting_reasons():
    result = assemble_vision_setup_qualification_context(
        request(opening_range_context=opening(state=VisionOpeningRangeState.INSIDE_RANGE, direction=VisionBreakDirection.NONE, location=VisionRangeLocation.INSIDE_RANGE))
    )

    assert result.setup_type is VisionSetupType.TREND_CONTINUATION
    assert result.setup_quality is VisionSetupQuality.HIGH
    assert result.eligible_for_option_confirmation is True
    assert "Above CPR" in result.supporting_reasons
    assert "Above H3" in result.supporting_reasons
    assert "Bullish BOS" in result.supporting_reasons
    assert "ADR only 32% consumed" in result.supporting_reasons
    assert "VWAP supportive" in result.supporting_reasons


def test_pullback_continuation_qualifies_without_choch():
    result = assemble_vision_setup_qualification_context(
        request(
            opening_range_context=opening(state=VisionOpeningRangeState.RETEST, direction=VisionBreakDirection.UP, location=VisionRangeLocation.ABOVE_RANGE),
            level_context=level(vwap=VisionVWAPRelation.RETEST),
            structure_context=structure(trend=VisionStructureTrend.BULLISH, state=VisionStructurePattern.HL),
            structure_event_context=event(bos=VisionBOS.NONE),
        )
    )

    assert result.setup_type is VisionSetupType.PULLBACK_CONTINUATION
    assert result.setup_quality is VisionSetupQuality.MEDIUM
    assert result.eligible_for_option_confirmation is True


def test_breakout_qualifies_from_opening_range_break_bos_and_clean_structure():
    result = assemble_vision_setup_qualification_context(
        request(
            opening_range_context=opening(state=VisionOpeningRangeState.BREAK_BELOW, direction=VisionBreakDirection.DOWN, location=VisionRangeLocation.BELOW_RANGE),
            structure_context=structure(trend=VisionStructureTrend.BEARISH, state=VisionStructurePattern.LL),
            structure_event_context=event(bos=VisionBOS.BEARISH_BOS, strength=VisionBreakStrength.NORMAL),
        )
    )

    assert result.setup_type is VisionSetupType.BREAKOUT
    assert result.setup_quality is VisionSetupQuality.MEDIUM
    assert "Bearish BOS" in result.supporting_reasons


def test_failed_breakout_qualifies_as_descriptive_setup():
    result = assemble_vision_setup_qualification_context(
        request(
            opening_range_context=opening(
                state=VisionOpeningRangeState.FALSE_BREAK,
                direction=VisionBreakDirection.UP,
                location=VisionRangeLocation.INSIDE_RANGE,
                false_break=True,
            )
        )
    )

    assert result.setup_type is VisionSetupType.FAILED_BREAKOUT
    assert result.setup_quality is VisionSetupQuality.MEDIUM
    assert "Opening range false break" in result.supporting_reasons


def test_liquidity_reversal_requires_sweep_and_choch():
    result = assemble_vision_setup_qualification_context(
        request(
            opening_range_context=opening(state=VisionOpeningRangeState.INSIDE_RANGE, direction=VisionBreakDirection.NONE, location=VisionRangeLocation.INSIDE_RANGE),
            structure_context=structure(trend=VisionStructureTrend.BEARISH, state=VisionStructurePattern.LL),
            liquidity_context=liquidity(sweep=VisionLiquiditySweep.SELL_SIDE_SWEEP),
            structure_event_context=event(choch=VisionCHoCH.BULLISH_CHOCH, strength=VisionBreakStrength.STRONG),
        )
    )

    assert result.setup_type is VisionSetupType.LIQUIDITY_REVERSAL
    assert result.setup_quality is VisionSetupQuality.HIGH
    assert "Liquidity sweep completed" in result.supporting_reasons
    assert "Bullish CHoCH" in result.supporting_reasons


def test_range_fade_qualifies_inside_range_near_extreme_without_continuation():
    result = assemble_vision_setup_qualification_context(
        request(
            opening_range_context=opening(state=VisionOpeningRangeState.INSIDE_RANGE, direction=VisionBreakDirection.NONE, location=VisionRangeLocation.INSIDE_RANGE),
            level_context=level(cpr=VisionCPRRelation.INSIDE_CPR, zone=VisionCamarillaZone.L3_L4),
            structure_context=structure(trend=VisionStructureTrend.RANGING, state=VisionStructurePattern.UNKNOWN),
            structure_event_context=event(bos=VisionBOS.NONE),
        )
    )

    assert result.setup_type is VisionSetupType.RANGE_FADE
    assert result.setup_quality is VisionSetupQuality.MEDIUM
    assert "Inside CPR" in result.supporting_reasons
    assert "Below L3" in result.supporting_reasons


def test_no_quality_setup_generates_blocking_reasons_and_is_not_eligible():
    result = assemble_vision_setup_qualification_context(
        request(
            opening_range_context=opening(state=VisionOpeningRangeState.INSIDE_RANGE, direction=VisionBreakDirection.NONE, location=VisionRangeLocation.INSIDE_RANGE),
            level_context=level(quality=VisionLevelQuality.PARTIAL, adr_pct=None, vwap=None),
            structure_event_context=event(bos=VisionBOS.NONE),
        )
    )

    assert result.setup_type is VisionSetupType.NO_QUALITY_SETUP
    assert result.setup_quality is VisionSetupQuality.LOW
    assert result.eligible_for_option_confirmation is False
    assert "No BOS" in result.blocking_reasons
    assert "Insufficient evidence" in result.blocking_reasons


def test_opening_range_incomplete_blocks_before_setup_classification():
    result = assemble_vision_setup_qualification_context(
        request(
            opening_range_context=opening(
                complete=False,
                state=VisionOpeningRangeState.WAITING,
                direction=VisionBreakDirection.NONE,
                location=VisionRangeLocation.INSIDE_RANGE,
            )
        )
    )

    assert result.setup_type is VisionSetupType.NO_QUALITY_SETUP
    assert result.setup_quality is VisionSetupQuality.INVALID
    assert result.eligible_for_option_confirmation is False
    assert result.blocking_reasons == ("Opening range incomplete",)


def test_validator_failures_and_duplicate_reason_rejection():
    valid = request()
    with pytest.raises(ValueError, match="instrument mismatch"):
        assemble_vision_setup_qualification_context(valid, instrument=RuntimeInstrument.BANKNIFTY)
    with pytest.raises(ValueError, match="timeframe mismatch"):
        assemble_vision_setup_qualification_context(valid, timeframe=TimeFrame.ONE_MINUTE)
    with pytest.raises(ValueError, match="timezone-aware"):
        request(timestamp=datetime(2026, 7, 29, 10, 30))
    with pytest.raises(ValueError, match="insufficient structure context"):
        assemble_vision_setup_qualification_context(request(structure_context=structure(quality=VisionLevelQuality.INSUFFICIENT)))
    with pytest.raises(ValueError, match="duplicate reasons"):
        VisionSetupQualificationContext(
            setup_type=VisionSetupType.NO_QUALITY_SETUP,
            setup_quality=VisionSetupQuality.INVALID,
            blocking_reasons=("No BOS", "no bos"),
            supporting_reasons=(),
            eligible_for_option_confirmation=False,
        )


def test_setup_qualification_context_is_immutable():
    result = assemble_vision_setup_qualification_context(request())

    with pytest.raises(FrozenInstanceError):
        result.setup_type = VisionSetupType.NO_QUALITY_SETUP


def test_vm07_boundary_creates_no_runtime_strategy_ai_or_option_code():
    package = Path("engines/vision_method")
    source = (package / "setup_qualification.py").read_text(encoding="utf-8").lower()

    assert (package / "setup_qualification.py").exists()
    assert not (package / "engine.py").exists()
    assert "strategydecision" not in source
    assert "aireasoning" not in source
    assert "optionchain" not in source
    assert "eventbus" not in source
