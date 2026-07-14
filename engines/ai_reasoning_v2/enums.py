"""
AI Reasoning Engine V2 enumerations.
"""

from enum import Enum


class AIReasoningDirection(str, Enum):
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"
    CONFLICTED = "conflicted"
    INSUFFICIENT_DATA = "insufficient_data"


class AIConviction(str, Enum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"
    UNAVAILABLE = "unavailable"


class AIReasoningState(str, Enum):
    ACTIONABLE_CONTEXT = "actionable_context"
    WAITING_CONFIRMATION = "waiting_confirmation"
    CONFLICTED_CONTEXT = "conflicted_context"
    AVOID_CONTEXT = "avoid_context"
    INSUFFICIENT_CONTEXT = "insufficient_context"


class AIReasoningEvidenceRole(str, Enum):
    PRIMARY = "primary"
    CONFIRMATION = "confirmation"
    CONFLICT = "conflict"
    WARNING = "warning"
    UNAVAILABLE = "unavailable"


class AIReasoningImpact(str, Enum):
    SUPPORTS_BULLISH = "supports_bullish"
    SUPPORTS_BEARISH = "supports_bearish"
    SUPPORTS_NEUTRAL = "supports_neutral"
    CREATES_CONFLICT = "creates_conflict"
    REDUCES_CONFIDENCE = "reduces_confidence"
    NO_IMPACT = "no_impact"


class AIReasoningChange(str, Enum):
    INITIAL = "initial"
    STRENGTHENED = "strengthened"
    WEAKENED = "weakened"
    TURNED_BULLISH = "turned_bullish"
    TURNED_BEARISH = "turned_bearish"
    BECAME_NEUTRAL = "became_neutral"
    BECAME_CONFLICTED = "became_conflicted"
    CONFLICT_RESOLVED = "conflict_resolved"
    UNCHANGED = "unchanged"
    INSUFFICIENT_DATA = "insufficient_data"


class AICautionSeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
