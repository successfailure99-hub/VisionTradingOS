"""
Trade Lifecycle Coordinator V1 enumerations.
"""

from enum import Enum


class TradeLifecycleStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    CLEARED = "cleared"


class TradeLifecycleStage(str, Enum):
    IDLE = "idle"
    CONTEXT_RECEIVED = "context_received"
    REASONING_COMPLETED = "reasoning_completed"
    STRATEGY_COMPLETED = "strategy_completed"
    RISK_COMPLETED = "risk_completed"
    EXECUTION_SUBMITTED = "execution_submitted"
    EXECUTION_ACKNOWLEDGED = "execution_acknowledged"
    EXECUTION_PARTIALLY_FILLED = "execution_partially_filled"
    EXECUTION_FILLED = "execution_filled"
    POSITION_OPEN = "position_open"
    POSITION_PARTIALLY_CLOSED = "position_partially_closed"
    POSITION_CLOSED = "position_closed"
    BLOCKED = "blocked"
    WAITING = "waiting"
    REJECTED = "rejected"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"


class TradeLifecycleOutcome(str, Enum):
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    EXECUTED_DRY_RUN = "executed_dry_run"
    POSITION_ACTIVE = "position_active"
    POSITION_CLOSED = "position_closed"
    INSUFFICIENT_DATA = "insufficient_data"
    FAILED = "failed"


class TradeLifecycleChange(str, Enum):
    INITIAL = "initial"
    STARTED = "started"
    STAGE_ADVANCED = "stage_advanced"
    BECAME_WAITING = "became_waiting"
    BECAME_BLOCKED = "became_blocked"
    BECAME_REJECTED = "became_rejected"
    EXECUTION_STARTED = "execution_started"
    POSITION_OPENED = "position_opened"
    POSITION_UPDATED = "position_updated"
    POSITION_CLOSED = "position_closed"
    RESET = "reset"
    UNCHANGED = "unchanged"


class TradeLifecycleBlockSource(str, Enum):
    NONE = "none"
    STRATEGY = "strategy"
    RISK = "risk"
    EXECUTION = "execution"
    POSITION = "position"
    DATA = "data"
    LIFECYCLE = "lifecycle"
