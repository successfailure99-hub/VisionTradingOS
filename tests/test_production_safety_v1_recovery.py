from engines.production_safety_v1 import (
    ProductionRecoveryEvaluator,
    ProductionSafetyV1Configuration,
    RecoveryDecision,
    SafetyDecision,
    SafetyIncident,
    SafetyIncidentStatus,
    SafetyRuleEvaluation,
    SafetyRuleResult,
    SafetyRuleType,
    SafetyScope,
    SafetySeverity,
)
from tests.test_market_context_v2_integration import NOW


def test_recovery_ready_manual_and_active_state_blocks():
    evaluator = ProductionRecoveryEvaluator()
    config = ProductionSafetyV1Configuration()

    ready = evaluator.evaluate(snapshot=None, current_evaluations=(), open_incidents=(), active_execution_count=0, active_position_count=0, configuration=config, timestamp=NOW)
    assert ready.decision is RecoveryDecision.READY

    incident = SafetyIncident("id", NOW, NOW, None, SafetyRuleType.MANUAL_KILL_SWITCH, SafetyScope.GLOBAL, None, SafetySeverity.CRITICAL, SafetyIncidentStatus.OPEN, "Manual", True)
    manual = evaluator.evaluate(snapshot=None, current_evaluations=(), open_incidents=(incident,), active_execution_count=0, active_position_count=0, configuration=config, timestamp=NOW)
    assert manual.decision is RecoveryDecision.MANUAL_RELEASE_REQUIRED

    active = evaluator.evaluate(snapshot=None, current_evaluations=(), open_incidents=(), active_execution_count=1, active_position_count=0, configuration=config, timestamp=NOW)
    assert active.decision is RecoveryDecision.BLOCKED_BY_ACTIVE_STATE

    ev = SafetyRuleEvaluation(SafetyRuleType.APPLICATION_RUNTIME_HEALTH, SafetyScope.GLOBAL, None, SafetyRuleResult.FAILED, SafetySeverity.CRITICAL, SafetyDecision.BLOCK_GLOBAL, "bad", None, None)
    dependency = evaluator.evaluate(snapshot=None, current_evaluations=(ev,), open_incidents=(), active_execution_count=0, active_position_count=0, configuration=config, timestamp=NOW)
    assert dependency.decision is RecoveryDecision.BLOCKED_BY_UNHEALTHY_DEPENDENCY
