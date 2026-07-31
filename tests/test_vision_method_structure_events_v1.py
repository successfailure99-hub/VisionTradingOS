from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from engines.vision_method import (
    VisionBOS,
    VisionBreakerBlock,
    VisionBreakerBlockState,
    VisionBreakStrength,
    VisionCHoCH,
    VisionLevelQuality,
    VisionLiquidityContext,
    VisionLiquidityLevel,
    VisionLiquidityPool,
    VisionLiquiditySweep,
    VisionMSS,
    VisionMitigationState,
    VisionReversalState,
    VisionStructureContext,
    VisionStructureEventContext,
    VisionStructureEventPhase,
    VisionStructureEventRequest,
    VisionStructurePattern,
    VisionStructureTrend,
    VisionSweepDirection,
    VisionSwingPoint,
    VisionSwingType,
    assemble_vision_structure_event_context,
)


IST = timezone(timedelta(hours=5, minutes=30))
TODAY = date(2026, 7, 29)
START = datetime(2026, 7, 29, 9, 15, tzinfo=IST)


def candle(index: int, open_: float, high: float, low: float, close: float, *, symbol="NIFTY", timeframe="5m", tz=IST) -> Candle:
    start = START.astimezone(tz) + timedelta(minutes=5 * index)
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        start_time=start,
        end_time=start + timedelta(minutes=5),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def swing(price: float, index: int, type_: VisionSwingType) -> VisionSwingPoint:
    return VisionSwingPoint(price, START + timedelta(minutes=5 * (index + 1)), index, 4, type_)


def structure(
    *,
    trend: VisionStructureTrend,
    state: VisionStructurePattern,
    high: float = 110.0,
    low: float = 100.0,
) -> VisionStructureContext:
    current_high = swing(high, 6, VisionSwingType.HIGH)
    current_low = swing(low, 8, VisionSwingType.LOW)
    return VisionStructureContext(
        current_swing_high=current_high,
        current_swing_low=current_low,
        previous_swing_high=swing(high - 5.0, 2, VisionSwingType.HIGH),
        previous_swing_low=swing(low - 5.0, 4, VisionSwingType.LOW),
        trend=trend,
        structure_state=state,
        last_confirmed_swing=current_high,
        quality=VisionLevelQuality.FULL,
    )


def liquidity(*, sweep: VisionLiquiditySweep = VisionLiquiditySweep.NONE) -> VisionLiquidityContext:
    equal_highs = ()
    equal_lows = ()
    pool = VisionLiquidityPool.NONE
    direction = VisionSweepDirection.NONE
    if sweep is VisionLiquiditySweep.BUY_SIDE_SWEEP:
        equal_highs = (VisionLiquidityLevel(110.0, START, START + timedelta(minutes=5), (0, 1), VisionSwingType.HIGH, 0.0005),)
        pool = VisionLiquidityPool.BUY_SIDE
        direction = VisionSweepDirection.BUY_SIDE
    elif sweep is VisionLiquiditySweep.SELL_SIDE_SWEEP:
        equal_lows = (VisionLiquidityLevel(100.0, START, START + timedelta(minutes=5), (0, 1), VisionSwingType.LOW, 0.0005),)
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
        quality=VisionLevelQuality.FULL,
    )


def request(*candles: Candle, structure_context=None, liquidity_context=None, **overrides) -> VisionStructureEventRequest:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "trading_date": TODAY,
        "timestamp": datetime(2026, 7, 29, 10, 30, tzinfo=IST),
        "candles": candles,
        "structure_context": structure_context or structure(
            trend=VisionStructureTrend.BULLISH,
            state=VisionStructurePattern.HH,
        ),
        "liquidity_context": liquidity_context or liquidity(),
    }
    values.update(overrides)
    return VisionStructureEventRequest(**values)


def base_candles(latest_close: float, latest_high: float | None = None, latest_low: float | None = None) -> tuple[Candle, ...]:
    latest_high = latest_high if latest_high is not None else max(latest_close, 110.0) + 1.0
    latest_low = latest_low if latest_low is not None else min(latest_close, 100.0) - 1.0
    return (
        candle(0, 104.0, 106.0, 103.0, 105.0),
        candle(1, 105.0, 107.0, 104.0, 106.0),
        candle(2, 106.0, latest_high, latest_low, latest_close),
    )


def test_bullish_bos_is_continuation_after_hh_hl_structure():
    result = assemble_vision_structure_event_context(
        request(*base_candles(111.0), structure_context=structure(trend=VisionStructureTrend.BULLISH, state=VisionStructurePattern.HH))
    )

    assert result.bos is VisionBOS.BULLISH_BOS
    assert result.choch is VisionCHoCH.NONE
    assert result.mss is VisionMSS.NONE
    assert result.continuation is VisionStructureEventPhase.CONTINUATION
    assert result.reversal is VisionReversalState.NONE
    assert result.break_strength is VisionBreakStrength.NORMAL
    assert result.quality is VisionLevelQuality.FULL


def test_bos_is_available_without_liquidity_context():
    result = assemble_vision_structure_event_context(
        request(
            *base_candles(111.0),
            structure_context=structure(trend=VisionStructureTrend.BULLISH, state=VisionStructurePattern.HH),
            liquidity_context=None,
        )
    )

    assert result.bos is VisionBOS.BULLISH_BOS
    assert result.choch is VisionCHoCH.NONE
    assert result.break_strength is VisionBreakStrength.NORMAL
    assert result.quality is VisionLevelQuality.FULL


