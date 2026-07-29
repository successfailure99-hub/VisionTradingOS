"""
Vision Method V1 deterministic vocabulary.
"""

from enum import Enum


class VisionOpeningLocation(str, Enum):
    ABOVE_CPR = "above_cpr"
    INSIDE_CPR = "inside_cpr"
    BELOW_CPR = "below_cpr"


class VisionMarketRegime(str, Enum):
    TREND_DAY = "trend_day"
    RANGE_DAY = "range_day"
    EXPANSION_DAY = "expansion_day"
    COMPRESSION_DAY = "compression_day"
    TRANSITION_DAY = "transition_day"
    REVERSAL_DAY = "reversal_day"
    UNKNOWN = "unknown"


class VisionStructureState(str, Enum):
    UNKNOWN = "unknown"
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"


class VisionOptionConfirmation(str, Enum):
    CONFIRMS = "confirms"
    PARTIAL = "partial"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"


class VisionCandidateState(str, Enum):
    OBSERVE = "observe"
    WAIT = "wait"
    PREPARE_LONG = "prepare_long"
    PREPARE_SHORT = "prepare_short"
    LONG_ELIGIBLE = "long_eligible"
    SHORT_ELIGIBLE = "short_eligible"
    AVOID = "avoid"
    INSUFFICIENT_DATA = "insufficient_data"
