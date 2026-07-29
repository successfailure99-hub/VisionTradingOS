from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from engines.vision_method import (
    VisionLevelQuality,
    VisionStructurePattern,
    VisionStructureRequest,
    VisionStructureTrend,
    VisionSwingPoint,
    VisionSwingType,
    assemble_vision_structure_context,
)


IST = timezone(timedelta(hours=5, minutes=30))
TODAY = date(2026, 7, 29)
START = datetime(2026, 7, 29, 9, 15, tzinfo=IST)


def candle(index: int, high: float, low: float, *, symbol="NIFTY", timeframe="5m", tz=IST) -> Candle:
    start = START.astimezone(tz) + timedelta(minutes=5 * index)
    end = start + timedelta(minutes=5)
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        start_time=start,
        end_time=end,
        open=(high + low) / 2,
        high=high,
        low=low,
        close=(high + low) / 2,
        volume=100,
    )


def candles_from(highs: tuple[float, ...], lows: tuple[float, ...], **overrides) -> tuple[Candle, ...]:
    return tuple(candle(index, high, lows[index], **overrides) for index, high in enumerate(highs))


def bullish_hh_candles() -> tuple[Candle, ...]:
    highs = (100, 102, 105, 103, 101, 106, 110, 107, 104, 110, 115, 112, 111)
    lows = (95, 97, 99, 98, 96, 101, 103, 102, 100, 106, 108, 107, 106)
    return candles_from(highs, lows)


def bullish_hl_candles() -> tuple[Candle, ...]:
    highs = (100, 102, 105, 103, 101, 106, 110, 107, 104, 108, 109)
    lows = (95, 97, 99, 98, 96, 101, 103, 102, 100, 105, 106)
    return candles_from(highs, lows)


def bearish_lh_candles() -> tuple[Candle, ...]:
    highs = (110, 112, 115, 113, 105, 108, 110, 107, 104)
    lows = (105, 107, 109, 106, 100, 104, 106, 101, 96)
    return candles_from(highs, lows)


def bearish_ll_candles() -> tuple[Candle, ...]:
    highs = (110, 112, 115, 113, 105, 108, 110, 107, 104, 106, 105, 103, 102)
    lows = (105, 107, 109, 106, 100, 104, 106, 101, 96, 99, 98, 95, 94)
    return candles_from(highs, lows)


def request(*candles: Candle, **overrides) -> VisionStructureRequest:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "trading_date": TODAY,
        "timestamp": datetime(2026, 7, 29, 10, 30, tzinfo=IST),
        "candles": candles or bullish_hh_candles(),
    }
    values.update(overrides)
    return VisionStructureRequest(**values)


def test_higher_high_and_bullish_trend_are_detected_from_confirmed_swings():
    result = assemble_vision_structure_context(request())

    assert result.structure_state is VisionStructurePattern.HH
    assert result.trend is VisionStructureTrend.BULLISH
    assert result.current_swing_high == VisionSwingPoint(115.0, START + timedelta(minutes=55), 10, 4, VisionSwingType.HIGH)
    assert result.previous_swing_high == VisionSwingPoint(110.0, START + timedelta(minutes=35), 6, 4, VisionSwingType.HIGH)
    assert result.current_swing_low == VisionSwingPoint(100.0, START + timedelta(minutes=45), 8, 4, VisionSwingType.LOW)
    assert result.previous_swing_low == VisionSwingPoint(96.0, START + timedelta(minutes=25), 4, 4, VisionSwingType.LOW)
    assert result.last_confirmed_swing is result.current_swing_high
    assert result.quality is VisionLevelQuality.FULL


def test_higher_low_is_classified_without_bos_or_choch():
    result = assemble_vision_structure_context(request(*bullish_hl_candles()))

    assert result.structure_state is VisionStructurePattern.HL
    assert result.trend is VisionStructureTrend.BULLISH
    assert result.last_confirmed_swing is result.current_swing_low
    assert result.current_swing_low.price == 100.0


def test_lower_high_and_lower_low_are_classified_for_bearish_structure():
    lower_high = assemble_vision_structure_context(request(*bearish_lh_candles()))
    lower_low = assemble_vision_structure_context(request(*bearish_ll_candles()))

    assert lower_high.structure_state is VisionStructurePattern.LH
    assert lower_high.trend is VisionStructureTrend.UNKNOWN
    assert lower_high.last_confirmed_swing is lower_high.current_swing_high
    assert lower_low.structure_state is VisionStructurePattern.LL
    assert lower_low.trend is VisionStructureTrend.BEARISH
    assert lower_low.last_confirmed_swing is lower_low.current_swing_low


