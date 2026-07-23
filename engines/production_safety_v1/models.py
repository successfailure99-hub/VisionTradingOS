"""
Immutable Production Safety & Recovery Engine V1 models.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real

from application.enums import ExecutionSafetyMode, RuntimeStatus
from application.trade_journal_runtime_integration_v1.models import TradeJournalRuntimeIntegrationV1Snapshot
from application.trade_lifecycle_runtime_integration_v1.models import TradeLifecycleRuntimeIntegrationV1Snapshot
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.production_safety_v1.enums import (
    ProductionSafetyStatus,
    RecoveryDecision,
    SafetyChange,
    SafetyDecision,
    SafetyIncidentStatus,
    SafetyRuleResult,
    SafetyRuleType,
    SafetyScope,
    SafetySeverity,
)
from engines.risk_management_v2.models import SUPPORTED_INSTRUMENTS, AccountRiskState, SessionRiskState


@dataclass(frozen=True, slots=True)
class ProductionSafetyV1Input:
    timestamp: datetime
    application_status: RuntimeStatus
    safety_mode: ExecutionSafetyMode
    broker_mode: BrokerExecutionMode
    lifecycle_integration_snapshot: TradeLifecycleRuntimeIntegrationV1Snapshot
    journal_integration_snapshot: TradeJournalRuntimeIntegrationV1Snapshot
    account_risk_state: AccountRiskState
    session_risk_state: SessionRiskState
    latest_market_data_at: tuple[tuple[Instrument, datetime | None], ...]

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.application_status, RuntimeStatus):
            raise TypeError("application_status must be RuntimeStatus")
        if self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            raise ValueError("safety_mode must be ANALYSIS_ONLY")
        if self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("broker_mode must be DRY_RUN")
        if not isinstance(self.lifecycle_integration_snapshot, TradeLifecycleRuntimeIntegrationV1Snapshot):
            raise TypeError("lifecycle_integration_snapshot must be TradeLifecycleRuntimeIntegrationV1Snapshot")
        if not isinstance(self.journal_integration_snapshot, TradeJournalRuntimeIntegrationV1Snapshot):
            raise TypeError("journal_integration_snapshot must be TradeJournalRuntimeIntegrationV1Snapshot")
        if not isinstance(self.account_risk_state, AccountRiskState):
            raise TypeError("account_risk_state must be AccountRiskState")
        if not isinstance(self.session_risk_state, SessionRiskState):
            raise TypeError("session_risk_state must be SessionRiskState")
        pairs = tuple(self.latest_market_data_at)
        seen = set()
        for instrument, timestamp in pairs:
            if instrument not in SUPPORTED_INSTRUMENTS:
                raise ValueError("market data instrument must be NIFTY, BANKNIFTY or SENSEX")
            if instrument in seen:
                raise ValueError("market data instruments must be unique")
            seen.add(instrument)
            if timestamp is not None:
                _aware(timestamp, "market_data_timestamp")
                if timestamp > self.timestamp:
                    raise ValueError("market data timestamp cannot be in the future")
        object.__setattr__(self, "latest_market_data_at", pairs)


@dataclass(frozen=True, slots=True)
class ManualSafetyCommand:
    timestamp: datetime
    scope: SafetyScope
    instrument: Instrument | None
    reason: str

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.scope, SafetyScope):
            raise TypeError("scope must be SafetyScope")
        if self.scope is SafetyScope.GLOBAL and self.instrument is not None:
            raise ValueError("GLOBAL command requires instrument None")
        if self.scope is SafetyScope.INSTRUMENT and self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("INSTRUMENT command requires supported instrument")
        _non_empty(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class SafetyRuleEvaluation:
    rule: SafetyRuleType
    scope: SafetyScope
    instrument: Instrument | None
    result: SafetyRuleResult
    severity: SafetySeverity
    decision: SafetyDecision
    message: str
    observed_value: float | int | str | None
    limit_value: float | int | str | None

    def __post_init__(self) -> None:
        for name, enum_type in (
            ("rule", SafetyRuleType),
            ("scope", SafetyScope),
            ("result", SafetyRuleResult),
            ("severity", SafetySeverity),
            ("decision", SafetyDecision),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be {enum_type.__name__}")
        if self.scope is SafetyScope.GLOBAL and self.instrument is not None:
            raise ValueError("GLOBAL evaluation requires instrument None")
        if self.scope is SafetyScope.INSTRUMENT and self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("INSTRUMENT evaluation requires supported instrument")
        if self.result is SafetyRuleResult.FAILED and self.decision is SafetyDecision.ALLOW:
            raise ValueError("failed rule cannot allow processing")
        if self.result is SafetyRuleResult.FAILED and self.severity is SafetySeverity.CRITICAL and self.decision not in {SafetyDecision.BLOCK_GLOBAL, SafetyDecision.BLOCK_INSTRUMENT}:
            raise ValueError("critical failure must block")
        _non_empty(self.message, "message")


@dataclass(frozen=True, slots=True)
class SafetyIncident:
    incident_id: str
    opened_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    rule: SafetyRuleType
    scope: SafetyScope
    instrument: Instrument | None
    severity: SafetySeverity
    status: SafetyIncidentStatus
    message: str
    manual_release_required: bool

    def __post_init__(self) -> None:
        _non_empty(self.incident_id, "incident_id")
        _aware(self.opened_at, "opened_at")
        _aware(self.updated_at, "updated_at")
        if self.updated_at < self.opened_at:
            raise ValueError("updated_at cannot precede opened_at")
        if self.resolved_at is not None:
            _aware(self.resolved_at, "resolved_at")
        if not isinstance(self.rule, SafetyRuleType) or not isinstance(self.scope, SafetyScope):
            raise TypeError("rule and scope must be safety enums")
        if self.scope is SafetyScope.INSTRUMENT and self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument incident requires supported instrument")
        if self.scope is SafetyScope.GLOBAL and self.instrument is not None:
            raise ValueError("global incident requires instrument None")
        if not isinstance(self.severity, SafetySeverity):
            raise TypeError("severity must be SafetySeverity")
        if not isinstance(self.status, SafetyIncidentStatus):
            raise TypeError("status must be SafetyIncidentStatus")
        if self.status is SafetyIncidentStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("resolved incident requires resolved_at")
        if type(self.manual_release_required) is not bool:
            raise TypeError("manual_release_required must be bool")
        _non_empty(self.message, "message")


@dataclass(frozen=True, slots=True)
class InstrumentSafetySnapshot:
    instrument: Instrument
    decision: SafetyDecision
    locked: bool
    degraded: bool
    market_data_age_seconds: float | None
    evaluations: tuple[SafetyRuleEvaluation, ...]
    open_incidents: tuple[SafetyIncident, ...]
    last_evaluated_at: datetime
    last_error: str | None

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if not isinstance(self.decision, SafetyDecision):
            raise TypeError("decision must be SafetyDecision")
        if type(self.locked) is not bool or type(self.degraded) is not bool:
            raise TypeError("locked and degraded must be bool")
        if self.locked != (self.decision is SafetyDecision.BLOCK_INSTRUMENT):
            raise ValueError("locked must match BLOCK_INSTRUMENT")
        if self.market_data_age_seconds is not None:
            _non_negative_real(self.market_data_age_seconds, "market_data_age_seconds")
        object.__setattr__(self, "evaluations", _tuple_of(self.evaluations, SafetyRuleEvaluation, "evaluations"))
        object.__setattr__(self, "open_incidents", _tuple_of(self.open_incidents, SafetyIncident, "open_incidents"))
        _aware(self.last_evaluated_at, "last_evaluated_at")
        if self.last_error is not None:
            _non_empty(self.last_error, "last_error")


@dataclass(frozen=True, slots=True)
class RecoveryReadinessSnapshot:
    timestamp: datetime
    decision: RecoveryDecision
    global_recovery_ready: bool
    instruments_ready: tuple[Instrument, ...]
    blocking_rules: tuple[SafetyRuleType, ...]
    blocking_incident_ids: tuple[str, ...]
    active_execution_count: int
    active_position_count: int
    message: str

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.decision, RecoveryDecision):
            raise TypeError("decision must be RecoveryDecision")
        if type(self.global_recovery_ready) is not bool:
            raise TypeError("global_recovery_ready must be bool")
        object.__setattr__(self, "instruments_ready", tuple(self.instruments_ready))
        if any(instrument not in SUPPORTED_INSTRUMENTS for instrument in self.instruments_ready):
            raise ValueError("instruments_ready must contain supported instruments")
        object.__setattr__(self, "blocking_rules", _tuple_of(self.blocking_rules, SafetyRuleType, "blocking_rules"))
        object.__setattr__(self, "blocking_incident_ids", tuple(self.blocking_incident_ids))
        for name in ("active_execution_count", "active_position_count"):
            _non_negative_int(getattr(self, name), name)
        _non_empty(self.message, "message")


@dataclass(frozen=True, slots=True)
class ProductionSafetyV1Snapshot:
    timestamp: datetime
    status: ProductionSafetyStatus
    change: SafetyChange
    decision: SafetyDecision
    severity: SafetySeverity
    global_locked: bool
    degraded: bool
    safety_mode: ExecutionSafetyMode
    broker_mode: BrokerExecutionMode
    instruments: tuple[InstrumentSafetySnapshot, ...]
    evaluations: tuple[SafetyRuleEvaluation, ...]
    open_incidents: tuple[SafetyIncident, ...]
    incident_history_size: int
    recovery: RecoveryReadinessSnapshot
    evaluation_count: int
    manual_kill_count: int
    automatic_lock_count: int
    recovery_request_count: int
    recovery_success_count: int
    error_count: int
    running: bool
    ready: bool
    last_evaluated_at: datetime | None
    last_locked_at: datetime | None
    last_recovered_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        for name, enum_type in (("status", ProductionSafetyStatus), ("change", SafetyChange), ("decision", SafetyDecision), ("severity", SafetySeverity)):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be {enum_type.__name__}")
        if type(self.global_locked) is not bool or type(self.degraded) is not bool:
            raise TypeError("global_locked and degraded must be bool")
        if self.global_locked != (self.decision is SafetyDecision.BLOCK_GLOBAL):
            raise ValueError("global_locked must match BLOCK_GLOBAL")
        if self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY or self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("production safety snapshot must remain ANALYSIS_ONLY and DRY_RUN")
        object.__setattr__(self, "instruments", _tuple_of(self.instruments, InstrumentSafetySnapshot, "instruments"))
        object.__setattr__(self, "evaluations", _tuple_of(self.evaluations, SafetyRuleEvaluation, "evaluations"))
        object.__setattr__(self, "open_incidents", _tuple_of(self.open_incidents, SafetyIncident, "open_incidents"))
        if not isinstance(self.recovery, RecoveryReadinessSnapshot):
            raise TypeError("recovery must be RecoveryReadinessSnapshot")
        for name in ("incident_history_size", "evaluation_count", "manual_kill_count", "automatic_lock_count", "recovery_request_count", "recovery_success_count", "error_count"):
            _non_negative_int(getattr(self, name), name)
        if type(self.running) is not bool or type(self.ready) is not bool:
            raise TypeError("running and ready must be bool")
        if self.running and self.status not in {ProductionSafetyStatus.MONITORING, ProductionSafetyStatus.DEGRADED, ProductionSafetyStatus.LOCKED, ProductionSafetyStatus.RECOVERY_PENDING}:
            raise ValueError("running status mismatch")
        for name in ("last_evaluated_at", "last_locked_at", "last_recovered_at"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
        if self.last_error is not None:
            _non_empty(self.last_error, "last_error")


def build_incident_id(evaluation: SafetyRuleEvaluation, timestamp: datetime) -> str:
    instrument = evaluation.instrument.value if evaluation.instrument is not None else "GLOBAL"
    return f"{evaluation.rule.value}:{evaluation.scope.value}:{instrument}:{timestamp.isoformat()}"


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _non_negative_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")


def _non_negative_real(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) or float(value) < 0.0:
        raise ValueError(f"{name} must be finite non-negative")


def _tuple_of(values, item_type, name):
    items = tuple(values)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain {item_type.__name__}")
    return items
