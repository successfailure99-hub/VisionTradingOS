"""
Market State Engine V1 enumerations.
"""

from enum import Enum


class MarketStateLifecycle(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"


class MarketState(str, Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    TRANSITION = "transition"
    EXPANSION = "expansion"
    COMPRESSION = "compression"
    VOLATILE = "volatile"
    QUIET = "quiet"
    BALANCED = "balanced"


class MarketPhase(str, Enum):
    EARLY = "early"
    DEVELOPING = "developing"
    MATURE = "mature"
    EXHAUSTING = "exhausting"


class MarketStability(str, Enum):
    STABLE = "stable"
    UNSTABLE = "unstable"
    CHANGING = "changing"


class VolatilityState(str, Enum):
    QUIET = "quiet"
    NORMAL = "normal"
    VOLATILE = "volatile"


class MarketEvidenceQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class StructuralConfidence(str, Enum):
    HIGH_STRUCTURE = "high_structure"
    MEDIUM_STRUCTURE = "medium_structure"
    LOW_STRUCTURE = "low_structure"
