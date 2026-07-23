from engines.ai_reasoning_v2.enums import AIReasoningDirection
from engines.strategy_decision_v2.configuration import StrategyDecisionV2Configuration
from engines.strategy_decision_v2.enums import StrategySetupFamily
from engines.strategy_decision_v2.models import StrategyDecisionV2Input


class StrategySetupSelector:
    def select(
        self,
        inputs: StrategyDecisionV2Input,
        configuration: StrategyDecisionV2Configuration,
    ) -> StrategySetupFamily:
        reasoning = inputs.reasoning
        primary_setup = reasoning.setup_classification.primary_setup.value
        direction = reasoning.direction
        if direction is AIReasoningDirection.CONFLICTED:
            return StrategySetupFamily.NO_SETUP
        if primary_setup in {"reversal_attempt", "bull_trap", "bear_trap", "liquidity_sweep"} and configuration.allow_reversal_watch:
            return StrategySetupFamily.REVERSAL_WATCH
        if primary_setup in {"breakout", "failed_breakout"} and direction in {
            AIReasoningDirection.BULLISH,
            AIReasoningDirection.STRONGLY_BULLISH,
        } and configuration.allow_breakout_retest:
            return StrategySetupFamily.BREAKOUT_RETEST
        if primary_setup in {"breakout", "failed_breakout"} and direction in {
            AIReasoningDirection.BEARISH,
            AIReasoningDirection.STRONGLY_BEARISH,
        } and configuration.allow_breakdown_retest:
            return StrategySetupFamily.BREAKDOWN_RETEST
        if primary_setup == "range_day" and configuration.allow_range_watch:
            if direction in {AIReasoningDirection.BULLISH, AIReasoningDirection.STRONGLY_BULLISH}:
                return StrategySetupFamily.RANGE_BREAKOUT_WATCH
            if direction in {AIReasoningDirection.BEARISH, AIReasoningDirection.STRONGLY_BEARISH}:
                return StrategySetupFamily.RANGE_BREAKDOWN_WATCH
            return StrategySetupFamily.NO_SETUP
        if primary_setup in {"trend_continuation", "pullback_continuation", "trend_day"} and configuration.allow_trend_continuation:
            return StrategySetupFamily.TREND_CONTINUATION
        return StrategySetupFamily.NO_SETUP
