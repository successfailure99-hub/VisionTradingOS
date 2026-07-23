from datetime import timedelta

import pytest

from application.enums import RuntimeInstrument
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import AI_REASONING_V2_READY, AI_REASONING_V2_UPDATED
from engines.multi_timeframe_evidence_fusion.enums import EvidenceCompleteness, FusionDirection
from tests.test_ai_reasoning_v2_interpreter import NOW, intelligence
from tests.test_ai_reasoning_v2_models import explanation, fusion, market_state, setup
from engines.ai_reasoning_v2 import (
    AI_REASONING_V2_INVALID,
    AI_REASONING_V2_PARTIAL,
    AI_REASONING_V2_STATE_UPDATED,
    AIReasoningV2Configuration,
    AIReasoningV2Engine,
)


def test_constructor_initial_state_first_process_and_events():
    events = []
    bus = EventBus()
    bus.subscribe(AI_REASONING_V2_UPDATED, lambda payload: events.append(("updated", payload)))
    bus.subscribe(AI_REASONING_V2_READY, lambda payload: events.append(("ready", payload)))
    bus.subscribe(AI_REASONING_V2_STATE_UPDATED, lambda payload: events.append(("state", payload)))
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY, event_bus=bus)
    inputs = intelligence()

    assert engine.snapshot is None
    assert engine.previous_snapshot is None
    assert engine.is_ready is False
    result = engine.process(
        inputs.multi_timeframe_evidence,
        inputs.market_state,
        inputs.setup_classification,
        inputs.chart_explanation,
    )

    assert engine.snapshot is result
    assert engine.is_ready is True
    assert [name for name, _ in events] == ["updated", "ready", "state"]
    assert engine.update(
        inputs.multi_timeframe_evidence,
        inputs.market_state,
        inputs.setup_classification,
        inputs.chart_explanation,
    ) is result
    assert engine.updated_count == 1


def test_partial_invalid_history_reset_and_clear():
    bus = EventBus()
    partial_events = []
    invalid_events = []
    bus.subscribe(AI_REASONING_V2_PARTIAL, partial_events.append)
    bus.subscribe(AI_REASONING_V2_INVALID, invalid_events.append)
    engine = AIReasoningV2Engine(
        instrument=Instrument.NIFTY,
        configuration=AIReasoningV2Configuration(history_limit=2),
        event_bus=bus,
    )

    complete = intelligence()
    first = engine.process(
        complete.multi_timeframe_evidence,
        complete.market_state,
        complete.setup_classification,
        complete.chart_explanation,
    )
    partial = intelligence(completeness=EvidenceCompleteness.PARTIAL, minute=1)
    second = engine.process(
        partial.multi_timeframe_evidence,
        partial.market_state,
        partial.setup_classification,
        partial.chart_explanation,
    )

    assert second is not first
    assert engine.previous_snapshot is first
    assert engine.partial_count == 1
    assert partial_events == [second]
    assert len(engine.history()) == 2

    with pytest.raises(TypeError):
        engine.process(None, partial.market_state, partial.setup_classification, partial.chart_explanation)
    assert invalid_events

    engine.reset()
    assert engine.snapshot is None
    engine.process(
        complete.multi_timeframe_evidence,
        complete.market_state,
        complete.setup_classification,
        complete.chart_explanation,
    )
    engine.clear()
    assert engine.history() == ()


def test_stale_upstream_degrades_to_partial_without_exception():
    bus = EventBus()
    partial_events = []
    bus.subscribe(AI_REASONING_V2_PARTIAL, partial_events.append)
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY, event_bus=bus)
    inputs = intelligence()

    result = engine.process(
        inputs.multi_timeframe_evidence,
        inputs.market_state,
        inputs.setup_classification,
        inputs.chart_explanation,
        timestamp=NOW + timedelta(minutes=6),
    )

    assert result.reasoning_state.value in {"actionable_context", "waiting_confirmation"}
    assert engine.partial_count == 1
    assert partial_events == [result]


def test_wrong_instrument_and_future_timestamp_are_rejected():
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY)
    bad = intelligence()

    with pytest.raises(ValueError):
        engine.process(
            fusion(instrument=RuntimeInstrument.BANKNIFTY),
            market_state(instrument=RuntimeInstrument.BANKNIFTY),
            setup(instrument=RuntimeInstrument.BANKNIFTY),
            explanation(instrument=RuntimeInstrument.BANKNIFTY),
        )

    with pytest.raises(ValueError):
        engine.process(
            bad.multi_timeframe_evidence,
            bad.market_state,
            bad.setup_classification,
            bad.chart_explanation,
            timestamp=NOW - timedelta(minutes=1),
        )


def test_observable_idempotency_ignores_source_fingerprint_changes():
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY)
    first = intelligence()
    result = engine.process(
        first.multi_timeframe_evidence,
        first.market_state,
        first.setup_classification,
        first.chart_explanation,
    )
    changed_fingerprints = intelligence()
    duplicate = engine.process(
        fusion(source_fingerprint="changed-fusion"),
        market_state(source_fingerprint="changed-market"),
        setup(source_fingerprint="changed-setup"),
        explanation(source_fingerprint="changed-explanation"),
    )

    assert duplicate is result
    assert engine.updated_count == 1


def test_changed_observable_direction_publishes_new_snapshot():
    engine = AIReasoningV2Engine(instrument=Instrument.NIFTY)
    first = intelligence(direction=FusionDirection.BULLISH)
    second = intelligence(direction=FusionDirection.BEARISH, minute=1)
    one = engine.process(
        first.multi_timeframe_evidence,
        first.market_state,
        first.setup_classification,
        first.chart_explanation,
    )
    two = engine.process(
        second.multi_timeframe_evidence,
        second.market_state,
        second.setup_classification,
        second.chart_explanation,
    )

    assert two is not one
    assert two.direction.value == "bearish"
    assert engine.updated_count == 2
