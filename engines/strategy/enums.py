"""
Strategy Engine V1 enumerations.
"""

from enum import Enum


class StrategyDecision(str, Enum):
    TRADE_ELIGIBLE = "trade_eligible"
    NO_TRADE = "no_trade"


class TradeDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NONE = "none"


class SetupQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REJECTED = "rejected"


class EntryReference(str, Enum):
    PRICE_ACTION_RETEST = "price_action_retest"
    STRUCTURE_BREAK_RETEST = "structure_break_retest"
    NONE = "none"


class StopReference(str, Enum):
    LATEST_SWING = "latest_swing"
    BROKEN_STRUCTURE = "broken_structure"
    NONE = "none"


class TargetReference(str, Enum):
    NEXT_STRUCTURE = "next_structure"
    CAMARILLA_LEVEL = "camarilla_level"
    OPTION_OI_LEVEL = "option_oi_level"
    NONE = "none"


class BlockReason(str, Enum):
    NONE = "none"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    PRIMARY_CONFLICT = "primary_conflict"
    SECONDARY_CONFLICT = "secondary_conflict"
    UNSUITABLE_CONTEXT = "unsuitable_context"
    LOW_CONFIDENCE = "low_confidence"
    NEUTRAL_BIAS = "neutral_bias"
    MIXED_BIAS = "mixed_bias"
    UNKNOWN_BIAS = "unknown_bias"
    DIRECTION_MISMATCH = "direction_mismatch"
    MISSING_PRIMARY_DATA = "missing_primary_data"
