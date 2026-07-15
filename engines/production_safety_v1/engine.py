"""
Production Safety & Recovery Engine V1.
"""

from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock

from core.base_engine import BaseEngine
from core.event_bus import EventBus
from core.enums.instrument import Instrument
from core.events import (
    PRODUCTION_SAFETY_ERROR,
    PRODUCTION_SAFETY_INCIDENT_OPENED,
    PRODUCTION_SAFETY_INCIDENT_RESOLVED,
    PRODUCTION_SAFETY_RECOVERY_PENDING,
    PRODUCTION_SAFETY_RECOVERED,
    PRODUCTION_SAFETY_V1_DEGRADED,
    PRODUCTION_SAFETY_V1_LOCKED,
    PRODUCTION_SAFETY_V1_READY,
    PRODUCTION_SAFETY_V1_UPDATED,
)
from engines.production_safety_v1.configuration import ProductionSafetyV1Configuration
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
from engines.production_safety_v1.evaluator import ProductionSafetyEvaluator
from engines.production_safety_v1.models import (
    InstrumentSafetySnapshot,
    ManualSafetyCommand,
    ProductionSafetyV1Input,
    ProductionSafetyV1Snapshot,
    RecoveryReadinessSnapshot,
    SafetyIncident,
    SafetyRuleEvaluation,
    build_incident_id,
)
from engines.production_safety_v1.recovery import ProductionRecoveryEvaluator


