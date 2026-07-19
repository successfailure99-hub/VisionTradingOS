from __future__ import annotations

from enum import Enum


class BacktestMode(Enum):
    SINGLE_SESSION = "single_session"
    BATCH = "batch"


class BacktestLifecycleState(Enum):
    IDLE = "idle"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class BacktestOutcome(Enum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    COMPLETED_WITH_FINDINGS = "completed_with_findings"
    FAILED = "failed"
    STOPPED = "stopped"


class BacktestSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReproducibilityStatus(Enum):
    NOT_CHECKED = "not_checked"
    MATCH = "match"
    MISMATCH = "mismatch"
