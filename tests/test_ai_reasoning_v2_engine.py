from datetime import timedelta

import pytest

from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import AI_REASONING_V2_READY, AI_REASONING_V2_UPDATED
from engines.ai_reasoning_v2 import AIReasoningV2Configuration, AIReasoningV2Engine
from engines.market_context_v2.enums import MarketDirection
from tests.test_ai_reasoning_v2_interpreter import NOW, ctx


def test_constructor_initial_state_first_process_and_events():
    events = []
    bus = EventBus()
    bus.subscribe(AI_REASONING_V2_UPDATED, lambda payload: events.append(("updated", payload)))
    bus.subscribe(AI_REASONING_V2_READY, lambda payload: events.append(("ready", payload)))
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY, event_bus=bus)
    assert engine.snapshot is None
    assert engine.previous_snapshot is None
    assert engine.is_ready is False
    result = engine.process(ctx())
    assert engine.snapshot is result
    assert engine.is_ready is True
    assert [name for name, _ in events] == ["updated", "ready"]
    assert engine.update(ctx()) is result


def test_correction_history_stale_wrong_instrument_reset_and_clear():
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY, configuration=AIReasoningV2Configuration(history_limit=2))
    first = engine.process(ctx())
    corrected = engine.process(ctx(confidence=0.8))
    assert corrected is not first
    assert len(engine.history()) == 1
    newer = ctx(MarketDirection.STRONGLY_BULLISH, 0.9)
    newer = type(newer)(**{**{field: getattr(newer, field) for field in newer.__dataclass_fields__}, "timestamp": NOW + timedelta(minutes=1)})
    second = engine.process(newer)
    assert engine.previous_snapshot is corrected
    assert second.change.value in {"strengthened", "unchanged"}
    older = type(newer)(**{**{field: getattr(newer, field) for field in newer.__dataclass_fields__}, "timestamp": NOW - timedelta(minutes=1)})
    with pytest.raises(ValueError):
        engine.process(older)
    with pytest.raises(ValueError):
        AIReasoningV2Engine(instrument=Instrument.SBI)
    engine.reset()
    assert engine.snapshot is None
    engine.process(ctx())
    engine.clear()
    assert engine.history() == ()
