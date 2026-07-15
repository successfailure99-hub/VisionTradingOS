from engines.production_safety_v1 import (
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


def test_production_safety_enum_values_are_stable():
    assert ProductionSafetyStatus.MONITORING.value == "monitoring"
    assert ProductionSafetyStatus.RECOVERY_PENDING.value == "recovery_pending"
    assert SafetyScope.GLOBAL.value == "global"
    assert SafetySeverity.CRITICAL.value == "critical"
    assert SafetyDecision.BLOCK_GLOBAL.value == "block_global"
    assert SafetyRuleType.DAILY_LOSS_LIMIT.value == "daily_loss_limit"
    assert SafetyRuleResult.FAILED.value == "failed"
    assert SafetyIncidentStatus.RESOLVED.value == "resolved"
    assert RecoveryDecision.MANUAL_RELEASE_REQUIRED.value == "manual_release_required"
    assert SafetyChange.GLOBAL_LOCKED.value == "global_locked"
