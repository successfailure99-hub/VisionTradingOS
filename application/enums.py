"""
Application Orchestrator V1 enumerations.
"""

from enum import Enum


class RuntimeInstrument(str, Enum):
    NIFTY = "NIFTY"
    BANKNIFTY = "BANKNIFTY"
    SENSEX = "SENSEX"


class RuntimeStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class ExecutionSafetyMode(str, Enum):
    ANALYSIS_ONLY = "analysis_only"
    DRY_RUN = "dry_run"
