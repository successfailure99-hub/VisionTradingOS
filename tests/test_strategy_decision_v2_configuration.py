import pytest

from engines.strategy_decision_v2 import StrategyDecisionV2Configuration


def test_defaults_frozen_slotted_and_safe_fields():
    config = StrategyDecisionV2Configuration()
    assert config.minimum_context_confidence == 0.50
    assert config.high_quality_confidence == 0.75
    assert hasattr(StrategyDecisionV2Configuration, "__slots__")
    with pytest.raises(Exception):
        config.history_limit = 1
    fields = set(StrategyDecisionV2Configuration.__dataclass_fields__)
    assert not any(word in name for name in fields for word in ("credential", "order", "quantity", "margin"))


def test_validation():
    with pytest.raises(ValueError):
        StrategyDecisionV2Configuration(minimum_context_confidence=-0.1)
    with pytest.raises(ValueError):
        StrategyDecisionV2Configuration(high_quality_confidence=0.4)
    with pytest.raises(TypeError):
        StrategyDecisionV2Configuration(require_context_ready=1)
    with pytest.raises(TypeError):
        StrategyDecisionV2Configuration(maximum_objectives=True)
    with pytest.raises(ValueError):
        StrategyDecisionV2Configuration(maximum_conditions=0)
    with pytest.raises(ValueError):
        StrategyDecisionV2Configuration(allow_trend_continuation=False, allow_breakout_retest=False, allow_breakdown_retest=False, allow_range_watch=False, allow_reversal_watch=False)
