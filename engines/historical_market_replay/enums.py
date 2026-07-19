from __future__ import annotations

from enum import Enum


class ReplayLifecycleState(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class ReplayMode(str, Enum):
    OFF = "off"
    STEP = "step"
    REALTIME = "realtime"
    ACCELERATED = "accelerated"


class ReplayRecordType(str, Enum):
    TICK = "TICK"
    OPTION_CHAIN = "OPTION_CHAIN"


class ReplaySeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReplayOutcome(str, Enum):
    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    FAIL = "fail"
    INCOMPLETE = "incomplete"
    STOPPED = "stopped"