class ProductionSafetyV1Engine(BaseEngine):
    def __init__(
        self,
        *,
        configuration: ProductionSafetyV1Configuration | None = None,
        evaluator: ProductionSafetyEvaluator | None = None,
        recovery_evaluator: ProductionRecoveryEvaluator | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ):
        super().__init__(event_bus or EventBus())
        self._configuration = configuration or ProductionSafetyV1Configuration()
        self._evaluator = evaluator or ProductionSafetyEvaluator()
        self._recovery_evaluator = recovery_evaluator or ProductionRecoveryEvaluator()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._status = ProductionSafetyStatus.CREATED
        self._change = SafetyChange.INITIAL
        self._manual_global_lock = False
        self._manual_instrument_locks: tuple[Instrument, ...] = ()
        self._evaluations: tuple[SafetyRuleEvaluation, ...] = ()
        self._incidents: tuple[SafetyIncident, ...] = ()
        self._snapshot_history: tuple[ProductionSafetyV1Snapshot, ...] = ()
        self._last_input = None
        self._last_snapshot_for_input = None
        self._evaluation_count = 0
        self._manual_kill_count = 0
        self._automatic_lock_count = 0
        self._recovery_request_count = 0
        self._recovery_success_count = 0
        self._error_count = 0
        self._last_evaluated_at = None
        self._last_locked_at = None
        self._last_recovered_at = None
        self._last_error = None
        self._recovery = self._empty_recovery(self._now())
        self._data = self.snapshot()

    def start(self) -> ProductionSafetyV1Snapshot:
        with self._lock:
            if self._status in {ProductionSafetyStatus.MONITORING, ProductionSafetyStatus.DEGRADED, ProductionSafetyStatus.LOCKED}:
                return self.snapshot()
            self._status = ProductionSafetyStatus.MONITORING
            self._change = SafetyChange.MONITORING_STARTED
            self._last_error = None
            snapshot = self._store_snapshot()
        self._event_bus.publish(PRODUCTION_SAFETY_V1_READY, snapshot)
        return snapshot

    def stop(self) -> ProductionSafetyV1Snapshot:
        with self._lock:
            if self._status is ProductionSafetyStatus.STOPPED:
                return self.snapshot()
            self._status = ProductionSafetyStatus.STOPPED
            self._change = SafetyChange.STOPPED
            snapshot = self._store_snapshot()
        self._event_bus.publish(PRODUCTION_SAFETY_V1_UPDATED, snapshot)
        return snapshot

    def evaluate(self, inputs: ProductionSafetyV1Input) -> ProductionSafetyV1Snapshot:
        if not isinstance(inputs, ProductionSafetyV1Input):
            raise TypeError("inputs must be ProductionSafetyV1Input")
        with self._lock:
            if self._status not in {ProductionSafetyStatus.MONITORING, ProductionSafetyStatus.DEGRADED, ProductionSafetyStatus.LOCKED, ProductionSafetyStatus.RECOVERY_PENDING}:
                raise RuntimeError("production safety engine must be monitoring")
            if self._last_input == inputs and self._last_snapshot_for_input is not None:
                return self._last_snapshot_for_input
            if self._last_input is not None and inputs.timestamp < self._last_input.timestamp:
                raise ValueError("stale production safety input")
            try:
                evaluations = self._evaluator.evaluate(inputs, self._configuration, manual_global_lock=self._manual_global_lock, manual_instrument_locks=self._manual_instrument_locks)
                opened, resolved = self._update_incidents(evaluations, inputs.timestamp)
                active_execution = sum(item.coordinator_snapshot.execution_snapshot.open_intent_count for item in inputs.lifecycle_integration_snapshot.instruments)
                active_position = sum(1 for item in inputs.lifecycle_integration_snapshot.instruments if item.coordinator_snapshot.position_snapshot.has_open_position)
                self._recovery = self._recovery_evaluator.evaluate(snapshot=self._data if isinstance(self._data, ProductionSafetyV1Snapshot) else None, current_evaluations=evaluations, open_incidents=self.open_incidents(), active_execution_count=active_execution, active_position_count=active_position, configuration=self._configuration, timestamp=inputs.timestamp)
                self._evaluations = evaluations
                self._evaluation_count += 1
                self._last_evaluated_at = inputs.timestamp
                self._apply_decision_state(evaluations)
                self._last_input = inputs
                snapshot = self._store_snapshot(replace_latest=self._last_snapshot_for_input is not None and inputs.timestamp == self._last_snapshot_for_input.timestamp)
                self._last_snapshot_for_input = snapshot
            except Exception as exc:
                self._status = ProductionSafetyStatus.ERROR
                self._change = SafetyChange.UNCHANGED
                self._error_count += 1
                self._last_error = _safe_error(exc)
                snapshot = self._store_snapshot()
                self._event_bus.publish(PRODUCTION_SAFETY_ERROR, snapshot)
                raise
        for incident in opened:
            self._event_bus.publish(PRODUCTION_SAFETY_INCIDENT_OPENED, incident)
        for incident in resolved:
            self._event_bus.publish(PRODUCTION_SAFETY_INCIDENT_RESOLVED, incident)
        self._publish_snapshot(snapshot)
        return snapshot

    def activate_global_kill_switch(self, command: ManualSafetyCommand) -> ProductionSafetyV1Snapshot:
        if command.scope is not SafetyScope.GLOBAL:
            raise ValueError("global kill switch requires GLOBAL command")
        with self._lock:
            if self._manual_global_lock:
                return self._data if isinstance(self._data, ProductionSafetyV1Snapshot) else self.snapshot()
            self._manual_global_lock = True
            self._manual_kill_count += 1
            self._last_locked_at = command.timestamp
            self._refresh_evaluations_for_manual_command(command.timestamp)
            self._status = ProductionSafetyStatus.LOCKED
            self._change = SafetyChange.GLOBAL_LOCKED
            snapshot = self._store_snapshot()
        self._event_bus.publish(PRODUCTION_SAFETY_V1_LOCKED, snapshot)
        return snapshot

    def activate_instrument_kill_switch(self, command: ManualSafetyCommand) -> ProductionSafetyV1Snapshot:
        if command.scope is not SafetyScope.INSTRUMENT or command.instrument is None:
            raise ValueError("instrument kill switch requires INSTRUMENT command")
        with self._lock:
            if command.instrument not in self._manual_instrument_locks:
                self._manual_instrument_locks += (command.instrument,)
            self._manual_kill_count += 1
            self._last_locked_at = command.timestamp
            self._refresh_evaluations_for_manual_command(command.timestamp)
            if _overall_decision(self._evaluations) is SafetyDecision.BLOCK_GLOBAL:
                self._status = ProductionSafetyStatus.LOCKED
                self._change = SafetyChange.GLOBAL_LOCKED
            else:
                self._status = ProductionSafetyStatus.DEGRADED
                self._change = SafetyChange.INSTRUMENT_LOCKED
            snapshot = self._store_snapshot()
        self._event_bus.publish(PRODUCTION_SAFETY_V1_DEGRADED, snapshot)
        return snapshot

    def request_recovery(self, inputs: ProductionSafetyV1Input) -> ProductionSafetyV1Snapshot:
        with self._lock:
            if self._status not in {ProductionSafetyStatus.LOCKED, ProductionSafetyStatus.DEGRADED, ProductionSafetyStatus.ERROR, ProductionSafetyStatus.RECOVERY_PENDING}:
                raise RuntimeError("recovery can be requested only from locked, degraded or error state")
            self._recovery_request_count += 1
        snapshot = self.evaluate(inputs)
        with self._lock:
            self._status = ProductionSafetyStatus.RECOVERY_PENDING
            self._change = SafetyChange.RECOVERY_READY if self._recovery.decision is RecoveryDecision.READY else SafetyChange.RECOVERY_REQUESTED
            snapshot = self._store_snapshot()
        self._event_bus.publish(PRODUCTION_SAFETY_RECOVERY_PENDING, snapshot)
        return snapshot

    def release_global_kill_switch(self, *, timestamp: datetime, reason: str) -> ProductionSafetyV1Snapshot:
        _aware(timestamp)
        _non_empty(reason)
        with self._lock:
            if not self._manual_global_lock:
                raise RuntimeError("global kill switch is not active")
            if self._recovery.decision is not RecoveryDecision.READY and self._recovery.decision is not RecoveryDecision.MANUAL_RELEASE_REQUIRED:
                raise RuntimeError("global release is not safe yet")
            self._manual_global_lock = False
            self._recovery_success_count += 1
            self._refresh_evaluations_for_manual_command(timestamp)
            self._resolve_manual(SafetyScope.GLOBAL, None, timestamp)
            self._refresh_recovery(timestamp)
            if _overall_decision(self._evaluations) is SafetyDecision.BLOCK_GLOBAL:
                self._status = ProductionSafetyStatus.LOCKED
                self._change = SafetyChange.GLOBAL_LOCKED
            elif _overall_decision(self._evaluations) is SafetyDecision.BLOCK_INSTRUMENT:
                self._status = ProductionSafetyStatus.DEGRADED
                self._change = SafetyChange.INSTRUMENT_LOCKED
            elif _overall_decision(self._evaluations) is SafetyDecision.ALLOW_WITH_WARNING:
                self._status = ProductionSafetyStatus.DEGRADED
                self._change = SafetyChange.BECAME_DEGRADED
            else:
                self._status = ProductionSafetyStatus.MONITORING
                self._change = SafetyChange.RECOVERED
            self._last_recovered_at = timestamp
            snapshot = self._store_snapshot()
        self._event_bus.publish(PRODUCTION_SAFETY_RECOVERED, snapshot)
        return snapshot

    def release_instrument_kill_switch(self, *, instrument: Instrument, timestamp: datetime, reason: str) -> ProductionSafetyV1Snapshot:
        _aware(timestamp)
        _non_empty(reason)
        with self._lock:
            if instrument in self._manual_instrument_locks:
                self._manual_instrument_locks = tuple(item for item in self._manual_instrument_locks if item is not instrument)
                self._recovery_success_count += 1
            self._resolve_manual(SafetyScope.INSTRUMENT, instrument, timestamp)
            self._status = ProductionSafetyStatus.MONITORING if not self._manual_global_lock and not self._manual_instrument_locks else ProductionSafetyStatus.DEGRADED
            self._change = SafetyChange.RECOVERED
            self._last_recovered_at = timestamp
            snapshot = self._store_snapshot()
        self._event_bus.publish(PRODUCTION_SAFETY_RECOVERED, snapshot)
        return snapshot

    def snapshot(self) -> ProductionSafetyV1Snapshot:
        evaluations = self._evaluations
        decision = _overall_decision(evaluations)
        severity = _highest_severity(evaluations)
        instruments = tuple(self._instrument_snapshot(instrument) for instrument in self._configuration.enabled_instruments)
        return ProductionSafetyV1Snapshot(
            timestamp=self._now(),
            status=self._status,
            change=self._change,
            decision=decision,
            severity=severity,
            global_locked=decision is SafetyDecision.BLOCK_GLOBAL,
            degraded=decision in {SafetyDecision.ALLOW_WITH_WARNING, SafetyDecision.BLOCK_INSTRUMENT} or any(item.locked or item.degraded for item in instruments),
            safety_mode=self._configuration.safety_mode,
            broker_mode=self._configuration.broker_mode,
            instruments=instruments,
            evaluations=evaluations,
            open_incidents=self.open_incidents(),
            incident_history_size=len(self._incidents),
            recovery=self._recovery,
            evaluation_count=self._evaluation_count,
            manual_kill_count=self._manual_kill_count,
            automatic_lock_count=self._automatic_lock_count,
            recovery_request_count=self._recovery_request_count,
            recovery_success_count=self._recovery_success_count,
            error_count=self._error_count,
            running=self._status in {ProductionSafetyStatus.MONITORING, ProductionSafetyStatus.DEGRADED, ProductionSafetyStatus.LOCKED, ProductionSafetyStatus.RECOVERY_PENDING},
            ready=self._status not in {ProductionSafetyStatus.ERROR, ProductionSafetyStatus.CLEARED},
            last_evaluated_at=self._last_evaluated_at,
            last_locked_at=self._last_locked_at,
            last_recovered_at=self._last_recovered_at,
            last_error=self._last_error,
        )

    def incident_history(self) -> tuple[SafetyIncident, ...]:
        return self._incidents

    def open_incidents(self) -> tuple[SafetyIncident, ...]:
        return tuple(incident for incident in self._incidents if incident.status is not SafetyIncidentStatus.RESOLVED)

    def snapshot_history(self) -> tuple[ProductionSafetyV1Snapshot, ...]:
        return self._snapshot_history

    def clear(self) -> ProductionSafetyV1Snapshot:
        with self._lock:
            if self._status is not ProductionSafetyStatus.STOPPED:
                raise RuntimeError("production safety engine must be stopped before clear")
            if self._manual_global_lock or self._manual_instrument_locks:
                raise RuntimeError("manual kill switches must be released before clear")
            if any(incident.status is not SafetyIncidentStatus.RESOLVED and incident.severity is SafetySeverity.CRITICAL for incident in self._incidents):
                raise RuntimeError("unresolved critical incidents block clear")
            self._evaluations = ()
            self._incidents = ()
            self._snapshot_history = ()
            self._evaluation_count = self._manual_kill_count = self._automatic_lock_count = 0
            self._recovery_request_count = self._recovery_success_count = self._error_count = 0
            self._status = ProductionSafetyStatus.CLEARED
            self._change = SafetyChange.CLEARED
            snapshot = self.snapshot()
            self._data = snapshot
            return snapshot

    def _update_incidents(self, evaluations, timestamp):
        opened = []
        resolved = []
        incidents = list(self._incidents)
        active_keys = {_incident_key(ev) for ev in evaluations if ev.result is SafetyRuleResult.FAILED}
        for ev in evaluations:
            key = _incident_key(ev)
            existing_index = next((i for i, item in enumerate(incidents) if _incident_key(item) == key and item.status is not SafetyIncidentStatus.RESOLVED), None)
            if ev.result is SafetyRuleResult.FAILED:
                manual = _manual_required(ev, self._configuration)
                if existing_index is None:
                    incident = SafetyIncident(build_incident_id(ev, timestamp), timestamp, timestamp, None, ev.rule, ev.scope, ev.instrument, ev.severity, SafetyIncidentStatus.OPEN, ev.message, manual)
                    incidents.append(incident)
                    opened.append(incident)
                    if ev.rule is not SafetyRuleType.MANUAL_KILL_SWITCH and ev.decision in {SafetyDecision.BLOCK_GLOBAL, SafetyDecision.BLOCK_INSTRUMENT}:
                        self._automatic_lock_count += 1
                else:
                    incidents[existing_index] = replace(incidents[existing_index], updated_at=timestamp, message=ev.message)
            elif existing_index is not None and key not in active_keys and not incidents[existing_index].manual_release_required:
                resolved_incident = replace(incidents[existing_index], updated_at=timestamp, resolved_at=timestamp, status=SafetyIncidentStatus.RESOLVED)
                incidents[existing_index] = resolved_incident
                resolved.append(resolved_incident)
        self._incidents = tuple(incidents[-self._configuration.incident_history_limit:])
        return tuple(opened), tuple(resolved)

    def _resolve_manual(self, scope, instrument, timestamp):
        self._incidents = tuple(
            replace(item, updated_at=timestamp, resolved_at=timestamp, status=SafetyIncidentStatus.RESOLVED)
            if item.rule is SafetyRuleType.MANUAL_KILL_SWITCH and item.scope is scope and item.instrument is instrument and item.status is not SafetyIncidentStatus.RESOLVED
            else item
            for item in self._incidents
        )

    def _apply_decision_state(self, evaluations):
        decision = _overall_decision(evaluations)
        if decision is SafetyDecision.BLOCK_GLOBAL:
            self._status = ProductionSafetyStatus.LOCKED
            self._change = SafetyChange.GLOBAL_LOCKED
            self._last_locked_at = self._last_evaluated_at
        elif decision is SafetyDecision.BLOCK_INSTRUMENT:
            self._status = ProductionSafetyStatus.DEGRADED
            self._change = SafetyChange.INSTRUMENT_LOCKED
            self._last_locked_at = self._last_evaluated_at
        elif decision is SafetyDecision.ALLOW_WITH_WARNING:
            self._status = ProductionSafetyStatus.DEGRADED
            self._change = SafetyChange.BECAME_DEGRADED
        else:
            self._status = ProductionSafetyStatus.MONITORING
            self._change = SafetyChange.UNCHANGED
        self._last_error = None

    def _instrument_snapshot(self, instrument):
        evaluations = tuple(ev for ev in self._evaluations if ev.scope is SafetyScope.INSTRUMENT and ev.instrument is instrument)
        decision = _overall_decision(evaluations)
        latest_md = next((ev.observed_value for ev in evaluations if ev.rule is SafetyRuleType.MARKET_DATA_STALENESS and isinstance(ev.observed_value, (int, float))), None)
        return InstrumentSafetySnapshot(
            instrument=instrument,
            decision=decision,
            locked=decision is SafetyDecision.BLOCK_INSTRUMENT,
            degraded=decision is SafetyDecision.ALLOW_WITH_WARNING,
            market_data_age_seconds=float(latest_md) if latest_md is not None else None,
            evaluations=evaluations,
            open_incidents=tuple(incident for incident in self.open_incidents() if incident.scope is SafetyScope.INSTRUMENT and incident.instrument is instrument),
            last_evaluated_at=self._last_evaluated_at or self._now(),
            last_error=None,
        )

    def _empty_recovery(self, timestamp):
        return RecoveryReadinessSnapshot(timestamp, RecoveryDecision.READY, True, self._configuration.enabled_instruments, (), (), 0, 0, "No recovery blockers.")

    def _store_snapshot(self, *, replace_latest=False):
        snapshot = self.snapshot()
        history = self._snapshot_history[:-1] + (snapshot,) if replace_latest and self._snapshot_history else self._snapshot_history + (snapshot,)
        self._snapshot_history = history[-self._configuration.snapshot_history_limit:]
        self._data = snapshot
        return snapshot

    def _refresh_evaluations_for_manual_command(self, timestamp):
        if self._last_input is None:
            evaluations = self._manual_only_evaluations()
        else:
            evaluations = self._evaluator.evaluate(
                self._last_input,
                self._configuration,
                manual_global_lock=self._manual_global_lock,
                manual_instrument_locks=self._manual_instrument_locks,
            )
        self._update_incidents(evaluations, timestamp)
        self._evaluations = evaluations
        self._last_evaluated_at = timestamp
        self._refresh_recovery(timestamp)
        self._last_snapshot_for_input = None

    def _manual_only_evaluations(self):
        evaluations = []
        if self._manual_global_lock:
            evaluations.append(SafetyRuleEvaluation(SafetyRuleType.MANUAL_KILL_SWITCH, SafetyScope.GLOBAL, None, SafetyRuleResult.FAILED, SafetySeverity.CRITICAL, SafetyDecision.BLOCK_GLOBAL, "Manual global kill switch is active.", "active", "inactive"))
        else:
            evaluations.append(SafetyRuleEvaluation(SafetyRuleType.MANUAL_KILL_SWITCH, SafetyScope.GLOBAL, None, SafetyRuleResult.PASSED, SafetySeverity.INFO, SafetyDecision.ALLOW, "Manual global kill switch is clear.", "inactive", "inactive"))
        for instrument in self._configuration.enabled_instruments:
            if instrument in self._manual_instrument_locks:
                evaluations.append(SafetyRuleEvaluation(SafetyRuleType.MANUAL_KILL_SWITCH, SafetyScope.INSTRUMENT, instrument, SafetyRuleResult.FAILED, SafetySeverity.CRITICAL, SafetyDecision.BLOCK_INSTRUMENT, "Manual instrument kill switch is active.", "active", "inactive"))
            else:
                evaluations.append(SafetyRuleEvaluation(SafetyRuleType.MANUAL_KILL_SWITCH, SafetyScope.INSTRUMENT, instrument, SafetyRuleResult.PASSED, SafetySeverity.INFO, SafetyDecision.ALLOW, "Manual instrument kill switch is clear.", "inactive", "inactive"))
        return tuple(evaluations)

    def _refresh_recovery(self, timestamp):
        active_execution = 0
        active_position = 0
        if self._last_input is not None:
            active_execution = sum(item.coordinator_snapshot.execution_snapshot.open_intent_count for item in self._last_input.lifecycle_integration_snapshot.instruments)
            active_position = sum(1 for item in self._last_input.lifecycle_integration_snapshot.instruments if item.coordinator_snapshot.position_snapshot.has_open_position)
        self._recovery = self._recovery_evaluator.evaluate(
            snapshot=self._data if isinstance(self._data, ProductionSafetyV1Snapshot) else None,
            current_evaluations=self._evaluations,
            open_incidents=self.open_incidents(),
            active_execution_count=active_execution,
            active_position_count=active_position,
            configuration=self._configuration,
            timestamp=timestamp,
        )

    def _publish_snapshot(self, snapshot):
        if snapshot.status is ProductionSafetyStatus.LOCKED:
            self._event_bus.publish(PRODUCTION_SAFETY_V1_LOCKED, snapshot)
        elif snapshot.status is ProductionSafetyStatus.DEGRADED:
            self._event_bus.publish(PRODUCTION_SAFETY_V1_DEGRADED, snapshot)
        self._event_bus.publish(PRODUCTION_SAFETY_V1_UPDATED, snapshot)

    def _now(self):
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value


