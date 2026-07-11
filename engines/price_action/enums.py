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