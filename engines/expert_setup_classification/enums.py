"""
Expert Setup Classification Engine V1 enumerations.
"""

from enum import Enum


class SetupClassificationLifecycle(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"


class ExpertSetup(str, Enum):
    TREND_CONTINUATION = "trend_continuation"
    PULLBACK_CONTINUATION = "pullback_continuation"
    BREAKOUT = "breakout"
    FAILED_BREAKOUT = "failed_breakout"
    RANGE_DAY = "range_day"
    TREND_DAY = "trend_day"
    COMPRESSION = "compression"
    EXPANSION = "expansion"
    BULL_TRAP = "bull_trap"
    BEAR_TRAP = "bear_trap"
    REVERSAL_ATTEMPT = "reversal_attempt"
    LIQUIDITY_SWEEP = "liquidity_sweep"
    NO_QUALITY_SETUP = "no_quality_setup"


class SetupStrength(str, Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class SetupQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SetupStability(str, Enum):
    STABLE = "stable"
    CHANGING = "changing"
    UNSTABLE = "unstable"
