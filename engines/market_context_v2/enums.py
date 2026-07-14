"""
Market Context Engine V2 enumerations.
"""

from enum import Enum


class MarketDirection(str, Enum):
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"
    CONFLICTED = "conflicted"
    INSUFFICIENT_DATA = "insufficient_data"


class MarketRegime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGE_BOUND = "range_bound"
    BREAKOUT_ATTEMPT = "breakout_attempt"
    BREAKDOWN_ATTEMPT = "breakdown_attempt"
    REVERSAL_RISK = "reversal_risk"
    HIGH_CONFLICT = "high_conflict"
    INSUFFICIENT_DATA = "insufficient_data"


class TradePosture(str, Enum):
    LOOK_FOR_LONGS = "look_for_longs"
    LOOK_FOR_SHORTS = "look_for_shorts"
    WAIT_FOR_CONFIRMATION = "wait_for_confirmation"
    AVOID_NEW_TRADES = "avoid_new_trades"
    MANAGE_EXISTING_ONLY = "manage_existing_only"
    INSUFFICIENT_DATA = "insufficient_data"


class MarketEvidenceSource(str, Enum):
    PRICE_ACTION = "price_action"
    OPTION_CHAIN = "option_chain"
    CAMARILLA = "camarilla"
    CPR = "cpr"
    VWAP = "vwap"


class EvidenceDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    CONFLICTED = "conflicted"
    UNAVAILABLE = "unavailable"


class EvidenceStrength(str, Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class MarketConflictSeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class MarketContextReadiness(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
