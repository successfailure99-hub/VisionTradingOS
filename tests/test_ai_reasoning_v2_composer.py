from application.enums import RuntimeInstrument  # noqa: F401
from engines.expert_setup_classification.enums import SetupQuality
from engines.multi_timeframe_evidence_fusion.enums import EvidenceCompleteness, EvidenceConflict, FusionDirection
from tests.test_ai_reasoning_v2_interpreter import intelligence
from engines.ai_reasoning_v2 import (
    AIReasoningState,
    AIReasoningV2Composer,
    AIReasoningV2Configuration,
    AIReasoningV2Interpreter,
)


def compose(inputs):
    return AIReasoningV2Composer().compose(
        inputs=inputs,
        configuration=AIReasoningV2Configuration(),
        interpreter=AIReasoningV2Interpreter(),
    )


def test_aligned_bullish_and_bearish_composition():
    bullish = compose(intelligence(direction=FusionDirection.BULLISH, alignment=96.0))
    assert bullish.direction.value == "bullish"
    assert bullish.actionable_context is True
    assert "trending conditions" in bullish.primary_thesis
    assert bullish.supporting_points

    bearish = compose(intelligence(direction=FusionDirection.BEARISH, alignment=96.0))
    assert bearish.direction.value == "bearish"
    assert bearish.actionable_context is True


def test_conflicted_partial_and_insufficient_composition():
    conflicted = compose(intelligence(evidence_conflict=EvidenceConflict.MAJOR, conflict_score=80.0))
    assert conflicted.actionable_context is False
    assert conflicted.reasoning_state is AIReasoningState.CONFLICTED_CONTEXT

    partial = compose(intelligence(completeness=EvidenceCompleteness.PARTIAL, quality=SetupQuality.MEDIUM))
    assert partial.actionable_context is False
    assert partial.watch_conditions

    insufficient = compose(intelligence(completeness=EvidenceCompleteness.INSUFFICIENT, alignment=0.0))
    assert insufficient.conviction.value == "unavailable"
    assert insufficient.reasoning_state is AIReasoningState.INSUFFICIENT_CONTEXT


def test_limits_deterministic_text_and_forbidden_vocabulary():
    inputs = intelligence()
    result = AIReasoningV2Composer().compose(
        inputs=inputs,
        configuration=AIReasoningV2Configuration(maximum_supporting_points=2, maximum_watch_conditions=1),
        interpreter=AIReasoningV2Interpreter(),
    )
    duplicate = AIReasoningV2Composer().compose(
        inputs=inputs,
        configuration=AIReasoningV2Configuration(maximum_supporting_points=2, maximum_watch_conditions=1),
        interpreter=AIReasoningV2Interpreter(),
    )

    assert result == duplicate
    assert len(result.supporting_points) <= 2
    assert len(result.watch_conditions) <= 1
    combined = " ".join(
        (
            result.headline,
            result.summary,
            result.primary_thesis,
            " ".join(result.supporting_points),
            " ".join(result.conflicting_points),
            " ".join(item.message for item in result.cautions),
        )
    ).lower()
    for word in ("buy", "sell", "long", "short", "entry", "exit", "target", "stop", "position size"):
        assert word not in combined
