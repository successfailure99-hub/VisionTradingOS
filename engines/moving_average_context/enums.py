"""
Moving Average Context Engine V1 enums.
"""

from enum import Enum


class MovingAverageAlignment(Enum):
    STRONG_BULLISH = "strong_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONG_BEARISH = "strong_bearish"


class MovingAverageSlope(Enum):
    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"
    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"


class MovingAverageCompressionState(Enum):
    COMPRESSED = "compressed"
    NORMAL = "normal"
    EXPANDING = "expanding"


class MovingAverageExpansionState(Enum):
    COMPRESSED = "compressed"
    NORMAL = "normal"
    EXPANDING = "expanding"