def test_bearish_bos_is_continuation_after_lh_ll_structure():
    result = assemble_vision_structure_event_context(
        request(
            *base_candles(99.0),
            structure_context=structure(trend=VisionStructureTrend.BEARISH, state=VisionStructurePattern.LL),
        )
    )

    assert result.bos is VisionBOS.BEARISH_BOS
    assert result.choch is VisionCHoCH.NONE
    assert result.continuation is VisionStructureEventPhase.CONTINUATION


def test_bullish_choch_and_mss_are_first_break_against_bearish_structure():
    result = assemble_vision_structure_event_context(
        request(
            *base_candles(111.2),
            structure_context=structure(trend=VisionStructureTrend.BEARISH, state=VisionStructurePattern.LL),
            liquidity_context=liquidity(sweep=VisionLiquiditySweep.SELL_SIDE_SWEEP),
        )
    )

    assert result.bos is VisionBOS.NONE
    assert result.choch is VisionCHoCH.BULLISH_CHOCH
    assert result.mss is VisionMSS.MARKET_STRUCTURE_SHIFT
    assert result.continuation is VisionStructureEventPhase.REVERSAL
    assert result.reversal is VisionReversalState.BULLISH_REVERSAL
    assert result.break_strength is VisionBreakStrength.STRONG


def test_bearish_choch_and_mss_are_first_break_against_bullish_structure():
    result = assemble_vision_structure_event_context(
        request(
            *base_candles(98.8),
            structure_context=structure(trend=VisionStructureTrend.BULLISH, state=VisionStructurePattern.HH),
            liquidity_context=liquidity(sweep=VisionLiquiditySweep.BUY_SIDE_SWEEP),
        )
    )

    assert result.bos is VisionBOS.NONE
    assert result.choch is VisionCHoCH.BEARISH_CHOCH
    assert result.mss is VisionMSS.MARKET_STRUCTURE_SHIFT
    assert result.reversal is VisionReversalState.BEARISH_REVERSAL
    assert result.break_strength is VisionBreakStrength.STRONG


def test_no_event_when_price_does_not_break_confirmed_structure():
    result = assemble_vision_structure_event_context(
        request(*base_candles(105.0), structure_context=structure(trend=VisionStructureTrend.BULLISH, state=VisionStructurePattern.HL))
    )

    assert result.bos is VisionBOS.NONE
    assert result.choch is VisionCHoCH.NONE
    assert result.mss is VisionMSS.NONE
    assert result.continuation is VisionStructureEventPhase.NONE
    assert result.reversal is VisionReversalState.NONE
    assert result.break_strength is VisionBreakStrength.NONE
    assert result.quality is VisionLevelQuality.PARTIAL


def test_validator_rejects_invalid_sequence_context_mismatch_and_duplicate_events():
    valid = base_candles(105.0)
    with pytest.raises(ValueError, match="instrument mismatch"):
        assemble_vision_structure_event_context(request(*valid), instrument=RuntimeInstrument.BANKNIFTY)
    with pytest.raises(ValueError, match="timeframe mismatch"):
        assemble_vision_structure_event_context(request(*valid), timeframe=TimeFrame.ONE_MINUTE)
    with pytest.raises(ValueError, match="candle timezone mismatch"):
        assemble_vision_structure_event_context(request(*tuple(candle(i, 100, 101, 99, 100, tz=timezone.utc) for i in range(3))))
    overlapping = (
        candle(0, 100.0, 101.0, 99.0, 100.0),
        Candle("NIFTY", "5m", START + timedelta(minutes=4), START + timedelta(minutes=10), 100.0, 101.0, 99.0, 100.0, 100),
    )
    with pytest.raises(ValueError, match="invalid candle sequence"):
        assemble_vision_structure_event_context(request(*overlapping))
    impossible = structure(trend=VisionStructureTrend.BULLISH, state=VisionStructurePattern.HH, high=100.0, low=110.0)
    with pytest.raises(ValueError, match="duplicate events"):
        assemble_vision_structure_event_context(request(*base_candles(105.0, latest_high=112.0, latest_low=98.0), structure_context=impossible))


def test_structure_event_model_rejects_impossible_bos_choch_and_is_immutable():
    result = assemble_vision_structure_event_context(request(*base_candles(111.0)))

    with pytest.raises(ValueError, match="BOS and CHoCH"):
        VisionStructureEventContext(
            bos=VisionBOS.BULLISH_BOS,
            choch=VisionCHoCH.BEARISH_CHOCH,
            mss=VisionMSS.NONE,
            continuation=VisionStructureEventPhase.CONTINUATION,
            reversal=VisionReversalState.NONE,
            break_strength=VisionBreakStrength.NORMAL,
            quality=VisionLevelQuality.FULL,
        )
    with pytest.raises(FrozenInstanceError):
        result.bos = VisionBOS.NONE


def test_vm06_boundary_creates_no_runtime_strategy_ai_or_option_code():
    package = Path("engines/vision_method")
    source = (package / "structure_events.py").read_text(encoding="utf-8").lower()

    assert (package / "structure_events.py").exists()
    assert not (package / "engine.py").exists()
    assert "strategydecision" not in source
    assert "aireasoning" not in source
    assert "optionchain" not in source
    assert "eventbus" not in source
