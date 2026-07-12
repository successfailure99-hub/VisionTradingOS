"""
Zerodha instrument discovery enums.
"""

from enum import Enum


class ZerodhaInstrumentType(Enum):
    INDEX = "index"
    EQUITY = "equity"
    FUTURE = "future"
    OPTION = "option"
    UNKNOWN = "unknown"


class ZerodhaInstrumentDiscoveryStatus(Enum):
    CREATED = "created"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"
    CLEARED = "cleared"
