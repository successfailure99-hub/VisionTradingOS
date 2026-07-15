"""
Trade Journal Runtime Integration V1 enumerations.
"""

from enum import Enum


class TradeJournalRuntimeIntegrationStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    CLEARED = "cleared"


class TradeJournalRoutingResult(str, Enum):
    RECORDED = "recorded"
    DUPLICATE = "duplicate"
    NOT_CLOSED = "not_closed"
    REJECTED = "rejected"
    NOT_READY = "not_ready"
    ERROR = "error"


class TradeJournalIntegrationChange(str, Enum):
    INITIAL = "initial"
    VALIDATED = "validated"
    STARTED = "started"
    TRADE_RECORDED = "trade_recorded"
    DUPLICATE_SUPPRESSED = "duplicate_suppressed"
    TRADE_REJECTED = "trade_rejected"
    STOPPED = "stopped"
    CLEARED = "cleared"
    BECAME_ERROR = "became_error"
    UNCHANGED = "unchanged"
