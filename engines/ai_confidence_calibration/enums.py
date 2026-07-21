"""
AI Confidence Calibration Engine V1 enumerations.
"""

from enum import Enum


class ConfidenceBand(str, Enum):
    BLOCKED = "blocked"
    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class EvidenceCategory(str, Enum):
    PRICE_ACTION = "price_action"
    OPTION_CHAIN = "option_chain"
    MARKET_CONTEXT = "market_context"
    CPR_CAMARILLA = "cpr_camarilla"
    VWAP = "vwap"
    SUPPORTING_INDICATORS = "supporting_indicators"


class EvidenceAlignment(str, Enum):
    SUPPORTS = "supports"
    CONFLICTS = "conflicts"
    NEUTRAL = "neutral"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"


class CalibrationDecision(str, Enum):
    TRUST = "trust"
    REDUCE = "reduce"
    BLOCK = "block"


class ConfidenceCalibrationLifecycle(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"
