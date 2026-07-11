"""
Market Context Engine V1 enumerations.
"""

from enum import Enum


class MarketBias(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class MarketPhase(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGE = "range"
    BREAKOUT_UP = "breakout_up"
    BREAKOUT_DOWN = "breakout_down"
    REVERSAL_UP = "reversal_up"
    REVERSAL_DOWN = "reversal_down"
    UNKNOWN = "unknown"


class AgreementState(str, Enum):
    ALIGNED = "aligned"
    CONFLICTED = "conflicted"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class ContextStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


class VWAPPosition(str, Enum):
    ABOVE = "above"
    BELOW = "below"
    AT = "at"
    UNAVAILABLE = "unavailable"


class CPRPosition(str, Enum):
    ABOVE = "above"
    BELOW = "below"
    INSIDE = "inside"
    UNAVAILABLE = "unavailable"


class CamarillaZone(str, Enum):
    ABOVE_H6 = "above_h6"
    H5_TO_H6 = "h5_to_h6"
    H4_TO_H5 = "h4_to_h5"
    H3_TO_H4 = "h3_to_h4"
    L3_TO_H3 = "l3_to_h3"
    L4_TO_L3 = "l4_to_l3"
    L5_TO_L4 = "l5_to_l4"
    L6_TO_L5 = "l6_to_l5"
    BELOW_L6 = "below_l6"
    UNAVAILABLE = "unavailable"


class EvidenceDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    UNKNOWN = "unknown"