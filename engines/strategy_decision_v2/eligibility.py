from engines.ai_reasoning_v2.enums import AIReasoningDirection, AIReasoningState
from engines.strategy_decision_v2.configuration import StrategyDecisionV2Configuration
from engines.strategy_decision_v2.enums import StrategyDirection
from engines.strategy_decision_v2.enums import StrategySetupStatus
from engines.strategy_decision_v2.models import StrategyDecisionV2Input


class StrategyEligibilityEvaluator:
    def evaluate(
        self,
        inputs: StrategyDecisionV2Input,
        configuration: StrategyDecisionV2Configuration,
    ) -> tuple[bool, StrategySetupStatus, tuple[str, ...]]:
        reasoning = inputs.reasoning
        fusion = reasoning.multi_timeframe_evidence
        market_state = reasoning.market_state
        setup = reasoning.setup_classification
        if (
            reasoning.reasoning_state is AIReasoningState.INSUFFICIENT_CONTEXT
            or reasoning.direction is AIReasoningDirection.INSUFFICIENT_DATA
            or fusion.evidence_completeness.value in {"insufficient", "partial"}
            or market_state.evidence_quality.value in {"low", "insufficient"}
            or setup.setup_quality.value == "low"
        ):
            return False, StrategySetupStatus.BLOCKED_BY_READINESS, ("Primary evidence is insufficient.",)
        if (
            reasoning.direction is AIReasoningDirection.CONFLICTED
            or reasoning.reasoning_state is AIReasoningState.CONFLICTED_CONTEXT
            or (
                configuration.block_high_conflict
                and fusion.evidence_conflict.value in {"major", "insufficient"}
            )
        ):
            return False, StrategySetupStatus.BLOCKED_BY_CONFLICT, ("Primary or high-severity conflict blocks strategy evaluation.",)
        if configuration.require_context_ready and market_state.evidence_quality.value not in {"high", "medium"}:
            return False, StrategySetupStatus.BLOCKED_BY_READINESS, ("Market context is not fully ready.",)
        if configuration.require_actionable_reasoning and not reasoning.actionable_context:
            return False, StrategySetupStatus.BLOCKED_BY_CONVICTION, ("AI reasoning is not actionable.",)
        if _structural_confidence(reasoning) < configuration.minimum_context_confidence:
            return False, StrategySetupStatus.BLOCKED_BY_CONVICTION, ("Market context confidence is below threshold.",)
        if reasoning.confidence < configuration.minimum_reasoning_confidence:
            return False, StrategySetupStatus.BLOCKED_BY_CONVICTION, ("AI reasoning confidence is below threshold.",)
        if _direction(reasoning.direction) not in {StrategyDirection.LONG, StrategyDirection.SHORT}:
            return False, StrategySetupStatus.NO_SETUP, ("Trade posture does not permit directional setup evaluation.",)
        return True, StrategySetupStatus.READY_FOR_RISK_REVIEW, ("Strategy context is eligible for setup evaluation.",)


def _direction(ai_direction) -> StrategyDirection:
    if ai_direction in {AIReasoningDirection.BULLISH, AIReasoningDirection.STRONGLY_BULLISH}:
        return StrategyDirection.LONG
    if ai_direction in {AIReasoningDirection.BEARISH, AIReasoningDirection.STRONGLY_BEARISH}:
        return StrategyDirection.SHORT
    if ai_direction is AIReasoningDirection.NEUTRAL:
        return StrategyDirection.NEUTRAL
    return StrategyDirection.NONE


def _structural_confidence(reasoning) -> float:
    return {
        "high_structure": 0.85,
        "medium_structure": 0.65,
        "low_structure": 0.35,
    }.get(reasoning.market_state.confidence_level.value, 0.0)
