from datetime import timedelta

import pytest

from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import STRATEGY_DECISION_V2_READY, STRATEGY_DECISION_V2_UPDATED
from engines.strategy_decision_v2 import StrategyDecisionV2Configuration, StrategyDecisionV2Engine, StrategyDecisionV2Input
from tests.test_strategy_decision_v2_integration import build_stack, cam, cpr, replace_context, vwap


def input_for(reasoning):
    return StrategyDecisionV2Input(reasoning, 108.0, cam(), cpr(), vwap())


def test_constructor_first_process_update_duplicate_and_events():
    events = []
    bus = EventBus()
    bus.subscribe(STRATEGY_DECISION_V2_UPDATED, lambda payload: events.append(("updated", payload)))
    bus.subscribe(STRATEGY_DECISION_V2_READY, lambda payload: events.append(("ready", payload)))
    engine = StrategyDecisionV2Engine(instrument=Instrument.NIFTY, event_bus=bus)
    assert engine.snapshot is None
    result = engine.process(input_for(build_stack("bullish")))
    assert engine.snapshot is result
    assert engine.is_ready is True
    assert engine.update(input_for(build_stack("bullish"))) is result
    assert [name for name, _ in events] == ["updated", "ready"]


def test_correction_history_stale_reset_clear_and_isolation():
    engine = StrategyDecisionV2Engine(instrument=Instrument.NIFTY, configuration=StrategyDecisionV2Configuration(history_limit=2))
    first_reasoning = build_stack("bullish")
    first = engine.process(input_for(first_reasoning))
    corrected_reasoning = replace_context(first_reasoning, confidence=0.8)
    corrected = engine.process(input_for(corrected_reasoning))
    assert corrected is not first
    assert len(engine.history()) == 1
    later_context = replace_context(first_reasoning, timestamp=first_reasoning.timestamp + timedelta(minutes=1))
    later = engine.process(input_for(later_context))
    assert engine.previous_snapshot is corrected
    stale_context = replace_context(first_reasoning, timestamp=first_reasoning.timestamp - timedelta(minutes=1))
    with pytest.raises(ValueError):
        engine.process(input_for(stale_context))
    assert later is engine.snapshot
    other = StrategyDecisionV2Engine(instrument=Instrument.BANKNIFTY)
    assert other.snapshot is None
    engine.reset()
    assert engine.history() == ()
    engine.process(input_for(first_reasoning))
    engine.clear()
    assert engine.is_ready is False
    with pytest.raises(ValueError):
        StrategyDecisionV2Engine(instrument=Instrument.SBI)
