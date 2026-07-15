"""
Price Action Engine V1 enumerations.
"""

from enum import Enum


class SwingType(str, Enum):
    HIGH = "high"
    LOW = "low"


class StructureType(str, Enum):
    HIGHER_HIGH = "higher_high"
    HIGHER_LOW = "higher_low"
    LOWER_HIGH = "lower_high"
    LOWER_LOW = "lower_low"
    EQUAL_HIGH = "equal_high"
    EQUAL_LOW = "equal_low"


class Trend(str, Enum):
    UNKNOWN = "unknown"
    RANGE = "range"
    BULLISH = "bullish"
    BEARISH = "bearish"


class BreakType(str, Enum):
    BULLISH_BOS = "bullish_bos"
    BEARISH_BOS = "bearish_bos"
    BULLISH_CHOCH = "bullish_choch"
    BEARISH_CHOCH = "bearish_choch"


class BreakDirection(str, Enum):
    NONE = "none"
    BULLISH = "bullish"
    BEARISH = "bearish"


class MarketStructure(str, Enum):
    UNKNOWN = "unknown"
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGE = "range"


class PullbackState(str, Enum):
    NONE = "none"
    BULLISH_PULLBACK = "bullish_pullback"
    BEARISH_PULLBACK = "bearish_pullback"


class RangeState(str, Enum):
    NOT_RANGE = "not_range"
    RANGE = "range"


class LiquiditySweep(str, Enum):
    NONE = "none"
    BUY_SIDE = "buy_side"
    SELL_SIDE = "sell_side"
    BOTH_SIDES = "both_sides"
