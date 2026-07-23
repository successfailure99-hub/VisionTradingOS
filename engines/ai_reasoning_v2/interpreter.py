"""
Pure interpretation helpers for AI Reasoning Engine V2.
"""

from engines.ai_reasoning_v2.configuration import AIReasoningV2Configuration
from engines.ai_reasoning_v2.enums import (
    AICautionSeverity,
    AIConviction,
    AIReasoningChange,
    AIReasoningDirection,
    AIReasoningEvidenceRole,
    AIReasoningImpact,
    AIReasoningState,
)
from engines.ai_reasoning_v2.models import AIReasoningEvidence, AIReasoningV2Input, AIReasoningV2Snapshot


_DIRECTION_MAP = {
    "bullish": AIReasoningDirection.BULLISH,
    "bearish": AIReasoningDirection.BEARISH,
    "neutral": AIReasoningDirection.NEUTRAL,
    "mixed": AIReasoningDirection.CONFLICTED,
    "unknown": AIReasoningDirection.INSUFFICIENT_DATA,
}


class AIReasoningV2Interpreter:
    """
    Stateless interpreter for deterministic intelligence snapshots.
    """

    def direction(self, inputs: AIReasoningV2Input) -> AIReasoningDirection:
        fusion = inputs.multi_timeframe_evidence
        if fusion.evidence_completeness.value == "insufficient":
            return AIReasoningDirection.INSUFFICIENT_DATA
        if fusion.evidence_conflict.value == "major":
            return AIReasoningDirection.CONFLICTED
        return _DIRECTION_MAP[_dominant_direction(inputs).value]

    def interpret_evidence(
        self,
        inputs: AIReasoningV2Input,
        configuration: AIReasoningV2Configuration,
    ) -> tuple[AIReasoningEvidence, ...]:
        if not isinstance(configuration, AIReasoningV2Configuration):
            raise TypeError("configuration must be AIReasoningV2Configuration")
        fusion = inputs.multi_timeframe_evidence
        market_state = inputs.market_state
        setup = inputs.setup_classification
        explanation = inputs.chart_explanation
        direction = self.direction(inputs).value
        evidence = [
            AIReasoningEvidence(
                source="multi_timeframe_evidence",
                role=AIReasoningEvidenceRole.PRIMARY,
                impact=_impact_from_direction(self.direction(inputs)),
                direction=direction,
                strength=fusion.evidence_agreement.value,
                score=round(fusion.alignment_score - fusion.conflict_score),
                explanation=(
                    f"Fusion reports {fusion.evidence_agreement.value} with "
                    f"{fusion.evidence_conflict.value} conflict."
                ),
            ),
            AIReasoningEvidence(
                source="market_state",
                role=AIReasoningEvidenceRole.PRIMARY,
                impact=AIReasoningImpact.SUPPORTS_NEUTRAL,
                direction=market_state.market_state.value,
                strength=market_state.confidence_level.value,
                score=_market_state_score(market_state),
                explanation=(
                    f"Market state is {market_state.market_state.value} with "
                    f"{market_state.evidence_quality.value} evidence quality."
                ),
            ),
            AIReasoningEvidence(
                source="expert_setup_classification",
                role=AIReasoningEvidenceRole.CONFIRMATION,
                impact=_setup_impact(setup),
                direction=setup.primary_setup.value,
                strength=setup.setup_strength.value,
                score=_setup_score(setup),
                explanation=(
                    f"Expert setup is {setup.primary_setup.value} with "
                    f"{setup.setup_quality.value} quality."
                ),
            ),
            AIReasoningEvidence(
                source="chart_explanation",
                role=AIReasoningEvidenceRole.CONFIRMATION,
                impact=AIReasoningImpact.SUPPORTS_NEUTRAL,
                direction=explanation.headline,
                strength=explanation.explanation_quality.value,
                score=_explanation_score(explanation),
                explanation=explanation.market_summary,
            ),
        ]
        for item in explanation.conflicting_evidence[: configuration.maximum_conflicting_points]:
            evidence.append(
                AIReasoningEvidence(
                    source="chart_explanation_conflict",
                    role=AIReasoningEvidenceRole.CONFLICT,
                    impact=AIReasoningImpact.REDUCES_CONFIDENCE,
                    direction="conflict",
                    strength="reported",
                    score=-1,
                    explanation=item,
                )
            )
        return tuple(evidence)

    def conviction(
        self,
        inputs: AIReasoningV2Input,
        configuration: AIReasoningV2Configuration,
    ) -> AIConviction:
        score = _structural_score(inputs)
        if inputs.multi_timeframe_evidence.evidence_completeness.value == "insufficient":
            return AIConviction.UNAVAILABLE
        if score >= configuration.very_high_confidence:
            return AIConviction.VERY_HIGH
        if score >= configuration.high_confidence:
            return AIConviction.HIGH
        if score >= configuration.moderate_confidence:
            return AIConviction.MODERATE
        if score >= configuration.low_confidence:
            return AIConviction.LOW
        return AIConviction.VERY_LOW

    def reasoning_state(
        self,
        inputs: AIReasoningV2Input,
    ) -> AIReasoningState:
        fusion = inputs.multi_timeframe_evidence
        market_state = inputs.market_state
        setup = inputs.setup_classification
        if (
            fusion.evidence_completeness.value == "insufficient"
            or market_state.evidence_quality.value == "insufficient"
        ):
            return AIReasoningState.INSUFFICIENT_CONTEXT
        if fusion.evidence_conflict.value == "major" or fusion.evidence_agreement.value == "conflict":
            return AIReasoningState.CONFLICTED_CONTEXT
        if setup.primary_setup.value == "no_quality_setup" or setup.setup_quality.value == "low":
            return AIReasoningState.AVOID_CONTEXT
        if (
            fusion.evidence_completeness.value == "partial"
            or market_state.market_state.value == "transition"
            or market_state.market_stability.value == "changing"
            or setup.setup_stability.value == "changing"
        ):
            return AIReasoningState.WAITING_CONFIRMATION
        return AIReasoningState.ACTIONABLE_CONTEXT

    def caution_severity(self, inputs: AIReasoningV2Input) -> AICautionSeverity:
        fusion = inputs.multi_timeframe_evidence
        market_state = inputs.market_state
        setup = inputs.setup_classification
        explanation = inputs.chart_explanation
        if fusion.evidence_conflict.value == "major" or market_state.volatility_state.value == "volatile":
            return AICautionSeverity.HIGH
        if (
            fusion.evidence_completeness.value == "partial"
            or market_state.evidence_quality.value == "low"
            or setup.setup_stability.value == "unstable"
            or explanation.explanation_quality.value == "low"
        ):
            return AICautionSeverity.MODERATE
        if fusion.evidence_conflict.value == "minor" or explanation.risk_notes:
            return AICautionSeverity.LOW
        return AICautionSeverity.NONE

    def change_type(
        self,
        inputs: AIReasoningV2Input,
        previous: AIReasoningV2Snapshot | None,
        configuration: AIReasoningV2Configuration,
    ) -> AIReasoningChange:
        current = self.direction(inputs)
        if previous is None:
            return AIReasoningChange.INITIAL
        if current is AIReasoningDirection.INSUFFICIENT_DATA:
            return AIReasoningChange.INSUFFICIENT_DATA
        if previous.direction is AIReasoningDirection.CONFLICTED and current is not AIReasoningDirection.CONFLICTED:
            return AIReasoningChange.CONFLICT_RESOLVED
        if current in {AIReasoningDirection.BULLISH, AIReasoningDirection.STRONGLY_BULLISH} and previous.direction not in {
            AIReasoningDirection.BULLISH,
            AIReasoningDirection.STRONGLY_BULLISH,
        }:
            return AIReasoningChange.TURNED_BULLISH
        if current in {AIReasoningDirection.BEARISH, AIReasoningDirection.STRONGLY_BEARISH} and previous.direction not in {
            AIReasoningDirection.BEARISH,
            AIReasoningDirection.STRONGLY_BEARISH,
        }:
            return AIReasoningChange.TURNED_BEARISH
        if current is AIReasoningDirection.NEUTRAL and previous.direction is not current:
            return AIReasoningChange.BECAME_NEUTRAL
        if current is AIReasoningDirection.CONFLICTED and previous.direction is not current:
            return AIReasoningChange.BECAME_CONFLICTED
        score = _structural_score(inputs)
        delta = score - previous.confidence
        if delta >= 0.10:
            return AIReasoningChange.STRENGTHENED
        if delta <= -0.10:
            return AIReasoningChange.WEAKENED
        return AIReasoningChange.UNCHANGED


