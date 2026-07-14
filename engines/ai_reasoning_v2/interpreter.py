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
from engines.ai_reasoning_v2.models import AIReasoningEvidence, AIReasoningV2Snapshot
from engines.market_context_v2.enums import (
    EvidenceDirection,
    MarketConflictSeverity,
    MarketContextReadiness,
    MarketDirection,
    MarketEvidenceSource,
    TradePosture,
)
from engines.market_context_v2.models import MarketContextV2Snapshot


_DIRECTION_MAP = {
    MarketDirection.STRONGLY_BULLISH: AIReasoningDirection.STRONGLY_BULLISH,
    MarketDirection.BULLISH: AIReasoningDirection.BULLISH,
    MarketDirection.NEUTRAL: AIReasoningDirection.NEUTRAL,
    MarketDirection.BEARISH: AIReasoningDirection.BEARISH,
    MarketDirection.STRONGLY_BEARISH: AIReasoningDirection.STRONGLY_BEARISH,
    MarketDirection.CONFLICTED: AIReasoningDirection.CONFLICTED,
    MarketDirection.INSUFFICIENT_DATA: AIReasoningDirection.INSUFFICIENT_DATA,
}


class AIReasoningV2Interpreter:
    """
    Stateless interpreter for Market Context V2 snapshots.
    """

    def direction(self, context: MarketContextV2Snapshot) -> AIReasoningDirection:
        return _DIRECTION_MAP[context.direction]

    def interpret_evidence(
        self,
        context: MarketContextV2Snapshot,
        configuration: AIReasoningV2Configuration,
    ) -> tuple[AIReasoningEvidence, ...]:
        if not isinstance(configuration, AIReasoningV2Configuration):
            raise TypeError("configuration must be AIReasoningV2Configuration")
        final = _final_evidence_direction(context.direction)
        interpreted = []
        for item in context.evidence:
            role = _role(item.source, item.direction, final)
            impact = _impact(item.direction)
            if role is AIReasoningEvidenceRole.CONFLICT:
                impact = (
                    AIReasoningImpact.CREATES_CONFLICT
                    if item.direction is EvidenceDirection.CONFLICTED
                    else AIReasoningImpact.REDUCES_CONFIDENCE
                )
            explanation = item.reasons[0] if item.reasons else f"{item.source.value} evidence is {item.direction.value}."
            interpreted.append(
                AIReasoningEvidence(
                    source=item.source,
                    role=role,
                    impact=impact,
                    direction=item.direction,
                    strength=item.strength,
                    score=item.score,
                    explanation=explanation,
                )
            )
        return tuple(interpreted)

    def conviction(
        self,
        context: MarketContextV2Snapshot,
        configuration: AIReasoningV2Configuration,
    ) -> AIConviction:
        if context.readiness is MarketContextReadiness.INSUFFICIENT:
            return AIConviction.UNAVAILABLE
        if context.conflict_severity is MarketConflictSeverity.CRITICAL:
            return AIConviction.VERY_LOW
        confidence = context.confidence
        if confidence >= configuration.very_high_confidence:
            conviction = AIConviction.VERY_HIGH
        elif confidence >= configuration.high_confidence:
            conviction = AIConviction.HIGH
        elif confidence >= configuration.moderate_confidence:
            conviction = AIConviction.MODERATE
        elif confidence >= configuration.low_confidence:
            conviction = AIConviction.LOW
        else:
            conviction = AIConviction.VERY_LOW
        if context.conflict_severity is MarketConflictSeverity.HIGH:
            return _cap_conviction(conviction, AIConviction.LOW)
        if context.readiness is MarketContextReadiness.PARTIAL:
            return _cap_conviction(conviction, AIConviction.MODERATE)
        return conviction

    def reasoning_state(
        self,
        context: MarketContextV2Snapshot,
    ) -> AIReasoningState:
        if context.readiness is MarketContextReadiness.INSUFFICIENT:
            return AIReasoningState.INSUFFICIENT_CONTEXT
        if context.direction is MarketDirection.CONFLICTED or context.conflict_severity in {
            MarketConflictSeverity.HIGH,
            MarketConflictSeverity.CRITICAL,
        }:
            return AIReasoningState.CONFLICTED_CONTEXT
        if context.trade_posture is TradePosture.AVOID_NEW_TRADES:
            return AIReasoningState.AVOID_CONTEXT
        if context.trade_posture is TradePosture.WAIT_FOR_CONFIRMATION or context.readiness is MarketContextReadiness.PARTIAL:
            return AIReasoningState.WAITING_CONFIRMATION
        if (
            context.trade_posture
            in {TradePosture.LOOK_FOR_LONGS, TradePosture.LOOK_FOR_SHORTS}
            and context.readiness is MarketContextReadiness.READY
        ):
            return AIReasoningState.ACTIONABLE_CONTEXT
        return AIReasoningState.WAITING_CONFIRMATION

    def caution_severity(self, context: MarketContextV2Snapshot) -> AICautionSeverity:
        if context.conflict_severity is MarketConflictSeverity.CRITICAL:
            return AICautionSeverity.CRITICAL
        if context.conflict_severity is MarketConflictSeverity.HIGH or context.trade_posture is TradePosture.AVOID_NEW_TRADES:
            return AICautionSeverity.HIGH
        if (
            context.readiness is MarketContextReadiness.PARTIAL
            or context.primary_sources_available == 1
            or context.confidence < 0.5
        ):
            return AICautionSeverity.MODERATE
        if context.warnings or context.conflict_severity in {
            MarketConflictSeverity.LOW,
            MarketConflictSeverity.MODERATE,
        }:
            return AICautionSeverity.LOW
        return AICautionSeverity.NONE

    def change_type(
        self,
        context: MarketContextV2Snapshot,
        previous: AIReasoningV2Snapshot | None,
    ) -> AIReasoningChange:
        current = self.direction(context)
        if previous is None:
            return AIReasoningChange.INITIAL
        if current is AIReasoningDirection.INSUFFICIENT_DATA:
            return AIReasoningChange.INSUFFICIENT_DATA
        if previous.direction is AIReasoningDirection.CONFLICTED and current is not AIReasoningDirection.CONFLICTED:
            return AIReasoningChange.CONFLICT_RESOLVED
        if current in {AIReasoningDirection.BULLISH, AIReasoningDirection.STRONGLY_BULLISH} and previous.direction is not current:
            if previous.direction not in {AIReasoningDirection.BULLISH, AIReasoningDirection.STRONGLY_BULLISH}:
                return AIReasoningChange.TURNED_BULLISH
        if current in {AIReasoningDirection.BEARISH, AIReasoningDirection.STRONGLY_BEARISH} and previous.direction is not current:
            if previous.direction not in {AIReasoningDirection.BEARISH, AIReasoningDirection.STRONGLY_BEARISH}:
                return AIReasoningChange.TURNED_BEARISH
        if current is AIReasoningDirection.NEUTRAL and previous.direction is not current:
            return AIReasoningChange.BECAME_NEUTRAL
        if current is AIReasoningDirection.CONFLICTED and previous.direction is not current:
            return AIReasoningChange.BECAME_CONFLICTED
        delta = context.confidence - previous.confidence
        if delta >= 0.10:
            return AIReasoningChange.STRENGTHENED
        if delta <= -0.10:
            return AIReasoningChange.WEAKENED
        return AIReasoningChange.UNCHANGED


