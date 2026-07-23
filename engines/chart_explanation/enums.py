"""
Chart Explanation Engine V1 enumerations.
"""

from enum import Enum


class ChartExplanationLifecycle(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"


class ExplanationQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
