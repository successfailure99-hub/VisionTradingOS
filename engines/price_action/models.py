"""
Immutable Price Action Engine V1 result models.
"""

from dataclasses import dataclass
from datetime import datetime

from core.models.candle import Candle
from engines.price_action.enums import (
    BreakDirection,
    BreakType,
    LiquiditySweep,
    MarketStructure,
    PullbackState,
    RangeState,
    StructureType,
    SwingType,
    Trend,
)


@dataclass(frozen=True, slots=True)
class SwingPoint:
    symbol: str
    timeframe: str
    swing_type: SwingType
    structure_type: StructureType | None
    price: float
    candle_start_time: datetime
    candle_end_time: datetime
    candle_index: int


@dataclass(frozen=True, slots=True)
class StructureBreak:
    break_type: BreakType
    broken_price: float
    break_price: float
    candle_start_time: datetime
    candle_end_time: datetime


@dataclass(frozen=True, slots=True)
class PriceActionState:
    symbol: str
    timeframe: str
    candle_count: int
    last_candle: Candle
    trend: Trend
    latest_swing_high: SwingPoint | None
    latest_swing_low: SwingPoint | None
    previous_swing_high: SwingPoint | None
    previous_swing_low: SwingPoint | None
    latest_break: StructureBreak | None
    market_structure: MarketStructure = MarketStructure.UNKNOWN
    latest_hh: SwingPoint | None = None
    latest_hl: SwingPoint | None = None
    latest_lh: SwingPoint | None = None
    latest_ll: SwingPoint | None = None
    swing_high: SwingPoint | None = None
    swing_low: SwingPoint | None = None
    bos_direction: BreakDirection = BreakDirection.NONE
    choch_direction: BreakDirection = BreakDirection.NONE
    pullback_state: PullbackState = PullbackState.NONE
    range_state: RangeState = RangeState.NOT_RANGE
    liquidity_sweep: LiquiditySweep = LiquiditySweep.NONE
    current_structure_high: float | None = None
    current_structure_low: float | None = None
    updated_at: datetime | None = None