def test_ranging_trend_when_highs_and_lows_disagree():
    highs = (100, 102, 105, 103, 101, 106, 110, 107, 104, 108, 109)
    lows = (95, 97, 99, 98, 96, 101, 103, 102, 94, 100, 101)

    result = assemble_vision_structure_context(request(*candles_from(highs, lows)))

    assert result.trend is VisionStructureTrend.RANGING
    assert result.structure_state is VisionStructurePattern.LL


def test_no_repaint_latest_candidate_waits_for_right_bars():
    incomplete = bullish_hh_candles()[:-2]
    complete = bullish_hh_candles()

    incomplete_result = assemble_vision_structure_context(request(*incomplete))
    complete_result = assemble_vision_structure_context(request(*complete))

    assert incomplete_result.current_swing_high.price == 110.0
    assert incomplete_result.structure_state is VisionStructurePattern.HL
    assert complete_result.current_swing_high.price == 115.0
    assert complete_result.structure_state is VisionStructurePattern.HH


def test_missing_candles_and_invalid_bar_configuration_are_rejected():
    with pytest.raises(ValueError, match="missing candles"):
        request(candles=())
    with pytest.raises(ValueError, match="insufficient candles"):
        assemble_vision_structure_context(request(*bullish_hh_candles()[:4]))
    with pytest.raises(ValueError, match="left_bars"):
        request(left_bars=0)
    with pytest.raises(TypeError, match="right_bars"):
        request(right_bars=True)


def test_validator_rejects_timezone_mismatch_wrong_context_and_invalid_sequence():
    with pytest.raises(ValueError, match="instrument mismatch"):
        assemble_vision_structure_context(request(), instrument=RuntimeInstrument.BANKNIFTY)
    with pytest.raises(ValueError, match="timeframe mismatch"):
        assemble_vision_structure_context(request(), timeframe=TimeFrame.ONE_MINUTE)
    with pytest.raises(ValueError, match="candle instrument mismatch"):
        assemble_vision_structure_context(request(*candles_from((1, 2, 5, 3, 1), (1, 1, 2, 1, 1), symbol="BANKNIFTY")))
    with pytest.raises(ValueError, match="timezone mismatch"):
        assemble_vision_structure_context(request(*candles_from((1, 2, 5, 3, 1), (1, 1, 2, 1, 1), tz=timezone.utc)))
    overlapping = (
        candle(0, 100, 95),
        Candle("NIFTY", "5m", START + timedelta(minutes=4), START + timedelta(minutes=10), 97, 101, 96, 98, 100),
        candle(2, 102, 98),
        candle(3, 101, 97),
        candle(4, 100, 96),
    )
    with pytest.raises(ValueError, match="invalid candle sequence"):
        assemble_vision_structure_context(request(*overlapping))


def test_duplicate_swing_model_and_context_are_immutable():
    swing = VisionSwingPoint(100.0, START, 0, 4, VisionSwingType.HIGH)
    result = assemble_vision_structure_context(request())

    with pytest.raises(FrozenInstanceError):
        swing.price = 101.0
    with pytest.raises(FrozenInstanceError):
        result.trend = VisionStructureTrend.RANGING


def test_structure_models_reject_duplicate_or_invalid_swing_identity():
    with pytest.raises(ValueError, match="index"):
        VisionSwingPoint(100.0, START, -1, 4, VisionSwingType.HIGH)
    with pytest.raises(ValueError, match="strength"):
        VisionSwingPoint(100.0, START, 0, 0, VisionSwingType.HIGH)
    with pytest.raises(TypeError, match="type"):
        VisionSwingPoint(100.0, START, 0, 4, "high")


def test_vm04_boundary_creates_no_bos_choch_liquidity_runtime_or_dashboard_code():
    package = Path("engines/vision_method")
    source = (package / "structure.py").read_text(encoding="utf-8").lower()

    assert (package / "structure.py").exists()
    assert not (package / "engine.py").exists()
    assert not (package / "bos.py").exists()
    assert not (package / "choch.py").exists()
    assert not (package / "liquidity.py").exists()
    assert "def assemble_vision_bos" not in source
    assert "def assemble_vision_choch" not in source
    assert "class visionbos" not in source
    assert "class visionliquidity" not in source
