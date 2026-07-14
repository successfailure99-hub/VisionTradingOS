import pytest

from engines.strategy_decision_v2 import (
    StrategyDirection,
    StrategyEntryCondition,
    StrategyInvalidationRule,
    StrategyInvalidationType,
    StrategyObjective,
    StrategyReferenceType,
    StrategyRiskHandoff,
    StrategySetupStatus,
    StrategyStructuralReference,
    StrategyTriggerType,
)


def ref():
    return StrategyStructuralReference(StrategyReferenceType.CAMARILLA_H4, 100.0, "H4", "camarilla")


def test_structural_condition_invalidation_objective_and_risk_models():
    reference = ref()
    assert reference.price == 100.0
    condition = StrategyEntryCondition(1, StrategyTriggerType.STRUCTURE_CONTINUATION, "Wait for continuation.", reference, True)
    invalidation = StrategyInvalidationRule(1, StrategyInvalidationType.PRIMARY_BIAS_REVERSAL, "Invalidate on reversal.", None)
    objective = StrategyObjective(1, reference, "Structural objective.")
    risk = StrategyRiskHandoff(True, StrategyDirection.LONG, StrategySetupStatus.READY_FOR_RISK_REVIEW, reference, 1, 0.7, 0.7, ("review",))
    assert condition.mandatory is True
    assert invalidation.priority == 1
    assert objective.reference is reference
    assert risk.requires_risk_review is True
    with pytest.raises(Exception):
        reference.price = 1


def test_invalid_model_values():
    with pytest.raises(ValueError):
        StrategyStructuralReference(StrategyReferenceType.CURRENT_PRICE, 0.0, "bad", "source")
    with pytest.raises(ValueError):
        StrategyEntryCondition(1, StrategyTriggerType.NONE, "bad", None, True)
    with pytest.raises(ValueError):
        StrategyRiskHandoff(True, StrategyDirection.LONG, StrategySetupStatus.WAITING_FOR_TRIGGER, None, 0, 0.5, 0.5, ("bad",))
