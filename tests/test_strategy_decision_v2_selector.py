from engines.market_context_v2.enums import MarketRegime
from engines.strategy_decision_v2 import StrategyDecisionV2Configuration, StrategyDecisionV2Input, StrategySetupFamily, StrategySetupSelector
from tests.test_strategy_decision_v2_integration import build_stack, replace_context


def test_selector_maps_regimes_deterministically():
    selector = StrategySetupSelector()
    config = StrategyDecisionV2Configuration()
    assert selector.select(StrategyDecisionV2Input(build_stack("bullish"), 108.0), config) is StrategySetupFamily.TREND_CONTINUATION
    breakout = StrategyDecisionV2Input(replace_context(build_stack("bullish"), regime=MarketRegime.BREAKOUT_ATTEMPT), 108.0)
    assert selector.select(breakout, config) is StrategySetupFamily.BREAKOUT_RETEST
    breakdown = StrategyDecisionV2Input(replace_context(build_stack("bearish"), regime=MarketRegime.BREAKDOWN_ATTEMPT), 93.0)
    assert selector.select(breakdown, config) is StrategySetupFamily.BREAKDOWN_RETEST
    reversal = StrategyDecisionV2Input(replace_context(build_stack("bullish"), regime=MarketRegime.REVERSAL_RISK), 108.0)
    assert selector.select(reversal, config) is StrategySetupFamily.REVERSAL_WATCH
