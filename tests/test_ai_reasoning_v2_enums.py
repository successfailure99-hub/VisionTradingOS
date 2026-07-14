from engines.ai_reasoning_v2 import (
    AICautionSeverity,
    AIConviction,
    AIReasoningChange,
    AIReasoningDirection,
    AIReasoningEvidenceRole,
    AIReasoningImpact,
    AIReasoningState,
)


def test_exact_enum_values_and_no_duplicates():
    assert AIReasoningDirection.STRONGLY_BULLISH.value == "strongly_bullish"
    assert AIReasoningDirection.BULLISH.value == "bullish"
    assert AIReasoningDirection.NEUTRAL.value == "neutral"
    assert AIReasoningDirection.BEARISH.value == "bearish"
    assert AIReasoningDirection.STRONGLY_BEARISH.value == "strongly_bearish"
    assert AIReasoningDirection.CONFLICTED.value == "conflicted"
    assert AIReasoningDirection.INSUFFICIENT_DATA.value == "insufficient_data"
    assert AIConviction.VERY_HIGH.value == "very_high"
    assert AIConviction.HIGH.value == "high"
    assert AIConviction.MODERATE.value == "moderate"
    assert AIConviction.LOW.value == "low"
    assert AIConviction.VERY_LOW.value == "very_low"
    assert AIConviction.UNAVAILABLE.value == "unavailable"
    assert AIReasoningState.ACTIONABLE_CONTEXT.value == "actionable_context"
    assert AIReasoningState.WAITING_CONFIRMATION.value == "waiting_confirmation"
    assert AIReasoningState.CONFLICTED_CONTEXT.value == "conflicted_context"
    assert AIReasoningState.AVOID_CONTEXT.value == "avoid_context"
    assert AIReasoningState.INSUFFICIENT_CONTEXT.value == "insufficient_context"
    assert AIReasoningEvidenceRole.PRIMARY.value == "primary"
    assert AIReasoningEvidenceRole.CONFIRMATION.value == "confirmation"
    assert AIReasoningEvidenceRole.CONFLICT.value == "conflict"
    assert AIReasoningEvidenceRole.WARNING.value == "warning"
    assert AIReasoningEvidenceRole.UNAVAILABLE.value == "unavailable"
    assert AIReasoningImpact.SUPPORTS_BULLISH.value == "supports_bullish"
    assert AIReasoningImpact.SUPPORTS_BEARISH.value == "supports_bearish"
    assert AIReasoningImpact.SUPPORTS_NEUTRAL.value == "supports_neutral"
    assert AIReasoningImpact.CREATES_CONFLICT.value == "creates_conflict"
    assert AIReasoningImpact.REDUCES_CONFIDENCE.value == "reduces_confidence"
    assert AIReasoningImpact.NO_IMPACT.value == "no_impact"
    assert AIReasoningChange.INITIAL.value == "initial"
    assert AIReasoningChange.STRENGTHENED.value == "strengthened"
    assert AIReasoningChange.WEAKENED.value == "weakened"
    assert AIReasoningChange.TURNED_BULLISH.value == "turned_bullish"
    assert AIReasoningChange.TURNED_BEARISH.value == "turned_bearish"
    assert AIReasoningChange.BECAME_NEUTRAL.value == "became_neutral"
    assert AIReasoningChange.BECAME_CONFLICTED.value == "became_conflicted"
    assert AIReasoningChange.CONFLICT_RESOLVED.value == "conflict_resolved"
    assert AIReasoningChange.UNCHANGED.value == "unchanged"
    assert AIReasoningChange.INSUFFICIENT_DATA.value == "insufficient_data"
    assert AICautionSeverity.NONE.value == "none"
    assert AICautionSeverity.LOW.value == "low"
    assert AICautionSeverity.MODERATE.value == "moderate"
    assert AICautionSeverity.HIGH.value == "high"
    assert AICautionSeverity.CRITICAL.value == "critical"
    for enum_type in (
        AIReasoningDirection,
        AIConviction,
        AIReasoningState,
        AIReasoningEvidenceRole,
        AIReasoningImpact,
        AIReasoningChange,
        AICautionSeverity,
    ):
        values = [item.value for item in enum_type]
        assert len(values) == len(set(values))
