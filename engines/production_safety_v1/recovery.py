"""
Stateless Production Safety V1 recovery evaluator.
"""

from engines.production_safety_v1.configuration import ProductionSafetyV1Configuration
from engines.production_safety_v1.enums import (
    RecoveryDecision,
    SafetyDecision,
    SafetyIncidentStatus,
    SafetyRuleResult,
    SafetyRuleType,
)
from engines.production_safety_v1.models import ProductionSafetyV1Snapshot, RecoveryReadinessSnapshot, SafetyIncident, SafetyRuleEvaluation


class ProductionRecoveryEvaluator:
    def evaluate(
        self,
        *,
        snapshot: ProductionSafetyV1Snapshot | None,
        current_evaluations: tuple[SafetyRuleEvaluation, ...],
        open_incidents: tuple[SafetyIncident, ...],
        active_execution_count: int,
        active_position_count: int,
        configuration: ProductionSafetyV1Configuration,
        timestamp,
    ) -> RecoveryReadinessSnapshot:
        if snapshot is not None and not isinstance(snapshot, ProductionSafetyV1Snapshot):
            raise TypeError("snapshot must be ProductionSafetyV1Snapshot or None")
        evaluations = tuple(current_evaluations)
        incidents = tuple(open_incidents)
        blocking = tuple(ev.rule for ev in evaluations if ev.result is SafetyRuleResult.FAILED and ev.decision in {SafetyDecision.BLOCK_GLOBAL, SafetyDecision.BLOCK_INSTRUMENT})
        manual = tuple(incident.incident_id for incident in incidents if incident.manual_release_required and incident.status is not SafetyIncidentStatus.RESOLVED)
        dependency_rules = {SafetyRuleType.APPLICATION_RUNTIME_HEALTH, SafetyRuleType.TRADE_LIFECYCLE_HEALTH, SafetyRuleType.JOURNAL_RUNTIME_HEALTH, SafetyRuleType.DEPENDENCY_ERROR}
        if manual:
            decision = RecoveryDecision.MANUAL_RELEASE_REQUIRED
            message = "Manual release is required before recovery."
        elif active_execution_count or active_position_count:
            decision = RecoveryDecision.BLOCKED_BY_ACTIVE_STATE
            message = "Active execution or position blocks recovery."
        elif any(rule in dependency_rules for rule in blocking):
            decision = RecoveryDecision.BLOCKED_BY_UNHEALTHY_DEPENDENCY
            message = "Unhealthy dependency blocks recovery."
        elif blocking:
            decision = RecoveryDecision.NOT_READY
            message = "Blocking safety rules remain active."
        else:
            decision = RecoveryDecision.READY
            message = "Recovery is ready."
        return RecoveryReadinessSnapshot(
            timestamp=timestamp,
            decision=decision,
            global_recovery_ready=decision is RecoveryDecision.READY,
            instruments_ready=configuration.enabled_instruments if decision is RecoveryDecision.READY else (),
            blocking_rules=blocking,
            blocking_incident_ids=tuple(incident.incident_id for incident in incidents if incident.status is not SafetyIncidentStatus.RESOLVED),
            active_execution_count=active_execution_count,
            active_position_count=active_position_count,
            message=message,
        )
