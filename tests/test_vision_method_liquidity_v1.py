from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from engines.vision_method import (
    VisionBreakerBlockState,
    VisionFairValueGapDirection,
    VisionLevelQuality,
    VisionLiquidityContext,
    VisionLiquidityPool,
    VisionLiquidityRequest,
    VisionLiquiditySweep,
    VisionMitigationState,
    VisionOrderBlockDirection,
    VisionSweepDirection,
    VisionSwingType,
    assemble_vision_liquidity_context,
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


def request(*candles: Candle, **overrides) -> VisionLiquidityRequest:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "trading_date": TODAY,
        "timestamp": datetime(2026, 7, 29, 10, 30, tzinfo=IST),
        "candles": candles,
    }
    values.update(overrides)
    return VisionLiquidityRequest(**values)


def test_equal_high_detects_buy_side_liquidity_pool():
    candles = (
        candle(0, 99.0, 100.0, 98.0, 99.5),
        candle(1, 99.4, 100.04, 98.2, 99.2),
        candle(2, 99.2, 99.8, 98.4, 99.0),
    )

    result = assemble_vision_liquidity_context(request(*candles))

    assert len(result.equal_highs) == 1
    assert result.equal_highs[0].type is VisionSwingType.HIGH
    assert result.equal_highs[0].indexes == (0, 1)
    assert result.liquidity_pool is VisionLiquidityPool.BUY_SIDE
    assert result.liquidity_sweep is VisionLiquiditySweep.NONE
    assert result.quality is VisionLevelQuality.FULL


def test_equal_low_detects_sell_side_liquidity_pool():
    candles = (
        candle(0, 99.0, 100.0, 98.0, 99.5),
        candle(1, 99.4, 100.2, 98.03, 99.2),
        candle(2, 99.2, 99.8, 98.4, 99.0),
    )

    result = assemble_vision_liquidity_context(request(*candles))

    assert len(result.equal_lows) == 1
    assert result.equal_lows[0].type is VisionSwingType.LOW
    assert result.equal_lows[0].indexes == (0, 1)
    assert result.liquidity_pool is VisionLiquidityPool.SELL_SIDE


def test_buy_side_and_sell_side_liquidity_sweeps_close_back_inside():
    buy_side = (
        candle(0, 99.0, 100.0, 98.0, 99.5),
        candle(1, 99.4, 100.04, 98.2, 99.2),
        candle(2, 99.2, 101.0, 98.4, 99.8),
    )
    sell_side = (
        candle(0, 99.0, 100.0, 98.0, 99.5),
        candle(1, 99.4, 100.2, 98.03, 99.2),
        candle(2, 99.2, 99.8, 97.0, 98.4),
    )

    buy_result = assemble_vision_liquidity_context(request(*buy_side))
    sell_result = assemble_vision_liquidity_context(request(*sell_side))

    assert buy_result.liquidity_sweep is VisionLiquiditySweep.BUY_SIDE_SWEEP
    assert buy_result.sweep_direction is VisionSweepDirection.BUY_SIDE
    assert sell_result.liquidity_sweep is VisionLiquiditySweep.SELL_SIDE_SWEEP
    assert sell_result.sweep_direction is VisionSweepDirection.SELL_SIDE


def test_no_sweep_when_price_does_not_close_back_inside():
    candles = (
        candle(0, 99.0, 100.0, 98.0, 99.5),
        candle(1, 99.4, 100.04, 98.2, 99.2),
        candle(2, 99.2, 101.0, 98.4, 100.5),
    )

    result = assemble_vision_liquidity_context(request(*candles))

    assert result.liquidity_sweep is VisionLiquiditySweep.NONE
    assert result.sweep_direction is VisionSweepDirection.NONE


def test_fair_value_gap_detects_three_candle_imbalance_without_mitigation_logic():
    candles = (
        candle(0, 99.0, 100.0, 99.0, 99.5),
        candle(1, 100.0, 100.6, 99.8, 100.4),
        candle(2, 101.2, 102.0, 101.0, 101.8),
    )

    result = assemble_vision_liquidity_context(request(*candles))

    assert result.fair_value_gap is not None
    assert result.fair_value_gap.direction is VisionFairValueGapDirection.BULLISH
    assert result.fair_value_gap.lower_bound == 100.0
    assert result.fair_value_gap.upper_bound == 101.0
    assert result.mitigation is VisionMitigationState.NOT_EVALUATED


def test_no_fair_value_gap_when_three_candle_ranges_overlap():
    candles = (
        candle(0, 99.0, 100.0, 98.5, 99.5),
        candle(1, 99.5, 100.5, 99.0, 100.0),
        candle(2, 99.8, 100.8, 99.5, 100.2),
    )

    result = assemble_vision_liquidity_context(request(*candles))

    assert result.fair_value_gap is None


def test_order_block_marks_last_opposite_candle_before_impulsive_move():
    candles = (
        candle(0, 100.0, 101.0, 98.0, 99.0),
        candle(1, 99.0, 103.0, 99.0, 102.0),
        candle(2, 102.0, 102.5, 100.0, 101.0),
    )

    result = assemble_vision_liquidity_context(request(*candles))

    assert result.order_block is not None
    assert result.order_block.direction is VisionOrderBlockDirection.BULLISH
    assert result.order_block.candle_index == 0
    assert result.breaker_block.state is VisionBreakerBlockState.NOT_EVALUATED


