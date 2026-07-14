from engines.ai_reasoning_v2.enums import AIReasoningDirection, AIReasoningState
from engines.market_context_v2.enums import MarketConflictSeverity, MarketContextReadiness, MarketDirection, TradePosture
from engines.strategy_decision_v2.configuration import StrategyDecisionV2Configuration
from engines.strategy_decision_v2.enums import StrategySetupStatus
from engines.strategy_decision_v2.models import StrategyDecisionV2Input


class StrategyEligibilityEvaluator:
    def evaluate(
        self,
        inputs: StrategyDecisionV2Input,
        configuration: StrategyDecisionV2Configuration,
    ) -> tuple[bool, StrategySetupStatus, tuple[str, ...]]:
        context = inputs.reasoning.market_context
        reasoning = inputs.reasoning
        if (
            context.readiness is MarketContextReadiness.INSUFFICIENT
            or reasoning.reasoning_state is AIReasoningState.INSUFFICIENT_CONTEXT
            or reasoning.direction is AIReasoningDirection.INSUFFICIENT_DATA
        ):
            return False, StrategySetupStatus.BLOCKED_BY_READINESS, ("Primary evidence is insufficient.",)
        if (
            context.direction is MarketDirection.CONFLICTED
            or reasoning.direction is AIReasoningDirection.CONFLICTED
            or reasoning.reasoning_state is AIReasoningState.CONFLICTED_CONTEXT
            or (
                configuration.block_high_conflict
                and context.conflict_severity in {MarketConflictSeverity.HIGH, MarketConflictSeverity.CRITICAL}
            )
        ):
            return False, StrategySetupStatus.BLOCKED_BY_CONFLICT, ("Primary or high-severity conflict blocks strategy evaluation.",)
        if configuration.require_context_ready and context.readiness is not MarketContextReadiness.READY:
            return False, StrategySetupStatus.BLOCKED_BY_READINESS, ("Market context is not fully ready.",)
        if configuration.require_actionable_reasoning and not reasoning.actionable_context:
            return False, StrategySetupStatus.BLOCKED_BY_CONVICTION, ("AI reasoning is not actionable.",)
        if context.confidence < configuration.minimum_context_confidence:
            return False, StrategySetupStatus.BLOCKED_BY_CONVICTION, ("Market context confidence is below threshold.",)
        if reasoning.confidence < configuration.minimum_reasoning_confidence:
            return False, StrategySetupStatus.BLOCKED_BY_CONVICTION, ("AI reasoning confidence is below threshold.",)
        if context.trade_posture not in {TradePosture.LOOK_FOR_LONGS, TradePosture.LOOK_FOR_SHORTS}:
            return False, StrategySetupStatus.NO_SETUP, ("Trade posture does not permit directional setup evaluation.",)
        return True, StrategySetupStatus.READY_FOR_RISK_REVIEW, ("Strategy context is eligible for setup evaluation.",)
