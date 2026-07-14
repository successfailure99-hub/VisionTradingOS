"""
Live option-chain runtime enums.
"""

from enum import Enum


class LiveOptionChainStatus(str, Enum):
    CREATED = "created"
    CONFIGURED = "configured"
    COLLECTING = "collecting"
    READY = "ready"
    PARTIAL = "partial"
    STALE = "stale"
    ERROR = "error"
    STOPPED = "stopped"
    CLEARED = "cleared"


class LiveOptionQuoteUpdateResult(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    STALE = "stale"
    REJECTED = "rejected"
