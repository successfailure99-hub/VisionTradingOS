"""
Production Safety & Recovery Engine V1 enumerations.
"""

from enum import Enum


class ProductionSafetyStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    MONITORING = "monitoring"
    DEGRADED = "degraded"
    LOCKED = "locked"
    RECOVERY_PENDING = "recovery_pending"
    STOPPED = "stopped"
    ERROR = "error"
    CLEARED = "cleared"


class SafetyScope(str, Enum):
    GLOBAL = "global"
    INSTRUMENT = "instrument"


class SafetySeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class SafetyDecision(str, Enum):
    ALLOW = "allow"
    ALLOW_WITH_WARNING = "allow_with_warning"
    BLOCK_INSTRUMENT = "block_instrument"
    BLOCK_GLOBAL = "block_global"


class SafetyRuleType(str, Enum):
    MANUAL_KILL_SWITCH = "manual_kill_switch"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    ACCOUNT_DRAWDOWN_LIMIT = "account_drawdown_limit"
    MAXIMUM_TRADES_LIMIT = "maximum_trades_limit"
    CONSECUTIVE_LOSS_LIMIT = "consecutive_loss_limit"
    MARKET_DATA_STALENESS = "market_data_staleness"
    APPLICATION_RUNTIME_HEALTH = "application_runtime_health"
    TRADE_LIFECYCLE_HEALTH = "trade_lifecycle_health"
    JOURNAL_RUNTIME_HEALTH = "journal_runtime_health"
    ACTIVE_EXECUTION_PRESENT = "active_execution_present"
    ACTIVE_POSITION_PRESENT = "active_position_present"
    DEPENDENCY_ERROR = "dependency_error"


class SafetyRuleResult(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class SafetyIncidentStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class RecoveryDecision(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    MANUAL_RELEASE_REQUIRED = "manual_release_required"
    BLOCKED_BY_ACTIVE_STATE = "blocked_by_active_state"
    BLOCKED_BY_UNHEALTHY_DEPENDENCY = "blocked_by_unhealthy_dependency"


class SafetyChange(str, Enum):
    INITIAL = "initial"
    VALIDATED = "validated"
    MONITORING_STARTED = "monitoring_started"
    BECAME_DEGRADED = "became_degraded"
    INSTRUMENT_LOCKED = "instrument_locked"
    GLOBAL_LOCKED = "global_locked"
    RECOVERY_REQUESTED = "recovery_requested"
    RECOVERY_READY = "recovery_ready"
    RECOVERED = "recovered"
    STOPPED = "stopped"
    CLEARED = "cleared"
    UNCHANGED = "unchanged"
