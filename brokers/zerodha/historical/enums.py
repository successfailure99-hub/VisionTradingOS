"""
Zerodha historical data enums.
"""

from enum import Enum


class ZerodhaHistoricalStatus(Enum):
    CREATED = "created"
    FETCHING = "fetching"
    READY = "ready"
    EMPTY = "empty"
    ERROR = "error"
    CLEARED = "cleared"


class HistoricalGapType(Enum):
    MISSING_INTERVAL = "missing_interval"
    DUPLICATE_TIMESTAMP = "duplicate_timestamp"
    OUT_OF_ORDER = "out_of_order"
