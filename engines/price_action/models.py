"""
Immutable Price Action Engine V1 result models.
"""

from dataclasses import dataclass
from datetime import datetime

from core.models.candle import Candle
from engines.price_action.enums import BreakType, StructureType, SwingType, Trend


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