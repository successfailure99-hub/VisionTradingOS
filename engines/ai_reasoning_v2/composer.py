"""
Deterministic AI Reasoning Engine V2 composer.
"""

from datetime import datetime

from engines.ai_reasoning_v2.configuration import AIReasoningV2Configuration
from engines.ai_reasoning_v2.enums import AICautionSeverity, AIReasoningState
from engines.ai_reasoning_v2.interpreter import AIReasoningV2Interpreter
from engines.ai_reasoning_v2.models import (
    AIReasoningCaution,
    AIReasoningV2Input,
    AIReasoningV2Snapshot,
    AIWatchCondition,
)


_FORBIDDEN_WORDS = ("buy", "sell", "long", "short", "entry", "exit", "target", "stop", "position size")


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
        timestamp: datetime | None = None,
    ) -> AIReasoningV2Snapshot:
        if not isinstance(inputs, AIReasoningV2Input):
            raise TypeError("inputs must be AIReasoningV2Input")
        if not isinstance(configuration, AIReasoningV2Configuration):
            raise TypeError("configuration must be AIReasoningV2Configuration")
        if not isinstance(interpreter, AIReasoningV2Interpreter):
            raise TypeError("interpreter must be AIReasoningV2Interpreter")
        output_timestamp = timestamp or inputs.chart_explanation.timestamp
        direction = interpreter.direction(inputs)
        conviction = interpreter.conviction(inputs, configuration)
        state = interpreter.reasoning_state(inputs)
        change = interpreter.change_type(inputs, inputs.previous_reasoning, configuration)
        caution_severity = interpreter.caution_severity(inputs)
        evidence = interpreter.interpret_evidence(inputs, configuration)
        supporting = _supporting_points(inputs, evidence, configuration.maximum_supporting_points)
        conflicting = _conflicting_points(inputs, configuration.maximum_conflicting_points)
        cautions = _cautions(inputs, caution_severity, configuration.maximum_cautions)
        watch = _watch_conditions(inputs, configuration.maximum_watch_conditions)
        confidence = _confidence_from_conviction(conviction)
        actionable = state is AIReasoningState.ACTIONABLE_CONTEXT
        headline = _headline(inputs, direction)
        summary = _summary(inputs, conviction)
        thesis = _primary_thesis(inputs)
        rationale = _clean_text(
            (
                thesis,
                summary,
                f"Fusion agreement is {inputs.multi_timeframe_evidence.evidence_agreement.value}.",
                f"Market state is {inputs.market_state.market_state.value}.",
                f"Setup classification is {inputs.setup_classification.primary_setup.value}.",
                f"Chart explanation quality is {inputs.chart_explanation.explanation_quality.value}.",
            )
        )
        previous = inputs.previous_reasoning
        return AIReasoningV2Snapshot(
            trading_date=inputs.multi_timeframe_evidence.trading_date,
            instrument=_instrument_for_snapshot(inputs.multi_timeframe_evidence.instrument),
            timestamp=output_timestamp,
            direction=direction,
            conviction=conviction,
            reasoning_state=state,
            change=change,
            caution_severity=caution_severity,
            multi_timeframe_evidence=inputs.multi_timeframe_evidence,
            market_state=inputs.market_state,
            setup_classification=inputs.setup_classification,
            chart_explanation=inputs.chart_explanation,
            headline=headline,
            summary=summary,
            primary_thesis=thesis,
            evidence=evidence,
            supporting_points=supporting,
            conflicting_points=conflicting,
            cautions=cautions,
            watch_conditions=watch,
            confidence=confidence,
            actionable_context=actionable,
            previous_direction=previous.direction if previous is not None else None,
            previous_confidence=previous.confidence if previous is not None else None,
            rationale=rationale,
            source_fingerprint=_source_fingerprint(inputs, state),
        )


def _headline(inputs: AIReasoningV2Input, direction) -> str:
    setup = inputs.setup_classification.primary_setup
    if inputs.multi_timeframe_evidence.evidence_completeness.value != "complete":
        return "Partial Deterministic Intelligence"
    if setup.value == "no_quality_setup":
        return "Low-Quality Market Explanation"
    setup_text = setup.value.replace("_", " ").title()
    if direction.value in {"bullish", "strongly_bullish"}:
        return f"Bullish {setup_text}"
    if direction.value in {"bearish", "strongly_bearish"}:
        return f"Bearish {setup_text}"
    if direction.value == "conflicted":
        return f"Conflicted {setup_text}"
    return setup_text