def _role(source, direction, final):
    if direction is EvidenceDirection.UNAVAILABLE:
        return AIReasoningEvidenceRole.UNAVAILABLE
    if direction is EvidenceDirection.CONFLICTED:
        return AIReasoningEvidenceRole.CONFLICT
    if final in {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH} and direction not in {
        final,
        EvidenceDirection.NEUTRAL,
    }:
        return AIReasoningEvidenceRole.CONFLICT
    if source in {MarketEvidenceSource.PRICE_ACTION, MarketEvidenceSource.OPTION_CHAIN}:
        return AIReasoningEvidenceRole.PRIMARY
    return AIReasoningEvidenceRole.CONFIRMATION


def _impact(direction):
    return {
        EvidenceDirection.BULLISH: AIReasoningImpact.SUPPORTS_BULLISH,
        EvidenceDirection.BEARISH: AIReasoningImpact.SUPPORTS_BEARISH,
        EvidenceDirection.NEUTRAL: AIReasoningImpact.SUPPORTS_NEUTRAL,
        EvidenceDirection.CONFLICTED: AIReasoningImpact.CREATES_CONFLICT,
        EvidenceDirection.UNAVAILABLE: AIReasoningImpact.NO_IMPACT,
    }[direction]


def _final_evidence_direction(direction):
    if direction in {MarketDirection.BULLISH, MarketDirection.STRONGLY_BULLISH}:
        return EvidenceDirection.BULLISH
    if direction in {MarketDirection.BEARISH, MarketDirection.STRONGLY_BEARISH}:
        return EvidenceDirection.BEARISH
    return EvidenceDirection.NEUTRAL


def _cap_conviction(value, cap):
    order = [
        AIConviction.UNAVAILABLE,
        AIConviction.VERY_LOW,
        AIConviction.LOW,
        AIConviction.MODERATE,
        AIConviction.HIGH,
        AIConviction.VERY_HIGH,
    ]
    return value if order.index(value) <= order.index(cap) else cap
