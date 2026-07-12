"""
Live market-data runtime lifecycle enums.
"""

from enum import Enum


class LiveMarketDataRuntimeStatus(Enum):
    CREATED = "created"
    READY = "ready"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
