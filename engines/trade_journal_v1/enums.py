"""
Trade Journal & Performance Analytics V1 enumerations.
"""

from enum import Enum


class TradeOutcome(str, Enum):
    WIN = "win"
    LOSS = "loss"
    FLAT = "flat"


class TradeJournalStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    CLEARED = "cleared"


class TradeRecordStatus(str, Enum):
    RECORDED = "recorded"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class TradeCloseCategory(str, Enum):
    OBJECTIVE = "objective"
    INVALIDATION = "invalidation"
    MANUAL_DRY_RUN = "manual_dry_run"
    OTHER = "other"


class PerformanceTrend(str, Enum):
    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient_data"


class JournalChange(str, Enum):
    INITIAL = "initial"
    TRADE_RECORDED = "trade_recorded"
    DUPLICATE_SUPPRESSED = "duplicate_suppressed"
    CLEARED = "cleared"
    UNCHANGED = "unchanged"
