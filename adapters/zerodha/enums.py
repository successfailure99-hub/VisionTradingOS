"""
Zerodha read-only connectivity adapter enums.
"""

from enum import Enum


class ZerodhaConnectionState(str, Enum):
    CREATED = "created"
    READY = "ready"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    STOPPED = "stopped"
    FAILED = "failed"
