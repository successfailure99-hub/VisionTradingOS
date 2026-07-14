from engines.ai_reasoning_v2 import AIReasoningChange, AIReasoningV2Engine
from core.enums.instrument import Instrument
from engines.market_context_v2.enums import MarketDirection, TradePosture
from tests.test_ai_reasoning_v2_interpreter import ctx


def test_direction_and_confidence_transitions():
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY)
    first = engine.process(
        ctx(
            MarketDirection.NEUTRAL,
            0.4,
            minute=0,
            posture=TradePosture.WAIT_FOR_CONFIRMATION,
        )
    )
    assert first.change is AIReasoningChange.INITIAL
    bullish = engine.process(ctx(MarketDirection.BULLISH, 0.6, minute=1))
    assert bullish.change is AIReasoningChange.TURNED_BULLISH
    stronger = engine.process(ctx(MarketDirection.BULLISH, 0.8, minute=2))
    assert stronger.change is AIReasoningChange.STRENGTHENED
    weaker = engine.process(ctx(MarketDirection.BULLISH, 0.55, minute=3))
    assert weaker.change is AIReasoningChange.WEAKENED
    bearish = engine.process(
        ctx(
            MarketDirection.BEARISH,
            0.7,
            minute=4,
            posture=TradePosture.LOOK_FOR_SHORTS,
        )
    )
    assert bearish.change is AIReasoningChange.TURNED_BEARISH


def test_same_timestamp_first_record_correction_remains_initial():
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY)
    first = engine.process(
        ctx(
            MarketDirection.NEUTRAL,
            0.4,
            minute=0,
            posture=TradePosture.WAIT_FOR_CONFIRMATION,
        )
    )
    corrected = engine.process(ctx(MarketDirection.BULLISH, 0.6, minute=0))

    assert first.change is AIReasoningChange.INITIAL
    assert corrected.change is AIReasoningChange.INITIAL
    assert len(engine.history()) == 1


def test_same_timestamp_correction_compares_against_previous_distinct_state():
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY)
    first = engine.process(
        ctx(
            MarketDirection.NEUTRAL,
            0.4,
            minute=0,
            posture=TradePosture.WAIT_FOR_CONFIRMATION,
        )
    )
    second = engine.process(ctx(MarketDirection.BULLISH, 0.6, minute=1))
    corrected = engine.process(
        ctx(
            MarketDirection.BEARISH,
            0.7,
            minute=1,
            posture=TradePosture.LOOK_FOR_SHORTS,
        )
    )

    assert first.change is AIReasoningChange.INITIAL
    assert second.change is AIReasoningChange.TURNED_BULLISH
    assert corrected.change is AIReasoningChange.TURNED_BEARISH
    assert engine.previous_snapshot is first
    assert len(engine.history()) == 2
