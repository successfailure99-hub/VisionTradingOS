"""
Deterministic AI Reasoning Engine V2 composer.
"""

from engines.ai_reasoning_v2.configuration import AIReasoningV2Configuration
from engines.ai_reasoning_v2.enums import (
    AICautionSeverity,
    AIReasoningEvidenceRole,
    AIReasoningState,
)
from engines.ai_reasoning_v2.interpreter import AIReasoningV2Interpreter
from engines.ai_reasoning_v2.models import (
    AIReasoningCaution,
    AIReasoningV2Input,
    AIReasoningV2Snapshot,
    AIWatchCondition,
)
from engines.market_context_v2.enums import (
    EvidenceDirection,
    MarketConflictSeverity,
    MarketContextReadiness,
    MarketDirection,
    MarketEvidenceSource,
    MarketRegime,
    TradePosture,
)


class AIReasoningV2Composer:
    """
    Pure deterministic reasoning snapshot composer.
    """

    def compose(
        self,
        *,
        inputs: AIReasoningV2Input,
        configuration: AIReasoningV2Configuration,
        interpreter: AIReasoningV2Interpreter,
    ) -> AIReasoningV2Snapshot:
        context = inputs.context
        direction = interpreter.direction(context)
        conviction = interpreter.conviction(context, configuration)
        state = interpreter.reasoning_state(context)
        change = interpreter.change_type(context, inputs.previous_reasoning)
        caution_severity = interpreter.caution_severity(context)
        evidence = interpreter.interpret_evidence(context, configuration)
        thesis = _primary_thesis(context)
        supporting = _supporting_points(evidence, configuration.maximum_supporting_points)
        conflicting = _conflicting_points(context, evidence, configuration.maximum_conflicting_points)
        cautions = _cautions(context, caution_severity, configuration.maximum_cautions)
        watch = _watch_conditions(context, configuration.maximum_watch_conditions)
        headline = f"{context.instrument.value} market context is {direction.value.replace('_', ' ')}."
        summary = _summary(context, conviction)
        actionable = (
            state is AIReasoningState.ACTIONABLE_CONTEXT
            and context.trade_posture
            in {TradePosture.LOOK_FOR_LONGS, TradePosture.LOOK_FOR_SHORTS}
            and context.readiness is MarketContextReadiness.READY
            and context.conflict_severity
            not in {MarketConflictSeverity.HIGH, MarketConflictSeverity.CRITICAL}
        )
        rationale = (
            thesis,
            evidence[0].explanation,
            evidence[1].explanation,
            "Structural confirmation is interpreted from Camarilla, CPR and VWAP evidence.",
            "Conflict interpretation is based only on Market Context V2 conflicts.",
            f"Confidence interpretation is {conviction.value}.",
            f"Posture interpretation is {context.trade_posture.value}.",
            watch[0].condition if watch else "No additional watch condition is required.",
        )
        previous = inputs.previous_reasoning
        return AIReasoningV2Snapshot(
            instrument=context.instrument,
            timestamp=context.timestamp,
            direction=direction,
            conviction=conviction,
            reasoning_state=state,
            change=change,
            caution_severity=caution_severity,
            market_context=context,
            headline=headline,
            summary=summary,
            primary_thesis=thesis,
            evidence=evidence,
            supporting_points=supporting,
            conflicting_points=conflicting,
            cautions=cautions,
            watch_conditions=watch,
            confidence=context.confidence,
            actionable_context=actionable,
            previous_direction=previous.direction if previous is not None else None,
            previous_confidence=previous.confidence if previous is not None else None,
            rationale=tuple(dict.fromkeys(rationale)),
        )


def _primary_thesis(context):
    pa = context.price_action_evidence
    oc = context.option_chain_evidence
    if any(conflict.primary_conflict for conflict in context.conflicts):
        return "Price Action and Option Chain Analytics conflict."
    if pa.direction is oc.direction and pa.direction in {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH}:
        return f"Price Action and Option Chain Analytics are aligned {pa.direction.value}."
    if pa.direction is not EvidenceDirection.UNAVAILABLE and oc.direction is EvidenceDirection.UNAVAILABLE:
        return f"Price Action is {pa.direction.value}, but Option Chain Analytics are unavailable."
    if oc.direction is not EvidenceDirection.UNAVAILABLE and pa.direction is EvidenceDirection.UNAVAILABLE:
        return f"Option Chain Analytics are {oc.direction.value}, but Price Action is unavailable."
    return "Insufficient primary evidence is available."