def _dominant_direction(inputs: AIReasoningV2Input):
    fusion = inputs.multi_timeframe_evidence
    directions = {summary.timeframe: summary.direction for summary in fusion.summaries}
    return directions.get(fusion.dominant_timeframe, _UnknownDirection())


class _UnknownDirection:
    value = "unknown"


def _impact_from_direction(direction: AIReasoningDirection) -> AIReasoningImpact:
    if direction in {AIReasoningDirection.BULLISH, AIReasoningDirection.STRONGLY_BULLISH}:
        return AIReasoningImpact.SUPPORTS_BULLISH
    if direction in {AIReasoningDirection.BEARISH, AIReasoningDirection.STRONGLY_BEARISH}:
        return AIReasoningImpact.SUPPORTS_BEARISH
    if direction is AIReasoningDirection.CONFLICTED:
        return AIReasoningImpact.CREATES_CONFLICT
    return AIReasoningImpact.SUPPORTS_NEUTRAL


def _setup_impact(setup) -> AIReasoningImpact:
    if setup.primary_setup.value in {"bull_trap", "bear_trap", "failed_breakout"}:
        return AIReasoningImpact.REDUCES_CONFIDENCE
    if setup.primary_setup.value == "no_quality_setup":
        return AIReasoningImpact.NO_IMPACT
    return AIReasoningImpact.SUPPORTS_NEUTRAL


def _structural_score(inputs: AIReasoningV2Input) -> float:
    fusion = inputs.multi_timeframe_evidence
    market_state = inputs.market_state
    setup = inputs.setup_classification
    explanation = inputs.chart_explanation
    score = 0.0
    score += max(0.0, min(1.0, fusion.alignment_score / 100.0)) * 0.525
    score -= max(0.0, min(1.0, fusion.conflict_score / 100.0)) * 0.30
    score += {
        "high_structure": 0.13,
        "medium_structure": 0.08,
        "low_structure": 0.04,
    }[market_state.confidence_level.value]
    score += {
        "high": 0.13,
        "medium": 0.08,
        "low": 0.00,
    }[setup.setup_quality.value]
    score += {
        "high": 0.13,
        "medium": 0.05,
        "low": 0.00,
    }[explanation.explanation_quality.value]
    if fusion.evidence_completeness.value != "complete":
        score -= 0.20
    return max(0.0, min(1.0, round(score, 4)))


def _market_state_score(market_state) -> int:
    return {
        "high": 3,
        "medium": 2,
        "low": 0,
        "insufficient": -2,
    }[market_state.evidence_quality.value]


def _setup_score(setup) -> int:
    return {
        "high": 3,
        "medium": 1,
        "low": -2,
    }[setup.setup_quality.value]


def _explanation_score(explanation) -> int:
    return {
        "high": 2,
        "medium": 1,
        "low": -1,
    }[explanation.explanation_quality.value]
