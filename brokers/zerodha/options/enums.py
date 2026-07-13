"""
Zerodha option-contract discovery enums.
"""

from enum import Enum


class ZerodhaDerivativeVenue(str, Enum):
    NFO = "NFO"
    BFO = "BFO"


class ZerodhaOptionRight(str, Enum):
    CALL = "CE"
    PUT = "PE"


class ZerodhaExpiryKind(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ZerodhaExpirySelection(str, Enum):
    CURRENT = "current"
    NEXT = "next"
    CURRENT_WEEKLY = "current_weekly"
    NEXT_WEEKLY = "next_weekly"
    CURRENT_MONTHLY = "current_monthly"
    NEXT_MONTHLY = "next_monthly"
    EXPLICIT = "explicit"


class ZerodhaOptionDiscoveryStatus(str, Enum):
    CREATED = "created"
    LOADING = "loading"
    READY = "ready"
    EMPTY = "empty"
    ERROR = "error"
    CLEARED = "cleared"
