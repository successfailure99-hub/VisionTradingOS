"""
Trade Lifecycle Runtime Integration V1 enumerations.
"""

from enum import Enum


class TradeLifecycleRuntimeIntegrationStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    CLEARED = "cleared"


class TradeLifecycleRoutingResult(str, Enum):
    PROCESSED = "processed"
    WAITING = "waiting"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    INSUFFICIENT_DATA = "insufficient_data"
    POSITION_UPDATED = "position_updated"
    DUPLICATE = "duplicate"
    NOT_READY = "not_ready"


class TradeLifecycleIntegrationChange(str, Enum):
    INITIAL = "initial"
    VALIDATED = "validated"
    STARTED = "started"
    STOPPED = "stopped"
    REQUEST_PROCESSED = "request_processed"
    POSITION_UPDATED = "position_updated"
    POSITION_CLOSED = "position_closed"
    BECAME_ERROR = "became_error"
    CLEARED = "cleared"
    UNCHANGED = "unchanged"