def test_overlapping_bullish_fvgs_are_normalized_without_crashing():
    candles = (
        candle(0, 99.0, 100.0, 99.0, 99.5),
        candle(1, 100.0, 100.5, 99.5, 100.2),
        candle(2, 101.0, 102.0, 101.0, 101.5),
        candle(3, 101.1, 102.2, 100.8, 101.7),
    )

    result = assemble_vision_liquidity_context(request(*candles))

    assert result.fair_value_gap is not None
    assert result.fair_value_gap.direction is VisionFairValueGapDirection.BULLISH
    assert result.fair_value_gap.lower_bound == 100.0
    assert result.fair_value_gap.upper_bound == 101.0


def test_overlapping_bearish_fvgs_are_normalized_without_crashing():
    candles = (
        candle(0, 101.0, 102.0, 100.0, 100.5),
        candle(1, 100.2, 100.8, 99.7, 100.0),
        candle(2, 99.0, 99.0, 98.0, 98.5),
        candle(3, 98.8, 99.5, 98.0, 98.2),
    )

    result = assemble_vision_liquidity_context(request(*candles))

    assert result.fair_value_gap is not None
    assert result.fair_value_gap.direction is VisionFairValueGapDirection.BEARISH
    assert result.fair_value_gap.lower_bound == 99.0
    assert result.fair_value_gap.upper_bound == 100.0


def test_opposite_direction_overlapping_fvgs_coexist_without_crashing():
    candles = (
        candle(0, 99.0, 100.0, 99.0, 99.5),
        candle(1, 100.0, 100.5, 99.5, 100.2),
        candle(2, 101.0, 102.0, 101.0, 101.5),
        candle(3, 101.2, 101.8, 100.8, 101.0),
        candle(4, 100.0, 100.5, 99.0, 99.5),
    )

    result = assemble_vision_liquidity_context(request(*candles))

    assert result.fair_value_gap is not None
    assert result.fair_value_gap.direction is VisionFairValueGapDirection.BEARISH
    assert result.fair_value_gap.lower_bound == 100.5
    assert result.fair_value_gap.upper_bound == 101.0


def test_validator_rejects_context_mismatch_invalid_sequence_and_bad_sweep_model():
    valid = (
        candle(0, 99.0, 100.0, 98.0, 99.5),
        candle(1, 99.4, 100.04, 98.2, 99.2),
        candle(2, 99.2, 99.8, 98.4, 99.0),
    )
    with pytest.raises(ValueError, match="instrument mismatch"):
        assemble_vision_liquidity_context(request(*valid), instrument=RuntimeInstrument.BANKNIFTY)
    with pytest.raises(ValueError, match="timeframe mismatch"):
        assemble_vision_liquidity_context(request(*valid), timeframe=TimeFrame.ONE_MINUTE)
    with pytest.raises(ValueError, match="candle timezone mismatch"):
        assemble_vision_liquidity_context(request(*tuple(candle(i, 99.0, 100.0, 98.0, 99.0, tz=timezone.utc) for i in range(3))))
    overlapping = (
        candle(0, 99.0, 100.0, 98.0, 99.5),
        Candle("NIFTY", "5m", START + timedelta(minutes=4), START + timedelta(minutes=10), 99.0, 100.0, 98.0, 99.0, 100),
        candle(2, 99.0, 100.0, 98.0, 99.0),
    )
    with pytest.raises(ValueError, match="invalid candle sequence"):
        assemble_vision_liquidity_context(request(*overlapping))
    with pytest.raises(ValueError, match="sweeps require"):
        VisionLiquidityContext(
            equal_highs=(),
            equal_lows=(),
            liquidity_pool=VisionLiquidityPool.NONE,
            liquidity_sweep=VisionLiquiditySweep.BUY_SIDE_SWEEP,
            sweep_direction=VisionSweepDirection.BUY_SIDE,
            fair_value_gap=None,
            order_block=None,
            breaker_block=assemble_vision_liquidity_context(request(*valid)).breaker_block,
            mitigation=VisionMitigationState.NOT_EVALUATED,
            quality=VisionLevelQuality.PARTIAL,
        )


def test_liquidity_models_are_immutable():
    result = assemble_vision_liquidity_context(
        request(
            candle(0, 99.0, 100.0, 98.0, 99.5),
            candle(1, 99.4, 100.04, 98.2, 99.2),
            candle(2, 99.2, 101.0, 98.4, 99.8),
        )
    )

    with pytest.raises(FrozenInstanceError):
        result.liquidity_pool = VisionLiquidityPool.NONE
    with pytest.raises(FrozenInstanceError):
        result.equal_highs[0].price = 1.0


def test_vm05_boundary_creates_no_runtime_strategy_ai_or_option_code():
    package = Path("engines/vision_method")
    source = (package / "liquidity.py").read_text(encoding="utf-8").lower()

    assert (package / "liquidity.py").exists()
    assert not (package / "engine.py").exists()
    assert "strategydecision" not in source
    assert "aireasoning" not in source
    assert "optionchain" not in source
    assert "eventbus" not in source
