"""
Position Management Engine V1 enumerations.
"""

from enum import Enum


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class PositionStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"
    INVALIDATED = "invalidated"
    OBJECTIVE_REACHED = "objective_reached"
    ERROR = "error"


class PositionDecision(str, Enum):
    HOLD = "hold"
    PARTIAL_EXIT = "partial_exit"
    FULL_EXIT = "full_exit"
    NO_POSITION = "no_position"


class PositionExitReason(str, Enum):
    NONE = "none"
    INVALIDATION = "invalidation"
    OBJECTIVE = "objective"
    MANUAL_DRY_RUN = "manual_dry_run"
    EXECUTION_CANCELLED = "execution_cancelled"
    EXECUTION_REJECTED = "execution_rejected"
    DATA_ERROR = "data_error"


class PositionChange(str, Enum):
    INITIAL = "initial"
    OPENED = "opened"
    PRICE_UPDATED = "price_updated"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"
    INVALIDATED = "invalidated"
    OBJECTIVE_REACHED = "objective_reached"
    UNCHANGED = "unchanged"


class PositionPnlState(str, Enum):
    PROFIT = "profit"
    LOSS = "loss"
    FLAT = "flat"
