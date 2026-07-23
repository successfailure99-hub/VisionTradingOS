from engines.expert_setup_classification.enums import ExpertSetup
from engines.multi_timeframe_evidence_fusion.enums import FusionDirection
from engines.strategy_decision_v2 import StrategyDecisionV2Configuration, StrategyDecisionV2Input, StrategySetupFamily, StrategySetupSelector
from tests.test_strategy_decision_v2_integration import build_stack, replace_context


def test_selector_maps_regimes_deterministically():
    selector = StrategySetupSelector()
    config = StrategyDecisionV2Configuration()
    assert selector.select(StrategyDecisionV2Input(build_stack("bullish")), config) is StrategySetupFamily.TREND_CONTINUATION
    breakout = StrategyDecisionV2Input(replace_context(build_stack("bullish"), primary_setup=ExpertSetup.BREAKOUT))
    assert selector.select(breakout, config) is StrategySetupFamily.BREAKOUT_RETEST
    breakdown = StrategyDecisionV2Input(
        replace_context(build_stack("bearish"), primary_setup=ExpertSetup.BREAKOUT, direction=FusionDirection.BEARISH)
    )
    assert selector.select(breakdown, config) is StrategySetupFamily.BREAKDOWN_RETEST
    reversal = StrategyDecisionV2Input(replace_context(build_stack("bullish"), primary_setup=ExpertSetup.REVERSAL_ATTEMPT))
    assert selector.select(reversal, config) is StrategySetupFamily.REVERSAL_WATCH
