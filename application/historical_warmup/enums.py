"""
Historical warm-up and backfill status enums.
"""

from enum import Enum


class HistoricalWarmupStatus(Enum):
    CREATED = "created"
    VALIDATING = "validating"
    FETCHING = "fetching"
    APPLYING = "applying"
    READY = "ready"
    PARTIAL = "partial"
    EMPTY = "empty"
    ERROR = "error"
    CLEARED = "cleared"


class HistoricalWarmupOperation(Enum):
    WARMUP = "warmup"
    BACKFILL = "backfill"
