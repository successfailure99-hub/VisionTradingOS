"""
Option Chain Analytics Engine V1 enumerations.
"""

from enum import Enum


class OptionBuildUpType(str, Enum):
    LONG_BUILDUP = "long_buildup"
    SHORT_BUILDUP = "short_buildup"
    LONG_UNWINDING = "long_unwinding"
    SHORT_COVERING = "short_covering"
    NEUTRAL = "neutral"
    INSUFFICIENT_DATA = "insufficient_data"


class OptionPressureType(str, Enum):
    CALL_WRITING = "call_writing"
    PUT_WRITING = "put_writing"
    CALL_UNWINDING = "call_unwinding"
    PUT_UNWINDING = "put_unwinding"
    BALANCED = "balanced"
    MIXED = "mixed"
    INSUFFICIENT_DATA = "insufficient_data"


class OptionTrendDirection(str, Enum):
    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"
    UNKNOWN = "unknown"


class OptionLevelMigration(str, Enum):
    SHIFTED_UP = "shifted_up"
    SHIFTED_DOWN = "shifted_down"
    UNCHANGED = "unchanged"
    APPEARED = "appeared"
    DISAPPEARED = "disappeared"
    UNKNOWN = "unknown"


class OptionAnalyticsBias(str, Enum):
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"
    CONFLICTED = "conflicted"
    INSUFFICIENT_DATA = "insufficient_data"
