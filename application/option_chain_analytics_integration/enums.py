"""
Option-chain analytics runtime integration enums.
"""

from enum import Enum


class OptionChainAnalyticsIntegrationStatus(str, Enum):
    CREATED = "created"
    VALIDATING = "validating"
    READY = "ready"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    CLEARED = "cleared"


class OptionChainAnalyticsProcessingResult(str, Enum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    NOT_READY = "not_ready"
