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


class LiveFeedWatchdogState(str, Enum):
    WAITING_FIRST_TICK = "waiting_first_tick"
    HEALTHY = "healthy"
    STALE_DETECTED = "stale_detected"
    RECONNECT_SCHEDULED = "reconnect_scheduled"
    RECONNECTING = "reconnecting"
    RESUBSCRIBING = "resubscribing"
    VERIFYING_FRESH_TICK = "verifying_fresh_tick"
    RECOVERED = "recovered"
    RECOVERY_FAILED = "recovery_failed"
    MARKET_CLOSED = "market_closed"
