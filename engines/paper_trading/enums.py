"""
Paper Trading & Position Lifecycle V1 enumerations.
"""

from enum import Enum


class PaperOrderState(str, Enum):
    PENDING = "pending"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"


class PaperPositionState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class PaperExitType(str, Enum):
    STOP_LOSS = "stop_loss"
    TARGET = "target"
    PLAN_EXPIRED = "plan_expired"
    SESSION_CLOSE = "session_close"
    STRATEGY_INVALIDATED = "strategy_invalidated"
    MANUAL_SIMULATION_CANCEL = "manual_simulation_cancel"
    DATA_STALE = "data_stale"
    SYSTEM_SHUTDOWN = "system_shutdown"


class PaperEntryMode(str, Enum):
    RETEST = "retest"
    BREAKOUT = "breakout"


class PaperIntrabarPolicy(str, Enum):
    STOP_FIRST = "stop_first"


class ManagedPaperSubmissionStatus(str, Enum):
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
