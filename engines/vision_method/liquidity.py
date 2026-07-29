"""
Vision Method liquidity context assembly.

VM-05 consumes canonical immutable closed candles only. It classifies equal
highs/lows, liquidity pools, liquidity sweeps, Fair Value Gaps, and an initial
order-block marker. It intentionally does not implement strategy, AI, runtime,
dashboard, option-chain confirmation, mitigation, or trade decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle

from .enums import (
    VisionBreakerBlockState,
    VisionFairValueGapDirection,
    VisionLevelQuality,
    VisionLiquidityPool,
    VisionLiquiditySweep,
    VisionMitigationState,
    VisionOrderBlockDirection,
    VisionSweepDirection,
    VisionSwingType,
)
from .models import (
    VisionBreakerBlock,
    VisionFairValueGap,
    VisionLiquidityContext,
    VisionLiquidityLevel,
    VisionOrderBlock,
)


DEFAULT_EQUAL_LEVEL_TOLERANCE_PCT = 0.0005


@dataclass(frozen=True, slots=True)
class VisionLiquidityRequest:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    trading_date: date
    timestamp: datetime
    candles: tuple[Candle, ...]
    equal_level_tolerance_pct: float = DEFAULT_EQUAL_LEVEL_TOLERANCE_PCT

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
        tolerance = _finite_number(self.equal_level_tolerance_pct, "equal_level_tolerance_pct")
        if tolerance < 0:
            raise ValueError("equal_level_tolerance_pct cannot be negative.")
        object.__setattr__(self, "equal_level_tolerance_pct", tolerance)


def assemble_vision_liquidity_context(
    request: VisionLiquidityRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionLiquidityContext:
    """
    Assemble deterministic liquidity context from closed candles.
    """

    validate_liquidity_request(request, instrument=instrument, timeframe=timeframe)
    ordered = tuple(sorted(request.candles, key=lambda candle: (candle.start_time, candle.end_time)))
    equal_highs = _detect_equal_levels(
        ordered,
        level_type=VisionSwingType.HIGH,
        tolerance_pct=request.equal_level_tolerance_pct,
    )
    equal_lows = _detect_equal_levels(
        ordered,
        level_type=VisionSwingType.LOW,
        tolerance_pct=request.equal_level_tolerance_pct,
    )
    pool = _classify_liquidity_pool(equal_highs, equal_lows)
    sweep, sweep_direction = _detect_liquidity_sweep(ordered, equal_highs, equal_lows)
    fair_value_gap = _detect_latest_fair_value_gap(ordered)
    order_block = _detect_latest_order_block(ordered)
    quality = VisionLevelQuality.FULL if equal_highs or equal_lows or fair_value_gap or order_block else VisionLevelQuality.PARTIAL

    return VisionLiquidityContext(
        equal_highs=equal_highs,
        equal_lows=equal_lows,
        liquidity_pool=pool,
        liquidity_sweep=sweep,
        sweep_direction=sweep_direction,
        fair_value_gap=fair_value_gap,
        order_block=order_block,
        breaker_block=VisionBreakerBlock(VisionBreakerBlockState.NOT_EVALUATED),
        mitigation=VisionMitigationState.NOT_EVALUATED,
        quality=quality,
    )


def validate_liquidity_request(
    request: VisionLiquidityRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionLiquidityRequest:
    if not isinstance(request, VisionLiquidityRequest):
        raise TypeError("request must be VisionLiquidityRequest.")
    expected_instrument = instrument or request.instrument
    expected_timeframe = timeframe or request.timeframe
    if request.instrument is not expected_instrument:
        raise ValueError("instrument mismatch.")
    if request.timeframe is not expected_timeframe:
        raise ValueError("timeframe mismatch.")
    if len(request.candles) < 3:
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


def _detect_equal_levels(
    candles: tuple[Candle, ...],
    *,
    level_type: VisionSwingType,
    tolerance_pct: float,
) -> tuple[VisionLiquidityLevel, ...]:
    levels: list[VisionLiquidityLevel] = []
    consumed: set[int] = set()
    values = tuple(candle.high if level_type is VisionSwingType.HIGH else candle.low for candle in candles)
    for index, price in enumerate(values):
        if index in consumed:
            continue
        indexes = [index]
        for other_index in range(index + 1, len(values)):
            if other_index in consumed:
                continue
            if _within_tolerance(price, values[other_index], tolerance_pct):
                indexes.append(other_index)
        if len(indexes) >= 2:
            consumed.update(indexes)
            level_price = sum(values[item] for item in indexes) / len(indexes)
            levels.append(
                VisionLiquidityLevel(
                    price=level_price,
                    start_time=candles[indexes[0]].end_time,
                    end_time=candles[indexes[-1]].end_time,
                    indexes=tuple(indexes),
                    type=level_type,
                    tolerance_pct=tolerance_pct,
                )
            )
    return tuple(levels)


def _classify_liquidity_pool(
    equal_highs: tuple[VisionLiquidityLevel, ...],
    equal_lows: tuple[VisionLiquidityLevel, ...],
) -> VisionLiquidityPool:
    if not equal_highs and not equal_lows:
        return VisionLiquidityPool.NONE
    if equal_highs and not equal_lows:
        return VisionLiquidityPool.BUY_SIDE
    if equal_lows and not equal_highs:
        return VisionLiquidityPool.SELL_SIDE
    latest_high_index = equal_highs[-1].indexes[-1]
    latest_low_index = equal_lows[-1].indexes[-1]
    return VisionLiquidityPool.BUY_SIDE if latest_high_index >= latest_low_index else VisionLiquidityPool.SELL_SIDE


def _detect_liquidity_sweep(
    candles: tuple[Candle, ...],
    equal_highs: tuple[VisionLiquidityLevel, ...],
    equal_lows: tuple[VisionLiquidityLevel, ...],
) -> tuple[VisionLiquiditySweep, VisionSweepDirection]:
    detected: list[tuple[int, VisionLiquiditySweep, VisionSweepDirection]] = []
    for level in equal_highs:
        for index in range(level.indexes[-1] + 1, len(candles)):
            candle = candles[index]
            if candle.high > level.price and candle.close < level.price:
                detected.append((index, VisionLiquiditySweep.BUY_SIDE_SWEEP, VisionSweepDirection.BUY_SIDE))
                break
    for level in equal_lows:
        for index in range(level.indexes[-1] + 1, len(candles)):
            candle = candles[index]
            if candle.low < level.price and candle.close > level.price:
                detected.append((index, VisionLiquiditySweep.SELL_SIDE_SWEEP, VisionSweepDirection.SELL_SIDE))
                break
    if not detected:
        return VisionLiquiditySweep.NONE, VisionSweepDirection.NONE
    if len({item[0] for item in detected}) != len(detected):
        raise ValueError("invalid sweeps.")
    _, sweep, direction = sorted(detected, key=lambda item: (item[0], item[1].value))[-1]
    return sweep, direction


def _detect_latest_fair_value_gap(candles: tuple[Candle, ...]) -> VisionFairValueGap | None:
    gaps: list[VisionFairValueGap] = []
    for index in range(0, len(candles) - 2):
        first = candles[index]
        third = candles[index + 2]
        if first.high < third.low:
            gaps.append(
                VisionFairValueGap(
                    direction=VisionFairValueGapDirection.BULLISH,
                    start_time=first.end_time,
                    end_time=third.start_time,
                    lower_bound=first.high,
                    upper_bound=third.low,
                    candle_indexes=(index, index + 1, index + 2),
                )
            )
        elif first.low > third.high:
            gaps.append(
                VisionFairValueGap(
                    direction=VisionFairValueGapDirection.BEARISH,
                    start_time=first.end_time,
                    end_time=third.start_time,
                    lower_bound=third.high,
                    upper_bound=first.low,
                    candle_indexes=(index, index + 1, index + 2),
                )
            )
    _validate_non_overlapping_gaps(gaps)
    return gaps[-1] if gaps else None


def _detect_latest_order_block(candles: tuple[Candle, ...]) -> VisionOrderBlock | None:
    latest: VisionOrderBlock | None = None
    for index in range(1, len(candles)):
        previous = candles[index - 1]
        current = candles[index]
        if _is_bearish(previous) and _is_bullish(current) and current.close > previous.high:
            latest = VisionOrderBlock(
                direction=VisionOrderBlockDirection.BULLISH,
                candle_index=index - 1,
                start_time=previous.start_time,
                end_time=previous.end_time,
                high=previous.high,
                low=previous.low,
            )
        elif _is_bullish(previous) and _is_bearish(current) and current.close < previous.low:
            latest = VisionOrderBlock(
                direction=VisionOrderBlockDirection.BEARISH,
                candle_index=index - 1,
                start_time=previous.start_time,
                end_time=previous.end_time,
                high=previous.high,
                low=previous.low,
            )
    return latest


def _validate_non_overlapping_gaps(gaps: list[VisionFairValueGap]) -> None:
    for index, gap in enumerate(gaps):
        for other in gaps[index + 1 :]:
            if max(gap.lower_bound, other.lower_bound) < min(gap.upper_bound, other.upper_bound):
                raise ValueError("overlapping gaps.")


def _within_tolerance(first: float, second: float, tolerance_pct: float) -> bool:
    anchor = max(abs(first), abs(second), 1.0)
    return abs(first - second) / anchor <= tolerance_pct


def _is_bullish(candle: Candle) -> bool:
    return candle.close > candle.open


def _is_bearish(candle: Candle) -> bool:
    return candle.close < candle.open


def _validate_candle(candle: Candle, request: VisionLiquidityRequest) -> None:
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


def _finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    normalized = float(value)
    if normalized != normalized or normalized in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite.")
    return normalized


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
