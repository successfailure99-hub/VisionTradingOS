"""
Zerodha market-data connection enums.
"""

from enum import Enum


class ZerodhaWebSocketStatus(Enum):
    CREATED = "created"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class ZerodhaSubscriptionMode(Enum):
    LTP = "ltp"
    QUOTE = "quote"
    FULL = "full"
