"""
Execution Runtime V1 enumerations.
"""

from enum import Enum


class ExecutionRuntimeStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    CLEARED = "cleared"


class ExecutionDecision(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WAIT = "wait"
    INSUFFICIENT_DATA = "insufficient_data"


class ExecutionSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NONE = "none"


class ExecutionOrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class ExecutionIntentStatus(str, Enum):
    CREATED = "created"
    VALIDATED = "validated"
    SUBMITTED_DRY_RUN = "submitted_dry_run"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ExecutionFillPolicy(str, Enum):
    IMMEDIATE_FULL = "immediate_full"
    IMMEDIATE_PARTIAL = "immediate_partial"
    MANUAL_CONFIRMATION = "manual_confirmation"


class ExecutionChange(str, Enum):
    INITIAL = "initial"
    INTENT_CREATED = "intent_created"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNCHANGED = "unchanged"