def _incident_key(item):
    return (item.rule, item.scope, item.instrument)


def _manual_required(ev, configuration):
    if ev.rule is SafetyRuleType.MANUAL_KILL_SWITCH:
        return configuration.require_manual_release_after_kill_switch
    if ev.rule is SafetyRuleType.DAILY_LOSS_LIMIT:
        return configuration.require_manual_release_after_daily_loss
    if ev.rule is SafetyRuleType.ACCOUNT_DRAWDOWN_LIMIT:
        return configuration.require_manual_release_after_drawdown
    return False


def _overall_decision(evaluations):
    decisions = [ev.decision for ev in evaluations]
    if SafetyDecision.BLOCK_GLOBAL in decisions:
        return SafetyDecision.BLOCK_GLOBAL
    if SafetyDecision.BLOCK_INSTRUMENT in decisions:
        return SafetyDecision.BLOCK_INSTRUMENT
    if SafetyDecision.ALLOW_WITH_WARNING in decisions:
        return SafetyDecision.ALLOW_WITH_WARNING
    return SafetyDecision.ALLOW


def _highest_severity(evaluations):
    order = (SafetySeverity.INFO, SafetySeverity.LOW, SafetySeverity.MODERATE, SafetySeverity.HIGH, SafetySeverity.CRITICAL)
    severity = SafetySeverity.INFO
    for ev in evaluations:
        if order.index(ev.severity) > order.index(severity):
            severity = ev.severity
    return severity


def _safe_error(exc):
    return str(exc).replace("token", "[redacted]").replace("credential", "[redacted]")


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")


def _non_empty(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("reason must be non-empty")
