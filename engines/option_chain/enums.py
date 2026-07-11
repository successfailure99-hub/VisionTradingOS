"""
Option Chain Engine V1 enumerations.
"""

from enum import Enum


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class PositioningBias(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class PressureType(str, Enum):
    CALL_WRITING = "call_writing"
    CALL_UNWINDING = "call_unwinding"
    PUT_WRITING = "put_writing"
    PUT_UNWINDING = "put_unwinding"
    BALANCED = "balanced"
    UNKNOWN = "unknown"