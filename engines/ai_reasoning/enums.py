"""
AI Reasoning Engine V1 enumerations.
"""

from enum import Enum


class AIMarketSummary(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    INSUFFICIENT = "insufficient"


class ReasoningConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class AgreementSummary(str, Enum):
    ALIGNED = "aligned"
    CONFLICTED = "conflicted"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class ConflictSummary(str, Enum):
    NONE = "none"
    PRIMARY_CONFLICT = "primary_conflict"
    SECONDARY_CONFLICT = "secondary_conflict"
    MIXED_SIGNALS = "mixed_signals"
    INSUFFICIENT = "insufficient"


class TradingSuitability(str, Enum):
    SUITABLE = "suitable"
    WATCHLIST = "watchlist"
    UNSUITABLE = "unsuitable"
    INSUFFICIENT = "insufficient"
