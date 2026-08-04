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


def candle_at(
    start: datetime,
    minutes: int = 1,
    *,
    high: float,
    low: float,
    close: float,
    open_price: float | None = None,
    symbol: str = "NIFTY",
    timeframe: str = "1m",
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        start_time=start,
        end_time=start + timedelta(minutes=minutes),
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
    assert result.expected_candle_count == 3
    assert result.actual_candle_count == 3
    assert result.missing_candle_timestamps == ()


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


def test_live_session_opening_range_ignores_previous_session_and_post_window_candles():
    session = datetime(2026, 8, 4, 9, 15, tzinfo=IST)
    previous_session = session - timedelta(days=1)
    previous_warmup = tuple(
        candle_at(previous_session + timedelta(minutes=index), high=25053.05, low=24900.0, close=25000.0)
        for index in range(15)
    )
    current_opening = tuple(
        candle_at(session + timedelta(minutes=index), high=24620.0 + index, low=24600.75, close=24610.0)
        for index in range(15)
    )
    post_window = (candle_at(session + timedelta(minutes=15), high=25053.05, low=24700.0, close=24750.0),)

    result = assemble_vision_opening_range_context(
        VisionOpeningRangeRequest(
            instrument=RuntimeInstrument.NIFTY,
            timeframe=TimeFrame.ONE_MINUTE,
            trading_date=date(2026, 8, 4),
            timestamp=datetime(2026, 8, 4, 9, 31, tzinfo=IST),
            candles=previous_warmup + current_opening + post_window,
        )
    )

    assert result.range_complete is True
    assert result.opening_high == 24634.0
    assert result.opening_low == 24600.75
    assert result.opening_width == 33.25
    assert result.expected_candle_count == 15
    assert result.actual_candle_count == 15


def test_opening_range_waiting_at_0920_reports_counts_and_missing_timestamps():
    session = datetime(2026, 8, 4, 9, 15, tzinfo=IST)
    current = tuple(
        candle_at(session + timedelta(minutes=index), high=101.0 + index, low=99.0, close=100.0)
        for index in range(5)
    )

    result = assemble_vision_opening_range_context(
        VisionOpeningRangeRequest(
            instrument=RuntimeInstrument.NIFTY,
            timeframe=TimeFrame.ONE_MINUTE,
            trading_date=date(2026, 8, 4),
            timestamp=datetime(2026, 8, 4, 9, 20, tzinfo=IST),
            candles=current,
        )
    )

    assert result.range_complete is False
    assert result.retest_state is VisionOpeningRangeState.WAITING
    assert result.expected_candle_count == 15
    assert result.actual_candle_count == 5
    assert result.missing_candle_timestamps[0] == datetime(2026, 8, 4, 9, 20, tzinfo=IST)
    assert result.missing_candle_timestamps[-1] == datetime(2026, 8, 4, 9, 29, tzinfo=IST)


def test_opening_range_waits_at_0929_until_final_candle_closes():
    session = datetime(2026, 8, 4, 9, 15, tzinfo=IST)
    current = tuple(
        candle_at(session + timedelta(minutes=index), high=101.0 + index, low=99.0, close=100.0)
        for index in range(14)
    )

    result = assemble_vision_opening_range_context(
        VisionOpeningRangeRequest(
            instrument=RuntimeInstrument.NIFTY,
            timeframe=TimeFrame.ONE_MINUTE,
            trading_date=date(2026, 8, 4),
            timestamp=datetime(2026, 8, 4, 9, 29, tzinfo=IST),
            candles=current,
        )
    )

    assert result.range_complete is False
    assert result.expected_candle_count == 15
    assert result.actual_candle_count == 14
    assert result.missing_candle_timestamps == (datetime(2026, 8, 4, 9, 29, tzinfo=IST),)


def test_opening_range_ready_immediately_after_0930_boundary():
    session = datetime(2026, 8, 4, 9, 15, tzinfo=IST)
    current = tuple(
        candle_at(session + timedelta(minutes=index), high=101.0 + index, low=99.0, close=100.0)
        for index in range(15)
    )

    result = assemble_vision_opening_range_context(
        VisionOpeningRangeRequest(
            instrument=RuntimeInstrument.NIFTY,
            timeframe=TimeFrame.ONE_MINUTE,
            trading_date=date(2026, 8, 4),
            timestamp=datetime(2026, 8, 4, 9, 30, tzinfo=IST),
            candles=current,
        )
    )

    assert result.range_complete is True
    assert result.quality is VisionLevelQuality.FULL
    assert result.actual_candle_count == 15
    assert result.missing_candle_timestamps == ()


def test_opening_range_missing_one_candle_reports_exact_timestamp_without_wide_range():
    session = datetime(2026, 8, 4, 9, 15, tzinfo=IST)
    current = tuple(
        candle_at(session + timedelta(minutes=index), high=24620.0 + index, low=24600.75, close=24610.0)
        for index in range(15)
        if index != 7
    )
    post_window = (candle_at(session + timedelta(minutes=15), high=25053.05, low=24700.0, close=24750.0),)

    with pytest.raises(ValueError) as exc:
        assemble_vision_opening_range_context(
            VisionOpeningRangeRequest(
                instrument=RuntimeInstrument.NIFTY,
                timeframe=TimeFrame.ONE_MINUTE,
                trading_date=date(2026, 8, 4),
                timestamp=datetime(2026, 8, 4, 9, 31, tzinfo=IST),
                candles=current + post_window,
            )
        )

    message = str(exc.value)
    assert "expected_count=15" in message
    assert "actual_count=14" in message
    assert "2026-08-04T09:22:00+05:30" in message


def test_restart_at_0935_reconstructs_opening_range_without_previous_session_leakage():
    session = datetime(2026, 8, 4, 9, 15, tzinfo=IST)
    previous_session = session - timedelta(days=1)
    previous = tuple(
        candle_at(previous_session + timedelta(minutes=index), high=25053.05, low=24900.0, close=25000.0)
        for index in range(20)
    )
    current = tuple(
        candle_at(session + timedelta(minutes=index), high=24620.0 + index, low=24600.75, close=24610.0)
        for index in range(20)
    )

    result = assemble_vision_opening_range_context(
        VisionOpeningRangeRequest(
            instrument=RuntimeInstrument.NIFTY,
            timeframe=TimeFrame.ONE_MINUTE,
            trading_date=date(2026, 8, 4),
            timestamp=datetime(2026, 8, 4, 9, 35, tzinfo=IST),
            candles=previous + current,
        )
    )

    assert result.range_complete is True
    assert result.opening_high == 24634.0
    assert result.opening_low == 24600.75
    assert result.actual_candle_count == 15


def test_next_day_rollover_does_not_reuse_previous_day_opening_range():
    previous_session = datetime(2026, 8, 4, 9, 15, tzinfo=IST)
    next_session = datetime(2026, 8, 5, 9, 15, tzinfo=IST)
    previous = tuple(
        candle_at(previous_session + timedelta(minutes=index), high=25053.05, low=24900.0, close=25000.0)
        for index in range(15)
    )
    current = tuple(
        candle_at(next_session + timedelta(minutes=index), high=101.0 + index, low=99.0, close=100.0)
        for index in range(15)
    )

    result = assemble_vision_opening_range_context(
        VisionOpeningRangeRequest(
            instrument=RuntimeInstrument.NIFTY,
            timeframe=TimeFrame.ONE_MINUTE,
            trading_date=date(2026, 8, 5),
            timestamp=datetime(2026, 8, 5, 9, 30, tzinfo=IST),
            candles=previous + current,
        )
    )

    assert result.range_complete is True
    assert result.opening_high == 115.0
    assert result.opening_low == 99.0
