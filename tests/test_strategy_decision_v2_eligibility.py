from engines.strategy_decision_v2 import StrategyDecisionV2Configuration, StrategyDecisionV2Input, StrategyEligibilityEvaluator, StrategySetupStatus
from tests.test_strategy_decision_v2_integration import build_stack


def test_actionable_context_is_eligible_and_conflict_or_low_confidence_blocks():
    evaluator = StrategyEligibilityEvaluator()
    config = StrategyDecisionV2Configuration()
    bullish = StrategyDecisionV2Input(build_stack("bullish"), 108.0)
    assert evaluator.evaluate(bullish, config)[0] is True
    conflict = StrategyDecisionV2Input(build_stack("conflict"), 108.0)
    assert evaluator.evaluate(conflict, config)[1] is StrategySetupStatus.BLOCKED_BY_CONFLICT
    low = StrategyDecisionV2Input(build_stack("low_confidence"), 108.0)
    assert evaluator.evaluate(low, config)[1] is StrategySetupStatus.BLOCKED_BY_CONVICTION
    insufficient = StrategyDecisionV2Input(build_stack("insufficient"), 108.0)
    assert evaluator.evaluate(insufficient, config)[1] is StrategySetupStatus.BLOCKED_BY_READINESS
