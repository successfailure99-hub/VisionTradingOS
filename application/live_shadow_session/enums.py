"""
Live shadow market session coordinator enums.
"""

from enum import Enum


class LiveShadowSessionState(str, Enum):
    CREATED = "created"
    READY = "ready"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class LiveShadowSessionStatus(str, Enum):
    HEALTHY = "healthy"
    HEALTHY_WITH_WARNINGS = "healthy_with_warnings"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    FAILED = "failed"
