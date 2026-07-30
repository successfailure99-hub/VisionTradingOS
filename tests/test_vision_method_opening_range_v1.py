from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from engines.vision_method import (
    VisionBreakDirection,
    VisionLevelQuality,
    VisionOpeningRangeRequest,
    VisionOpeningRangeState,
    VisionRangeLocation,
    assemble_vision_opening_range_context,
)


IST = timezone(timedelta(hours=5, minutes=30))
TODAY = date(2026, 7, 29)
SESSION = datetime(2026, 7, 29, 9, 15, tzinfo=IST)


def candle(
    start_minute: int,
    end_minute: int,
    *,
    high: float,
    low: float,
    close: float,
    open_price: float | None = None,
    symbol: str = "NIFTY",
    timeframe: str = "5m",
    tz=IST,
) -> Candle:
    start = datetime(2026, 7, 29, 9, start_minute, tzinfo=tz)
    end = datetime(2026, 7, 29, 9, end_minute, tzinfo=tz)
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        start_time=start,
        end_time=end,
        open=close if open_price is None else open_price,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def opening_candles() -> tuple[Candle, ...]:
    return (
        candle(15, 20, high=101.0, low=99.0, close=100.0),
        candle(20, 25, high=102.0, low=100.0, close=101.0),
        candle(25, 30, high=101.5, low=99.5, close=100.5),
    )


def request(*candles: Candle, timestamp=None, **overrides) -> VisionOpeningRangeRequest:
    values = {
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": TimeFrame.FIVE_MINUTES,
        "trading_date": TODAY,
        "timestamp": timestamp or datetime(2026, 7, 29, 9, 35, tzinfo=IST),
        "candles": candles or opening_candles(),
    }
    values.update(overrides)
    return VisionOpeningRangeRequest(**values)


def test_opening_range_builds_high_low_width_and_freezes_after_0930():
    result = assemble_vision_opening_range_context(request())

    assert result.opening_start_time == SESSION
    assert result.opening_end_time == datetime(2026, 7, 29, 9, 30, tzinfo=IST)
    assert result.opening_high == 102.0
    assert result.opening_low == 99.0
    assert result.opening_width == 3.0
    assert result.range_complete is True
    assert result.elapsed_minutes == 15
    assert result.quality is VisionLevelQuality.FULL


def test_waiting_state_before_opening_range_completes():
    result = assemble_vision_opening_range_context(
        request(
            candle(15, 20, high=101.0, low=99.0, close=100.0),
            candle(20, 25, high=102.0, low=100.0, close=101.0),
            timestamp=datetime(2026, 7, 29, 9, 25, tzinfo=IST),
        )
    )

    assert result.range_complete is False
    assert result.retest_state is VisionOpeningRangeState.WAITING
    assert result.break_direction is VisionBreakDirection.NONE
    assert result.current_location is VisionRangeLocation.INSIDE_RANGE
    assert result.elapsed_minutes == 10
    assert result.quality is VisionLevelQuality.PARTIAL


def test_inside_range_after_completion_has_no_break_direction():
    result = assemble_vision_opening_range_context(
        request(*opening_candles(), candle(30, 35, high=101.0, low=99.5, close=100.0))
    )

    assert result.current_location is VisionRangeLocation.INSIDE_RANGE
    assert result.break_direction is VisionBreakDirection.NONE
    assert result.retest_state is VisionOpeningRangeState.INSIDE_RANGE
    assert result.false_break is False


def test_break_above_and_break_below_are_descriptive_only():
    break_above = assemble_vision_opening_range_context(
        request(*opening_candles(), candle(30, 35, high=104.0, low=102.5, close=103.0))
    )
    break_below = assemble_vision_opening_range_context(
        request(*opening_candles(), candle(30, 35, high=98.5, low=97.0, close=98.0))
    )

    assert break_above.current_location is VisionRangeLocation.ABOVE_RANGE
    assert break_above.break_direction is VisionBreakDirection.UP
    assert break_above.retest_state is VisionOpeningRangeState.BREAK_ABOVE
    assert break_below.current_location is VisionRangeLocation.BELOW_RANGE
    assert break_below.break_direction is VisionBreakDirection.DOWN
    assert break_below.retest_state is VisionOpeningRangeState.BREAK_BELOW


