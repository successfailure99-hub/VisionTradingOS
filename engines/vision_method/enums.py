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


class VisionCPRRelation(str, Enum):
    ABOVE_CPR = "above_cpr"
    INSIDE_CPR = "inside_cpr"
    BELOW_CPR = "below_cpr"


class VisionCamarillaZone(str, Enum):
    ABOVE_H6 = "above_h6"
    H5_H6 = "h5_h6"
    H4_H5 = "h4_h5"
    H3_H4 = "h3_h4"
    INSIDE_VALUE = "inside_value"
    L3_L4 = "l3_l4"
    L4_L5 = "l4_l5"
    L5_L6 = "l5_l6"
    BELOW_L6 = "below_l6"


class VisionPreviousDayRelation(str, Enum):
    ABOVE_PREVIOUS_HIGH = "above_previous_high"
    INSIDE_PREVIOUS_RANGE = "inside_previous_range"
    BELOW_PREVIOUS_LOW = "below_previous_low"


class VisionGapType(str, Enum):
    GAP_UP = "gap_up"
    GAP_DOWN = "gap_down"
    NO_GAP = "no_gap"


class VisionVWAPRelation(str, Enum):
    ABOVE_VWAP = "above_vwap"
    BELOW_VWAP = "below_vwap"
    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"
    RETEST = "retest"
    REJECT = "reject"
    FAR_ABOVE = "far_above"
    FAR_BELOW = "far_below"
    UNAVAILABLE = "unavailable"


class VisionLevelQuality(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class VisionOpeningRangeState(str, Enum):
    WAITING = "waiting"
    INSIDE_RANGE = "inside_range"
    BREAK_ABOVE = "break_above"
    BREAK_BELOW = "break_below"
    RETEST = "retest"
    FALSE_BREAK = "false_break"


class VisionBreakDirection(str, Enum):
    NONE = "none"
    UP = "up"
    DOWN = "down"


class VisionRangeLocation(str, Enum):
    ABOVE_RANGE = "above_range"
    INSIDE_RANGE = "inside_range"
    BELOW_RANGE = "below_range"
