from engines.risk_management_v2 import (
    PositionSizingMode,
    RiskDecision,
    RiskDecisionChange,
    RiskRuleResult,
    RiskRuleType,
    RiskSeverity,
    RiskStatus,
)


def test_exact_enum_values_and_public_exports():
    assert RiskDecision.APPROVED.value == "approved"
    assert RiskDecision.APPROVED_REDUCED.value == "approved_reduced"
    assert RiskDecision.REJECTED.value == "rejected"
    assert RiskDecision.WAIT.value == "wait"
    assert RiskDecision.INSUFFICIENT_DATA.value == "insufficient_data"
    assert RiskStatus.BLOCKED_BY_DAILY_LOSS.value == "blocked_by_daily_loss"
    assert RiskSeverity.CRITICAL.value == "critical"
    assert RiskRuleType.MINIMUM_REWARD_RISK.value == "minimum_reward_risk"
    assert RiskRuleResult.REDUCED.value == "reduced"
    assert PositionSizingMode.MINIMUM_OF_LIMITS.value == "minimum_of_limits"
    assert RiskDecisionChange.RISK_DECREASED.value == "risk_decreased"