def _summary(inputs: AIReasoningV2Input, conviction) -> str:
    fusion = inputs.multi_timeframe_evidence
    market_state = inputs.market_state
    setup = inputs.setup_classification
    explanation = inputs.chart_explanation
    return _safe_sentence(
        f"{explanation.headline} is explained by {fusion.evidence_agreement.value} "
        f"multi-timeframe evidence, {market_state.market_state.value} market state, "
        f"and {setup.primary_setup.value} setup classification. "
        f"Structural conviction is {conviction.value}."
    )


def _primary_thesis(inputs: AIReasoningV2Input) -> str:
    return _safe_sentence(
        f"The deterministic intelligence layer describes {inputs.market_state.market_state.value} "
        f"conditions with {inputs.setup_classification.setup_quality.value} setup quality."
    )


def _supporting_points(inputs: AIReasoningV2Input, evidence, limit: int) -> tuple[str, ...]:
    points = [
        item.explanation
        for item in evidence
        if item.role.value in {"primary", "confirmation"}
    ]
    points.extend(inputs.chart_explanation.supporting_evidence)
    return _clean_text(points)[:limit]


def _conflicting_points(inputs: AIReasoningV2Input, limit: int) -> tuple[str, ...]:
    points: list[str] = []
    points.extend(inputs.chart_explanation.conflicting_evidence)
    points.extend(inputs.setup_classification.conflicting_evidence)
    if inputs.multi_timeframe_evidence.evidence_conflict.value != "none":
        points.append(f"Fusion conflict is {inputs.multi_timeframe_evidence.evidence_conflict.value}.")
    return _clean_text(points or ("No major deterministic conflict reported.",))[:limit]


def _cautions(inputs: AIReasoningV2Input, severity: AICautionSeverity, limit: int) -> tuple[AIReasoningCaution, ...]:
    if severity is AICautionSeverity.NONE:
        return ()
    cautions = [
        AIReasoningCaution(
            severity=severity,
            category="deterministic_intelligence",
            message="AI Reasoning V2 found cautionary conditions in deterministic intelligence.",
        )
    ]
    for note in inputs.chart_explanation.risk_notes:
        cautions.append(AIReasoningCaution(severity=severity, category="chart_explanation", message=note))
    return tuple(dict.fromkeys(cautions))[:limit]


def _watch_conditions(inputs: AIReasoningV2Input, limit: int) -> tuple[AIWatchCondition, ...]:
    items = [
        AIWatchCondition(
            priority=1,
            condition="Monitor whether the deterministic intelligence remains internally consistent.",
            reason=f"Fusion completeness is {inputs.multi_timeframe_evidence.evidence_completeness.value}.",
        )
    ]
    if inputs.multi_timeframe_evidence.conflicting_timeframes:
        items.append(
            AIWatchCondition(
                priority=2,
                condition="Monitor the conflicting timeframe group.",
                reason="Conflicting timeframes are reported by Fusion.",
            )
        )
    if inputs.market_state.market_stability.value != "stable":
        items.append(
            AIWatchCondition(
                priority=3,
                condition="Monitor whether market state stabilizes.",
                reason=f"Market stability is {inputs.market_state.market_stability.value}.",
            )
        )
    return tuple(dict.fromkeys(items))[:limit]


def _confidence_from_conviction(conviction) -> float:
    return {
        "very_high": 0.9,
        "high": 0.75,
        "moderate": 0.6,
        "low": 0.4,
        "very_low": 0.2,
        "unavailable": 0.0,
    }[conviction.value]


def _source_fingerprint(inputs: AIReasoningV2Input, state: AIReasoningState) -> str:
    return "|".join(
        (
            inputs.multi_timeframe_evidence.source_fingerprint,
            inputs.market_state.source_fingerprint,
            inputs.setup_classification.source_fingerprint,
            inputs.chart_explanation.source_fingerprint,
            state.value,
        )
    )


def _instrument_for_snapshot(instrument):
    from core.enums.instrument import Instrument

    for item in Instrument:
        if item.value == instrument.value:
            return item
    raise ValueError("unsupported deterministic intelligence instrument")


def _clean_text(values) -> tuple[str, ...]:
    cleaned = []
    for value in values:
        text = _safe_sentence(value)
        if text not in cleaned:
            cleaned.append(text)
    return tuple(cleaned)


def _safe_sentence(value: str) -> str:
    text = str(value).strip().replace("_", " ")
    lowered = text.lower()
    for word in _FORBIDDEN_WORDS:
        lowered = lowered.replace(word, "")
    text = lowered.strip()
    if not text:
        text = "deterministic intelligence unavailable"
    text = text[0].upper() + text[1:]
    return text if text.endswith(".") else text + "."
