from tests.test_ai_reasoning_v2_interpreter import ctx

from engines.ai_reasoning_v2 import (
    AIReasoningState,
    AIReasoningV2Composer,
    AIReasoningV2Configuration,
    AIReasoningV2Input,
    AIReasoningV2Interpreter,
)
from engines.market_context_v2.enums import (
    MarketConflictSeverity,
    MarketContextReadiness,
    MarketDirection,
    TradePosture,
)


def compose(context):
    return AIReasoningV2Composer().compose(
        inputs=AIReasoningV2Input(context),
        configuration=AIReasoningV2Configuration(),
        interpreter=AIReasoningV2Interpreter(),
    )


def test_aligned_bullish_and_bearish_composition():
    bullish = compose(ctx(MarketDirection.STRONGLY_BULLISH, 0.9))
    assert bullish.direction.value == "strongly_bullish"
    assert bullish.actionable_context is True
    assert "aligned bullish" in bullish.primary_thesis
    assert bullish.supporting_points
    bearish = compose(ctx(MarketDirection.STRONGLY_BEARISH, 0.9, posture=TradePosture.LOOK_FOR_SHORTS))
    assert bearish.direction.value == "strongly_bearish"
    assert bearish.actionable_context is True


def test_conflicted_partial_and_insufficient_composition():
    conflicted = compose(ctx(MarketDirection.CONFLICTED, 0.2, posture=TradePosture.AVOID_NEW_TRADES, conflict=MarketConflictSeverity.HIGH))
    assert conflicted.actionable_context is False
    assert conflicted.reasoning_state is AIReasoningState.CONFLICTED_CONTEXT
    partial = compose(ctx(readiness=MarketContextReadiness.PARTIAL, posture=TradePosture.WAIT_FOR_CONFIRMATION))
    assert partial.actionable_context is False
    assert partial.watch_conditions
    insufficient = compose(ctx(MarketDirection.INSUFFICIENT_DATA, 0.0, MarketContextReadiness.INSUFFICIENT, TradePosture.INSUFFICIENT_DATA))
    assert insufficient.conviction.value == "unavailable"
    assert insufficient.reasoning_state is AIReasoningState.INSUFFICIENT_CONTEXT


def test_limits_and_deterministic_text():
    result = AIReasoningV2Composer().compose(
        inputs=AIReasoningV2Input(ctx()),
        configuration=AIReasoningV2Configuration(maximum_supporting_points=2, maximum_watch_conditions=1),
        interpreter=AIReasoningV2Interpreter(),
    )
    assert len(result.supporting_points) <= 2
    assert len(result.watch_conditions) <= 1
    assert result.headline == "NIFTY market context is bullish."
