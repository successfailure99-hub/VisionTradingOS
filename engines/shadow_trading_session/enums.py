"""
Shadow Trading Session Engine V1 enums.
"""

from enum import Enum


class ShadowSessionLifecycleState(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class ShadowSessionStatus(str, Enum):
    HEALTHY = "healthy"
    HEALTHY_WITH_WARNINGS = "healthy_with_warnings"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    FAILED = "failed"
