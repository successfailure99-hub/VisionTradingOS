"""
Vision Method structural swing context assembly.

VM-04 consumes canonical immutable closed candles only. It confirms swing highs
and swing lows with deterministic left/right bars and classifies only
HH/HL/LH/LL structure. It intentionally does not detect BOS, CHoCH, MSS,
liquidity, FVG, order blocks, strategy, or trade decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle

from .enums import (
    VisionLevelQuality,
    VisionStructurePattern,
    VisionStructureTrend,
    VisionSwingType,
)
from .models import VisionStructureContext, VisionSwingPoint


DEFAULT_LEFT_BARS = 2
DEFAULT_RIGHT_BARS = 2


@dataclass(frozen=True, slots=True)
class VisionStructureRequest:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    trading_date: date
    timestamp: datetime
    candles: tuple[Candle, ...]
    left_bars: int = DEFAULT_LEFT_BARS
    right_bars: int = DEFAULT_RIGHT_BARS

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
        _validate_bar_count(self.left_bars, "left_bars")
        _validate_bar_count(self.right_bars, "right_bars")


def assemble_vision_structure_context(
    request: VisionStructureRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionStructureContext:
    """
    Assemble deterministic structural swing context from closed candles.
    """

    validate_structure_request(request, instrument=instrument, timeframe=timeframe)
    ordered = tuple(sorted(request.candles, key=lambda candle: (candle.start_time, candle.end_time)))
    swings = _detect_confirmed_swings(ordered, left_bars=request.left_bars, right_bars=request.right_bars)
    _validate_unique_swings(swings)

    highs = tuple(swing for swing in swings if swing.type is VisionSwingType.HIGH)
    lows = tuple(swing for swing in swings if swing.type is VisionSwingType.LOW)
    current_high = highs[-1] if highs else None
    previous_high = highs[-2] if len(highs) >= 2 else None
    current_low = lows[-1] if lows else None
    previous_low = lows[-2] if len(lows) >= 2 else None
    last_swing = swings[-1] if swings else None
    structure_state = _classify_latest_structure(last_swing, previous_high, previous_low)
    trend = _classify_trend(current_high, previous_high, current_low, previous_low)
    quality = VisionLevelQuality.FULL if current_high and current_low else VisionLevelQuality.PARTIAL

    return VisionStructureContext(
        current_swing_high=current_high,
        current_swing_low=current_low,
        previous_swing_high=previous_high,
        previous_swing_low=previous_low,
        trend=trend,
        structure_state=structure_state,
        last_confirmed_swing=last_swing,
        quality=quality,
    )


def validate_structure_request(
    request: VisionStructureRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionStructureRequest:
    if not isinstance(request, VisionStructureRequest):
        raise TypeError("request must be VisionStructureRequest.")
    expected_instrument = instrument or request.instrument
    expected_timeframe = timeframe or request.timeframe
    if request.instrument is not expected_instrument:
        raise ValueError("instrument mismatch.")
    if request.timeframe is not expected_timeframe:
        raise ValueError("timeframe mismatch.")
    minimum = request.left_bars + request.right_bars + 1
    if len(request.candles) < minimum:
        raise ValueError("insufficient candles.")

    previous: Candle | None = None
    for candle in sorted(request.candles, key=lambda item: (item.start_time, item.end_time)):
        _validate_candle(candle, request)
        if previous is not None:
            if candle.start_time < previous.end_time:
                raise ValueError("invalid candle sequence.")
            if candle.start_time == previous.start_time or candle.end_time == previous.end_time:
                raise ValueError("invalid candle sequence.")
        previous = candle
    return request


def _detect_confirmed_swings(
    candles: tuple[Candle, ...],
    *,
    left_bars: int,
    right_bars: int,
) -> tuple[VisionSwingPoint, ...]:
    swings: list[VisionSwingPoint] = []
    for index in range(left_bars, len(candles) - right_bars):
        candidate = candles[index]
        left = candles[index - left_bars : index]
        right = candles[index + 1 : index + 1 + right_bars]
        if all(candidate.high > candle.high for candle in (*left, *right)):
            swings.append(
                VisionSwingPoint(
                    price=candidate.high,
                    time=candidate.end_time,
                    index=index,
                    strength=left_bars + right_bars,
                    type=VisionSwingType.HIGH,
                )
            )
        if all(candidate.low < candle.low for candle in (*left, *right)):
            swings.append(
                VisionSwingPoint(
                    price=candidate.low,
                    time=candidate.end_time,
                    index=index,
                    strength=left_bars + right_bars,
                    type=VisionSwingType.LOW,
                )
            )
    return tuple(sorted(swings, key=lambda swing: (swing.index, swing.type.value)))


def _validate_unique_swings(swings: tuple[VisionSwingPoint, ...]) -> None:
    identities: set[tuple[int, VisionSwingType]] = set()
    for swing in swings:
        identity = (swing.index, swing.type)
        if identity in identities:
            raise ValueError("duplicate swing.")
        identities.add(identity)


def _classify_latest_structure(
    last_swing: VisionSwingPoint | None,
    previous_high: VisionSwingPoint | None,
    previous_low: VisionSwingPoint | None,
) -> VisionStructurePattern:
    if last_swing is None:
        return VisionStructurePattern.UNKNOWN
    if last_swing.type is VisionSwingType.HIGH:
        if previous_high is None:
            return VisionStructurePattern.UNKNOWN
        return VisionStructurePattern.HH if last_swing.price > previous_high.price else VisionStructurePattern.LH
    if previous_low is None:
        return VisionStructurePattern.UNKNOWN
    return VisionStructurePattern.HL if last_swing.price > previous_low.price else VisionStructurePattern.LL


def _classify_trend(
    current_high: VisionSwingPoint | None,
    previous_high: VisionSwingPoint | None,
    current_low: VisionSwingPoint | None,
    previous_low: VisionSwingPoint | None,
) -> VisionStructureTrend:
    if not (current_high and previous_high and current_low and previous_low):
        return VisionStructureTrend.UNKNOWN
    high_rising = current_high.price > previous_high.price
    low_rising = current_low.price > previous_low.price
    high_falling = current_high.price < previous_high.price
    low_falling = current_low.price < previous_low.price
    if high_rising and low_rising:
        return VisionStructureTrend.BULLISH
    if high_falling and low_falling:
        return VisionStructureTrend.BEARISH
    return VisionStructureTrend.RANGING


def _validate_candle(candle: Candle, request: VisionStructureRequest) -> None:
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


def _validate_bar_count(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int.")
    if value < 1:
        raise ValueError(f"{field_name} must be positive.")


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
