"""
Vision Method structure-event context assembly.

VM-06 consumes existing Vision Method structure and liquidity context plus
canonical immutable closed candles. It classifies BOS, CHoCH, MSS,
continuation/reversal, and break strength. It intentionally does not implement
runtime, dashboard, strategy, AI, option confirmation, or trade decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle

from .enums import (
    VisionBOS,
    VisionBreakStrength,
    VisionCHoCH,
    VisionLevelQuality,
    VisionLiquiditySweep,
    VisionMSS,
    VisionReversalState,
    VisionStructureEventPhase,
    VisionStructurePattern,
    VisionStructureTrend,
)
from .models import (
    VisionLiquidityContext,
    VisionStructureContext,
    VisionStructureEventContext,
    VisionSwingPoint,
)


@dataclass(frozen=True, slots=True)
class VisionStructureEventRequest:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    trading_date: date
    timestamp: datetime
    candles: tuple[Candle, ...]
    structure_context: VisionStructureContext
    liquidity_context: VisionLiquidityContext

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
        if not isinstance(self.structure_context, VisionStructureContext):
            raise TypeError("structure_context must be VisionStructureContext.")
        if not isinstance(self.liquidity_context, VisionLiquidityContext):
            raise TypeError("liquidity_context must be VisionLiquidityContext.")


def assemble_vision_structure_event_context(
    request: VisionStructureEventRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionStructureEventContext:
    """
    Assemble deterministic structure-event context from confirmed structure.
    """

    validate_structure_event_request(request, instrument=instrument, timeframe=timeframe)
    ordered = tuple(sorted(request.candles, key=lambda candle: (candle.start_time, candle.end_time)))
    latest = ordered[-1]
    event = _classify_event(latest, request.structure_context)
    strength = _classify_break_strength(
        latest,
        ordered,
        request.structure_context,
        request.liquidity_context,
        event,
    )
    quality = VisionLevelQuality.FULL if event.bos is not VisionBOS.NONE or event.choch is not VisionCHoCH.NONE else VisionLevelQuality.PARTIAL

    result = VisionStructureEventContext(
        bos=event.bos,
        choch=event.choch,
        mss=event.mss,
        continuation=event.continuation,
        reversal=event.reversal,
        break_strength=strength,
        quality=quality,
    )
    validate_structure_event_context(result)
    return result


def validate_structure_event_request(
    request: VisionStructureEventRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionStructureEventRequest:
    if not isinstance(request, VisionStructureEventRequest):
        raise TypeError("request must be VisionStructureEventRequest.")
    expected_instrument = instrument or request.instrument
    expected_timeframe = timeframe or request.timeframe
    if request.instrument is not expected_instrument:
        raise ValueError("instrument mismatch.")
    if request.timeframe is not expected_timeframe:
        raise ValueError("timeframe mismatch.")
    if request.structure_context.quality is VisionLevelQuality.INSUFFICIENT:
        raise ValueError("insufficient structure context.")
    if request.liquidity_context.quality is VisionLevelQuality.INSUFFICIENT:
        raise ValueError("insufficient liquidity context.")
    if len(request.candles) < 2:
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


def validate_structure_event_context(context: VisionStructureEventContext) -> VisionStructureEventContext:
    if not isinstance(context, VisionStructureEventContext):
        raise TypeError("context must be VisionStructureEventContext.")
    return context


@dataclass(frozen=True, slots=True)
class _ClassifiedEvent:
    bos: VisionBOS
    choch: VisionCHoCH
    mss: VisionMSS
    continuation: VisionStructureEventPhase
    reversal: VisionReversalState


def _classify_event(candle: Candle, structure: VisionStructureContext) -> _ClassifiedEvent:
    bullish_break = _breaks_above(candle, structure.current_swing_high)
    bearish_break = _breaks_below(candle, structure.current_swing_low)
    if bullish_break and bearish_break:
        raise ValueError("duplicate events.")

    bullish_structure = structure.trend is VisionStructureTrend.BULLISH or structure.structure_state in (
        VisionStructurePattern.HH,
        VisionStructurePattern.HL,
    )
    bearish_structure = structure.trend is VisionStructureTrend.BEARISH or structure.structure_state in (
        VisionStructurePattern.LH,
        VisionStructurePattern.LL,
    )

    if bullish_break and bullish_structure:
        return _ClassifiedEvent(
            bos=VisionBOS.BULLISH_BOS,
            choch=VisionCHoCH.NONE,
            mss=VisionMSS.NONE,
            continuation=VisionStructureEventPhase.CONTINUATION,
            reversal=VisionReversalState.NONE,
        )
    if bearish_break and bearish_structure:
        return _ClassifiedEvent(
            bos=VisionBOS.BEARISH_BOS,
            choch=VisionCHoCH.NONE,
            mss=VisionMSS.NONE,
            continuation=VisionStructureEventPhase.CONTINUATION,
            reversal=VisionReversalState.NONE,
        )
    if bullish_break and bearish_structure:
        return _ClassifiedEvent(
            bos=VisionBOS.NONE,
            choch=VisionCHoCH.BULLISH_CHOCH,
            mss=VisionMSS.MARKET_STRUCTURE_SHIFT,
            continuation=VisionStructureEventPhase.REVERSAL,
            reversal=VisionReversalState.BULLISH_REVERSAL,
        )
    if bearish_break and bullish_structure:
        return _ClassifiedEvent(
            bos=VisionBOS.NONE,
            choch=VisionCHoCH.BEARISH_CHOCH,
            mss=VisionMSS.MARKET_STRUCTURE_SHIFT,
            continuation=VisionStructureEventPhase.REVERSAL,
            reversal=VisionReversalState.BEARISH_REVERSAL,
        )
    return _ClassifiedEvent(
        bos=VisionBOS.NONE,
        choch=VisionCHoCH.NONE,
        mss=VisionMSS.NONE,
        continuation=VisionStructureEventPhase.NONE,
        reversal=VisionReversalState.NONE,
    )


def _classify_break_strength(
    latest: Candle,
    candles: tuple[Candle, ...],
    structure: VisionStructureContext,
    liquidity: VisionLiquidityContext,
    event: _ClassifiedEvent,
) -> VisionBreakStrength:
    if event.bos is VisionBOS.NONE and event.choch is VisionCHoCH.NONE:
        return VisionBreakStrength.NONE

    broken_level = _broken_level(structure, event)
    if broken_level is None:
        raise ValueError("impossible structure event.")
    recent_ranges = tuple(candle.high - candle.low for candle in candles[:-1])[-5:]
    average_range = sum(recent_ranges) / len(recent_ranges) if recent_ranges else latest.high - latest.low
    break_distance = abs(latest.close - broken_level.price)
    distance_score = break_distance / average_range if average_range > 0 else 0.0
    liquidity_bonus = _liquidity_supports_event(liquidity, event)

    if distance_score >= 0.75 or (distance_score >= 0.35 and liquidity_bonus):
        return VisionBreakStrength.STRONG
    if distance_score >= 0.2 or liquidity_bonus:
        return VisionBreakStrength.NORMAL
    return VisionBreakStrength.WEAK


def _broken_level(structure: VisionStructureContext, event: _ClassifiedEvent) -> VisionSwingPoint | None:
    if event.bos is VisionBOS.BULLISH_BOS or event.choch is VisionCHoCH.BULLISH_CHOCH:
        return structure.current_swing_high
    if event.bos is VisionBOS.BEARISH_BOS or event.choch is VisionCHoCH.BEARISH_CHOCH:
        return structure.current_swing_low
    return None


def _liquidity_supports_event(liquidity: VisionLiquidityContext, event: _ClassifiedEvent) -> bool:
    if event.bos is VisionBOS.BULLISH_BOS or event.choch is VisionCHoCH.BULLISH_CHOCH:
        return liquidity.liquidity_sweep is VisionLiquiditySweep.SELL_SIDE_SWEEP
    if event.bos is VisionBOS.BEARISH_BOS or event.choch is VisionCHoCH.BEARISH_CHOCH:
        return liquidity.liquidity_sweep is VisionLiquiditySweep.BUY_SIDE_SWEEP
    return False


def _breaks_above(candle: Candle, swing: VisionSwingPoint | None) -> bool:
    return swing is not None and candle.close > swing.price


def _breaks_below(candle: Candle, swing: VisionSwingPoint | None) -> bool:
    return swing is not None and candle.close < swing.price


def _validate_candle(candle: Candle, request: VisionStructureEventRequest) -> None:
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


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
