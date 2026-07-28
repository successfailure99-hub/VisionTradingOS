"""
Zerodha market-data connection enums.
"""

from enum import Enum


class ZerodhaWebSocketStatus(Enum):
    CREATED = "created"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECT_WAIT = "reconnect_wait"
    DISCONNECTING = "disconnecting"
    STOPPED = "stopped"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class ZerodhaSubscriptionMode(Enum):
    LTP = "ltp"
    QUOTE = "quote"
    FULL = "full"