def test_retest_after_break_is_classified_without_trade_logic():
    result = assemble_vision_opening_range_context(
        request(
            *opening_candles(),
            candle(30, 35, high=104.0, low=102.5, close=103.0),
            candle(35, 40, high=103.5, low=101.8, close=103.2),
            timestamp=datetime(2026, 7, 29, 9, 40, tzinfo=IST),
        )
    )

    assert result.break_direction is VisionBreakDirection.UP
    assert result.retest_state is VisionOpeningRangeState.RETEST
    assert result.false_break is False


def test_false_break_after_break_above_or_below_is_classified():
    false_above = assemble_vision_opening_range_context(
        request(
            *opening_candles(),
            candle(30, 35, high=104.0, low=102.5, close=103.0),
            candle(35, 40, high=103.0, low=100.5, close=101.0),
            timestamp=datetime(2026, 7, 29, 9, 40, tzinfo=IST),
        )
    )
    false_below = assemble_vision_opening_range_context(
        request(
            *opening_candles(),
            candle(30, 35, high=98.5, low=97.0, close=98.0),
            candle(35, 40, high=100.0, low=97.5, close=99.5),
            timestamp=datetime(2026, 7, 29, 9, 40, tzinfo=IST),
        )
    )

    assert false_above.retest_state is VisionOpeningRangeState.FALSE_BREAK
    assert false_above.false_break is True
    assert false_below.retest_state is VisionOpeningRangeState.FALSE_BREAK
    assert false_below.false_break is True


def test_invalid_session_missing_candles_incomplete_opening_and_timezone_validation():
    with pytest.raises(ValueError, match="invalid session"):
        request(session_open=time(9, 0))
    with pytest.raises(ValueError, match="missing candles"):
        request(candles=())
    with pytest.raises(ValueError, match="incomplete opening data"):
        assemble_vision_opening_range_context(
            request(
                candle(15, 20, high=101.0, low=99.0, close=100.0),
                timestamp=datetime(2026, 7, 29, 9, 31, tzinfo=IST),
            )
        )
    with pytest.raises(ValueError, match="timezone mismatch"):
        assemble_vision_opening_range_context(
            request(
                *opening_candles(),
                candle(30, 35, high=101.0, low=99.5, close=100.0, tz=timezone.utc),
            )
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        request(timestamp=datetime(2026, 7, 29, 9, 35))


def test_validator_rejects_wrong_instrument_timeframe_and_overlapping_candles():
    with pytest.raises(ValueError, match="instrument mismatch"):
        assemble_vision_opening_range_context(request(), instrument=RuntimeInstrument.BANKNIFTY)
    with pytest.raises(ValueError, match="timeframe mismatch"):
        assemble_vision_opening_range_context(request(), timeframe=TimeFrame.ONE_MINUTE)
    with pytest.raises(ValueError, match="candle instrument mismatch"):
        assemble_vision_opening_range_context(
            request(
                *opening_candles(),
                candle(30, 35, high=101.0, low=99.5, close=100.0, symbol="BANKNIFTY"),
            )
        )
    with pytest.raises(ValueError, match="overlapping"):
        assemble_vision_opening_range_context(
            request(
                *opening_candles(),
                Candle("NIFTY", "5m", datetime(2026, 7, 29, 9, 29, tzinfo=IST), datetime(2026, 7, 29, 9, 35, tzinfo=IST), 100.0, 101.0, 99.0, 100.0, 100),
            )
        )


def test_opening_range_snapshot_is_immutable():
    result = assemble_vision_opening_range_context(request())

    with pytest.raises(FrozenInstanceError):
        result.opening_high = 999.0


def test_vm03_boundary_creates_only_opening_range_module():
    package = Path("engines/vision_method")

    assert (package / "opening_range.py").exists()
    assert not (package / "engine.py").exists()
