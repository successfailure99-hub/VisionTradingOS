"""
Multi-Timeframe Evidence Fusion Engine V1 enumerations.
"""

from enum import Enum


class FusionLifecycle(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"


class FusionDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class EvidenceAgreement(str, Enum):
    FULL_ALIGNMENT = "full_alignment"
    PARTIAL_ALIGNMENT = "partial_alignment"
    MIXED = "mixed"
    CONFLICT = "conflict"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceConflict(str, Enum):
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    INSUFFICIENT = "insufficient"


class EvidenceCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
