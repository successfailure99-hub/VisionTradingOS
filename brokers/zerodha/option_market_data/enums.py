"""
Zerodha option market-data subscription enums.
"""

from enum import Enum


class ZerodhaOptionSubscriptionStatus(str, Enum):
    CREATED = "created"
    PREPARED = "prepared"
    ACTIVATING = "activating"
    ACTIVE = "active"
    REPLACING = "replacing"
    DEACTIVATING = "deactivating"
    INACTIVE = "inactive"
    ERROR = "error"
    CLEARED = "cleared"


class ZerodhaOptionSubscriptionOperation(str, Enum):
    PREPARE = "prepare"
    ACTIVATE = "activate"
    REPLACE = "replace"
    DEACTIVATE = "deactivate"
    CLEAR = "clear"
