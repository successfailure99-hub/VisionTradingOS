from application.enums import RuntimeInstrument  # noqa: F401
from core.enums.instrument import Instrument
from engines.multi_timeframe_evidence_fusion.enums import FusionDirection
from tests.test_ai_reasoning_v2_interpreter import intelligence
from engines.ai_reasoning_v2 import AIReasoningChange, AIReasoningV2Engine


def _process(engine, inputs):
    return engine.process(
        inputs.multi_timeframe_evidence,
        inputs.market_state,
        inputs.setup_classification,
        inputs.chart_explanation,
    )


def test_direction_and_confidence_transitions():
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY)
    first = _process(engine, intelligence(direction=FusionDirection.NEUTRAL, alignment=40.0, minute=0))
    assert first.change is AIReasoningChange.INITIAL
    bullish = _process(engine, intelligence(direction=FusionDirection.BULLISH, alignment=60.0, minute=1))
    assert bullish.change is AIReasoningChange.TURNED_BULLISH
    stronger = _process(engine, intelligence(direction=FusionDirection.BULLISH, alignment=95.0, minute=2))
    assert stronger.change is AIReasoningChange.STRENGTHENED
    weaker = _process(engine, intelligence(direction=FusionDirection.BULLISH, alignment=30.0, conflict_score=50.0, minute=3))
    assert weaker.change is AIReasoningChange.WEAKENED
    bearish = _process(engine, intelligence(direction=FusionDirection.BEARISH, alignment=70.0, minute=4))
    assert bearish.change is AIReasoningChange.TURNED_BEARISH


def test_same_timestamp_first_record_correction_remains_initial():
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY)
    first = _process(engine, intelligence(direction=FusionDirection.NEUTRAL, alignment=40.0, minute=0))
    corrected = _process(engine, intelligence(direction=FusionDirection.BULLISH, alignment=60.0, minute=0))

    assert first.change is AIReasoningChange.INITIAL
    assert corrected.change is AIReasoningChange.INITIAL
    assert len(engine.history()) == 1


def test_same_timestamp_correction_compares_against_previous_distinct_state():
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY)
    first = _process(engine, intelligence(direction=FusionDirection.NEUTRAL, alignment=40.0, minute=0))
    second = _process(engine, intelligence(direction=FusionDirection.BULLISH, alignment=60.0, minute=1))
    corrected = _process(engine, intelligence(direction=FusionDirection.BEARISH, alignment=70.0, minute=1))

    assert first.change is AIReasoningChange.INITIAL
    assert second.change is AIReasoningChange.TURNED_BULLISH
    assert corrected.change is AIReasoningChange.TURNED_BEARISH
    assert engine.previous_snapshot is first
    assert len(engine.history()) == 2
