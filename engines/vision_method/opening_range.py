"""
Vision Method opening-range context assembly.

VM-03 consumes canonical immutable closed candles only. It observes the
09:15-09:30 window, freezes the opening high and low for the trading day, and
classifies descriptive context without producing strategy or trade decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import math

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.models.building_candle import INTRADAY_SESSION_OPEN
from core.models.candle import Candle

from .enums import (
    VisionBreakDirection,
    VisionLevelQuality,
    VisionOpeningRangeState,
    VisionRangeLocation,
)
from .models import VisionOpeningRangeContext


OPENING_RANGE_MINUTES = 15


@dataclass(frozen=True, slots=True)
class VisionOpeningRangeRequest:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    trading_date: date
    timestamp: datetime
    candles: tuple[Candle, ...]
    session_open: time = INTRADAY_SESSION_OPEN
    opening_minutes: int = OPENING_RANGE_MINUTES

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        if not isinstance(self.trading_date, date):
            raise TypeError("trading_date must be date.")
        _validate_aware(self.timestamp, "timestamp")
        if not isinstance(self.candles, tuple):
            raise TypeError("candles must be a tuple.")
        if not self.candles:
            raise ValueError("missing candles.")
        if not isinstance(self.session_open, time):
            raise TypeError("session_open must be time.")
        if self.session_open != INTRADAY_SESSION_OPEN:
            raise ValueError("invalid session for Vision Method opening range.")
        if isinstance(self.opening_minutes, bool) or not isinstance(self.opening_minutes, int):
            raise TypeError("opening_minutes must be int.")
        if self.opening_minutes != OPENING_RANGE_MINUTES:
            raise ValueError("invalid opening range duration.")


def assemble_vision_opening_range_context(
    request: VisionOpeningRangeRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionOpeningRangeContext:
    """
    Assemble deterministic opening-range context from closed candles.
    """

    validate_opening_range_request(request, instrument=instrument, timeframe=timeframe)
    session_start = request.timestamp.replace(
        hour=request.session_open.hour,
        minute=request.session_open.minute,
        second=0,
        microsecond=0,
    )
    session_end = session_start + timedelta(minutes=request.opening_minutes)
    expected_starts = _expected_opening_starts(request, session_start, session_end)
    expected_count = len(expected_starts)
    ordered = _session_candles(request)
    opening_candles = tuple(
        candle
        for candle in ordered
        if candle.start_time >= session_start and candle.end_time <= session_end
    )
    actual_count = len(opening_candles)
    missing_starts = _missing_opening_starts(opening_candles, expected_starts)
    if not opening_candles:
        raise ValueError(_incomplete_message(expected_starts, actual_count, missing_starts))

    range_complete = request.timestamp >= session_end
    if range_complete:
        _validate_opening_window_complete(opening_candles, expected_starts, session_end)

    opening_high = max(candle.high for candle in opening_candles)
    opening_low = min(candle.low for candle in opening_candles)
    latest_close = _latest_relevant_close(ordered, request.timestamp)
    current_location = _classify_location(latest_close, opening_high, opening_low)
    elapsed_minutes = min(
        request.opening_minutes,
        max(0, int((request.timestamp - session_start).total_seconds() // 60)),
    )

    if not range_complete:
        return VisionOpeningRangeContext(
            opening_start_time=session_start,
            opening_end_time=session_end,
            opening_high=opening_high,
            opening_low=opening_low,
            opening_width=opening_high - opening_low,
            range_complete=False,
            current_location=current_location,
            break_direction=VisionBreakDirection.NONE,
            retest_state=VisionOpeningRangeState.WAITING,
            false_break=False,
            elapsed_minutes=elapsed_minutes,
            quality=VisionLevelQuality.PARTIAL,
            expected_candle_count=expected_count,
            actual_candle_count=actual_count,
            missing_candle_timestamps=missing_starts,
        )

    post_opening = tuple(candle for candle in ordered if candle.start_time >= session_end)
    break_direction, retest_state, false_break = _classify_break_retest_false_break(
        post_opening,
        opening_high=opening_high,
        opening_low=opening_low,
    )

    return VisionOpeningRangeContext(
        opening_start_time=session_start,
        opening_end_time=session_end,
        opening_high=opening_high,
        opening_low=opening_low,
        opening_width=opening_high - opening_low,
        range_complete=True,
        current_location=current_location,
        break_direction=break_direction,
        retest_state=retest_state,
        false_break=false_break,
        elapsed_minutes=elapsed_minutes,
        quality=VisionLevelQuality.FULL,
        expected_candle_count=expected_count,
        actual_candle_count=actual_count,
        missing_candle_timestamps=(),
    )


def validate_opening_range_request(
    request: VisionOpeningRangeRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionOpeningRangeRequest:
    if not isinstance(request, VisionOpeningRangeRequest):
        raise TypeError("request must be VisionOpeningRangeRequest.")
    expected_instrument = instrument or request.instrument
    expected_timeframe = timeframe or request.timeframe
    if request.instrument is not expected_instrument:
        raise ValueError("instrument mismatch.")
    if request.timeframe is not expected_timeframe:
        raise ValueError("timeframe mismatch.")

    previous: Candle | None = None
    session_start = request.timestamp.replace(
        hour=request.session_open.hour,
        minute=request.session_open.minute,
        second=0,
        microsecond=0,
    )
    for candle in _validation_candles(request, session_start):
        _validate_candle(candle, request)
        if previous is not None and candle.start_time < previous.end_time:
            raise ValueError("overlapping opening range candles.")
        previous = candle
    return request


def _validate_candle(candle: Candle, request: VisionOpeningRangeRequest) -> None:
    if not isinstance(candle, Candle):
        raise TypeError("candles must contain Candle objects.")
    if candle.symbol != request.instrument.value:
        raise ValueError("candle instrument mismatch.")
    if candle.timeframe != request.timeframe.value:
        raise ValueError("candle timeframe mismatch.")
    _validate_aware(candle.start_time, "candle.start_time")
    _validate_aware(candle.end_time, "candle.end_time")
    if candle.start_time.utcoffset() != request.timestamp.utcoffset() or candle.end_time.utcoffset() != request.timestamp.utcoffset():
        raise ValueError("candle timezone mismatch.")
    if candle.start_time.date() != request.trading_date or candle.end_time.date() != request.trading_date:
        raise ValueError("candle trading date mismatch.")
    if candle.end_time <= candle.start_time:
        raise ValueError("candle end_time must be after start_time.")
    if candle.high < candle.low:
        raise ValueError("candle high cannot be below low.")
    if not candle.low <= candle.open <= candle.high:
        raise ValueError("candle open must be inside high/low range.")
    if not candle.low <= candle.close <= candle.high:
        raise ValueError("candle close must be inside high/low range.")


def _session_candles(request: VisionOpeningRangeRequest) -> tuple[Candle, ...]:
    return tuple(
        sorted(
            (
                candle
                for candle in request.candles
                if isinstance(candle, Candle)
                and candle.symbol == request.instrument.value
                and candle.timeframe == request.timeframe.value
                and candle.start_time.tzinfo is not None
                and candle.end_time.tzinfo is not None
                and candle.start_time.utcoffset() == request.timestamp.utcoffset()
                and candle.end_time.utcoffset() == request.timestamp.utcoffset()
                and candle.start_time.date() == request.trading_date
                and candle.end_time.date() == request.trading_date
                and candle.end_time <= request.timestamp
            ),
            key=lambda candle: (candle.start_time, candle.end_time),
        )
    )


def _validation_candles(
    request: VisionOpeningRangeRequest,
    session_start: datetime,
) -> tuple[Candle, ...]:
    return tuple(
        sorted(
            (
                candle
                for candle in request.candles
                if isinstance(candle, Candle)
                and candle.start_time.tzinfo is not None
                and candle.end_time.tzinfo is not None
                and candle.start_time.date() == request.trading_date
                and candle.end_time.date() == request.trading_date
                and candle.end_time.time() > session_start.time()
            ),
            key=lambda candle: (candle.start_time, candle.end_time),
        )
    )


def _expected_opening_starts(
    request: VisionOpeningRangeRequest,
    session_start: datetime,
    session_end: datetime,
) -> tuple[datetime, ...]:
    duration = request.timeframe.duration
    if duration.total_seconds() <= 0:
        raise ValueError("invalid opening range timeframe.")
    count = math.ceil((session_end - session_start).total_seconds() / duration.total_seconds())
    return tuple(session_start + index * duration for index in range(count))


def _missing_opening_starts(
    candles: tuple[Candle, ...],
    expected_starts: tuple[datetime, ...],
) -> tuple[datetime, ...]:
    observed = {candle.start_time for candle in candles}
    return tuple(start for start in expected_starts if start not in observed)


def _validate_opening_window_complete(
    candles: tuple[Candle, ...],
    expected_starts: tuple[datetime, ...],
    session_end: datetime,
) -> None:
    missing = _missing_opening_starts(candles, expected_starts)
    if missing or len(candles) != len(expected_starts):
        raise ValueError(_incomplete_message(expected_starts, len(candles), missing))
    for index, candle in enumerate(candles):
        if candle.start_time != expected_starts[index]:
            raise ValueError(_incomplete_message(expected_starts, len(candles), missing))
        expected_end = expected_starts[index + 1] if index + 1 < len(expected_starts) else session_end
        if candle.end_time != expected_end:
            raise ValueError(_incomplete_message(expected_starts, len(candles), missing))


def _incomplete_message(
    expected_starts: tuple[datetime, ...],
    actual_count: int,
    missing_starts: tuple[datetime, ...],
) -> str:
    missing = ", ".join(timestamp.isoformat() for timestamp in missing_starts) or "none"
    return (
        "incomplete opening data: "
        f"expected_count={len(expected_starts)}; "
        f"actual_count={actual_count}; "
        f"missing_timestamps={missing}"
    )


def _latest_relevant_close(candles: tuple[Candle, ...], timestamp: datetime) -> float:
    eligible = tuple(candle for candle in candles if candle.end_time <= timestamp)
    if not eligible:
        eligible = candles
    return eligible[-1].close


def _classify_location(price: float, opening_high: float, opening_low: float) -> VisionRangeLocation:
    if price > opening_high:
        return VisionRangeLocation.ABOVE_RANGE
    if price < opening_low:
        return VisionRangeLocation.BELOW_RANGE
    return VisionRangeLocation.INSIDE_RANGE


def _classify_break_retest_false_break(
    candles: tuple[Candle, ...],
    *,
    opening_high: float,
    opening_low: float,
) -> tuple[VisionBreakDirection, VisionOpeningRangeState, bool]:
    direction = VisionBreakDirection.NONE
    state = VisionOpeningRangeState.INSIDE_RANGE
    broken_at: int | None = None
    for index, candle in enumerate(candles):
        if candle.close > opening_high:
            direction = VisionBreakDirection.UP
            state = VisionOpeningRangeState.BREAK_ABOVE
            broken_at = index
            break
        if candle.close < opening_low:
            direction = VisionBreakDirection.DOWN
            state = VisionOpeningRangeState.BREAK_BELOW
            broken_at = index
            break

    if broken_at is None:
        return direction, state, False

    for candle in candles[broken_at + 1 :]:
        if direction is VisionBreakDirection.UP:
            if candle.close <= opening_high:
                return direction, VisionOpeningRangeState.FALSE_BREAK, True
            if candle.low <= opening_high:
                state = VisionOpeningRangeState.RETEST
        if direction is VisionBreakDirection.DOWN:
            if candle.close >= opening_low:
                return direction, VisionOpeningRangeState.FALSE_BREAK, True
            if candle.high >= opening_low:
                state = VisionOpeningRangeState.RETEST
    return direction, state, False


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