def _summary(context, conviction):
    if context.readiness is MarketContextReadiness.INSUFFICIENT:
        return f"{context.instrument.value} does not yet have sufficient primary evidence for a reliable market interpretation."
    if context.direction is MarketDirection.CONFLICTED:
        return (
            f"{context.instrument.value} has conflicting primary evidence. "
            "Secondary confirmations do not establish a reliable direction. "
            "New trades should be avoided until the conflict is resolved."
        )
    return (
        f"{context.instrument.value} has a {context.direction.value.replace('_', ' ')} market context "
        f"in a {context.regime.value.replace('_', ' ')} regime. "
        f"Trade posture is {context.trade_posture.value.replace('_', ' ')}. "
        f"Confidence is {conviction.value.replace('_', ' ')} and conflict is {context.conflict_severity.value}."
    )


def _supporting_points(evidence, limit):
    points = [
        item.explanation
        for item in evidence
        if item.role in {
            AIReasoningEvidenceRole.PRIMARY,
            AIReasoningEvidenceRole.CONFIRMATION,
        }
    ]
    return tuple(dict.fromkeys(points))[:limit]


def _conflicting_points(context, evidence, limit):
    points = [conflict.rationale for conflict in context.conflicts]
    points.extend(item.explanation for item in evidence if item.role is AIReasoningEvidenceRole.CONFLICT)
    return tuple(dict.fromkeys(points))[:limit]


def _cautions(context, severity, limit):
    cautions = []
    if severity is not AICautionSeverity.NONE:
        category = "primary_conflict" if any(conflict.primary_conflict for conflict in context.conflicts) else "context_caution"
        cautions.append(AIReasoningCaution(severity, category, "Context contains cautionary conditions and should be interpreted conditionally."))
    if context.readiness is MarketContextReadiness.PARTIAL:
        cautions.append(AIReasoningCaution(AICautionSeverity.MODERATE, "partial_readiness", "Only one primary source is available."))
    if context.readiness is MarketContextReadiness.INSUFFICIENT:
        cautions.append(AIReasoningCaution(AICautionSeverity.HIGH, "insufficient_data", "Primary market evidence is not yet sufficient."))
    for warning in context.warnings:
        category = "extension" if "extended" in warning else "missing_source"
        cautions.append(AIReasoningCaution(AICautionSeverity.LOW, category, warning))
    return tuple(dict.fromkeys(cautions))[:limit]


def _watch_conditions(context, limit):
    items = []
    if any(conflict.primary_conflict for conflict in context.conflicts):
        items.append(AIWatchCondition(1, "Wait for Price Action and Option Chain evidence to align.", "Primary evidence is conflicting."))
    if context.readiness is MarketContextReadiness.PARTIAL:
        items.append(AIWatchCondition(2, "Wait for the missing primary source before treating the context as fully confirmed.", "Readiness is partial."))
    if context.regime is MarketRegime.RANGE_BOUND:
        items.append(AIWatchCondition(3, "Wait for a confirmed break from the current range.", "The market context is range bound."))
    if context.regime is MarketRegime.BREAKOUT_ATTEMPT:
        items.append(AIWatchCondition(4, "Watch whether bullish structure sustains beyond the breakout area.", "The context is a breakout attempt."))
    if context.regime is MarketRegime.BREAKDOWN_ATTEMPT:
        items.append(AIWatchCondition(4, "Watch whether bearish structure sustains beyond the breakdown area.", "The context is a breakdown attempt."))
    if context.direction in {MarketDirection.BULLISH, MarketDirection.STRONGLY_BULLISH} and context.vwap_evidence.direction is EvidenceDirection.BEARISH:
        items.append(AIWatchCondition(5, "Watch whether price reclaims and sustains above VWAP.", "VWAP conflicts with bullish context."))
    if context.direction in {MarketDirection.BEARISH, MarketDirection.STRONGLY_BEARISH} and context.vwap_evidence.direction is EvidenceDirection.BULLISH:
        items.append(AIWatchCondition(5, "Watch whether price moves back below VWAP.", "VWAP conflicts with bearish context."))
    if any("Camarilla H5" in warning or "Camarilla L5" in warning for warning in context.warnings):
        items.append(AIWatchCondition(6, "Monitor extension risk near the outer Camarilla levels.", "Camarilla warning indicates extension risk."))
    if context.readiness is MarketContextReadiness.INSUFFICIENT:
        items.append(AIWatchCondition(1, "Wait for Price Action or Option Chain Analytics to become available.", "Primary context is insufficient."))
    return tuple(sorted(dict.fromkeys(items), key=lambda item: item.priority))[:limit]
