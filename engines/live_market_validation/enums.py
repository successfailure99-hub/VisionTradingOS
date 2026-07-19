from enum import Enum


class ValidationMode(str, Enum):
    OFF = "off"
    SIMULATION = "simulation"
    LIVE_OBSERVE = "live_observe"


class ValidationLifecycleState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FindingResolution(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


class ValidationComponent(str, Enum):
    MARKET_DATA = "market_data"
    CANDLE = "candle"
    PRICE_ACTION = "price_action"
    OPTION_CHAIN = "option_chain"
    MARKET_CONTEXT = "market_context"
    CPR = "cpr"
    CAMARILLA = "camarilla"
    VWAP = "vwap"
    AI_REASONING = "ai_reasoning"
    STRATEGY = "strategy"
    RISK = "risk"
    PAPER_TRADING = "paper_trading"
    PERFORMANCE_ANALYTICS = "performance_analytics"
    EVENT_FLOW = "event_flow"
    RECONNECT = "reconnect"
    PERSISTENCE = "persistence"


class ComponentStatus(str, Enum):
    NOT_ENABLED = "not_enabled"
    NOT_OBSERVED = "not_observed"
    HEALTHY = "healthy"
    WARNING = "warning"
    STALE = "stale"
    INVALID = "invalid"
    FAILED = "failed"


class ValidationHealth(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    FAILED = "failed"


class RecoveryState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECOVERING = "recovering"
    RECOVERED = "recovered"


class OptionSnapshotQuality(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    STALE = "stale"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


class ValidationOutcome(str, Enum):
    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    FAIL = "fail"
    INCOMPLETE = "incomplete"
