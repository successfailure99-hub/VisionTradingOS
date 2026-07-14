from engines.market_context_v2.enums import MarketDirection, MarketRegime
from engines.strategy_decision_v2.configuration import StrategyDecisionV2Configuration
from engines.strategy_decision_v2.enums import StrategySetupFamily
from engines.strategy_decision_v2.models import StrategyDecisionV2Input


class StrategySetupSelector:
    def select(
        self,
        inputs: StrategyDecisionV2Input,
        configuration: StrategyDecisionV2Configuration,
    ) -> StrategySetupFamily:
        context = inputs.reasoning.market_context
        if context.direction is MarketDirection.CONFLICTED:
            return StrategySetupFamily.NO_SETUP
        if context.regime is MarketRegime.REVERSAL_RISK and configuration.allow_reversal_watch:
            return StrategySetupFamily.REVERSAL_WATCH
        if context.regime is MarketRegime.BREAKOUT_ATTEMPT and configuration.allow_breakout_retest:
            return StrategySetupFamily.BREAKOUT_RETEST
        if context.regime is MarketRegime.BREAKDOWN_ATTEMPT and configuration.allow_breakdown_retest:
            return StrategySetupFamily.BREAKDOWN_RETEST
        if context.regime is MarketRegime.RANGE_BOUND and configuration.allow_range_watch:
            if context.direction in {MarketDirection.BULLISH, MarketDirection.STRONGLY_BULLISH}:
                return StrategySetupFamily.RANGE_BREAKOUT_WATCH
            if context.direction in {MarketDirection.BEARISH, MarketDirection.STRONGLY_BEARISH}:
                return StrategySetupFamily.RANGE_BREAKDOWN_WATCH
            return StrategySetupFamily.NO_SETUP
        if context.regime is MarketRegime.TRENDING_UP and configuration.allow_trend_continuation:
            return StrategySetupFamily.TREND_CONTINUATION
        if context.regime is MarketRegime.TRENDING_DOWN and configuration.allow_trend_continuation:
            return StrategySetupFamily.TREND_CONTINUATION
        return StrategySetupFamily.NO_SETUP
