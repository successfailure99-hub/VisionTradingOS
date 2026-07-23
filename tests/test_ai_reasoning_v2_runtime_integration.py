from datetime import timedelta

from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from application.orchestrator import ApplicationOrchestrator
from core.event_bus import EventBus
from core.events import (
    CHART_EXPLANATION_PARTIAL,
    MARKET_STATE_PARTIAL,
    MULTI_TIMEFRAME_EVIDENCE_PARTIAL,
    SETUP_CLASSIFICATION_PARTIAL,
)
from engines.ai_reasoning_v2 import AI_REASONING_V2_PARTIAL
from tests.test_ai_reasoning_v2_models import NOW as AI_NOW
from tests.test_ai_reasoning_v2_models import explanation, fusion, market_state, setup
from tests.test_tradingview_evidence_assembly_coordinator_v1 import NOW as RUNTIME_NOW
from tests.test_tradingview_evidence_assembly_coordinator_v1 import live_tick


def runtime_with_events(events=None):
    bus = EventBus()
    if events is not None:
        for event_name, label in (
            (MULTI_TIMEFRAME_EVIDENCE_PARTIAL, "fusion"),
            (MARKET_STATE_PARTIAL, "market_state"),
            (SETUP_CLASSIFICATION_PARTIAL, "setup"),
            (CHART_EXPLANATION_PARTIAL, "chart_explanation"),
            (AI_REASONING_V2_PARTIAL, "ai_reasoning_v2"),
        ):
            bus.subscribe(event_name, lambda _payload, item=label: events.append(item))
    orchestrator = ApplicationOrchestrator(
        bus,
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.NIFTY,),
            timeframes=("1m",),
        ),
    )
    orchestrator.start()
    return orchestrator, orchestrator.get_runtime(RuntimeInstrument.NIFTY)


def close_one_runtime_candle(orchestrator):
    orchestrator.warm_up_candles(RuntimeInstrument.NIFTY, ())
    orchestrator.process_tick(live_tick())
    orchestrator.process_tick(live_tick(timestamp=RUNTIME_NOW + timedelta(minutes=1), price=101.0))


def current_intelligence(runtime):
    return (
        runtime.multi_timeframe_evidence_fusion_engine.snapshot().last_snapshot,
        runtime.market_state_engine.snapshot().last_snapshot,
        runtime.setup_classification_engine.snapshot().last_snapshot,
        runtime.chart_explanation_engine.snapshot().last_snapshot,
    )


def test_runtime_executes_ai_reasoning_v2_after_chart_explanation():
    events = []
    orchestrator, runtime = runtime_with_events(events)

    orchestrator.process_tick(live_tick())
    assert runtime.chart_explanation_engine.snapshot().last_snapshot is None
    assert runtime.ai_reasoning_v2_engine.snapshot is None

    orchestrator.process_tick(live_tick(timestamp=RUNTIME_NOW + timedelta(minutes=1), price=101.0))

    assert runtime.chart_explanation_engine.snapshot().last_snapshot is not None
    assert runtime.ai_reasoning_v2_engine.snapshot is not None
    assert events.index("chart_explanation") < events.index("ai_reasoning_v2")


def test_runtime_ordering_remains_deterministic_through_ai_reasoning_v2():
    events = []
    orchestrator, runtime = runtime_with_events(events)

    close_one_runtime_candle(orchestrator)

    assert events == [
        "fusion",
        "market_state",
        "setup",
        "chart_explanation",
        "ai_reasoning_v2",
    ]
    assert runtime.ai_reasoning_v2_engine.partial_count == 1


def test_partial_runtime_explanation_produces_partial_ai_reasoning_v2():
    events = []
    orchestrator, runtime = runtime_with_events(events)

    close_one_runtime_candle(orchestrator)

    assert runtime.chart_explanation_engine.snapshot().partial_count == 1
    assert runtime.ai_reasoning_v2_engine.partial_count == 1
    assert events[-1] == "ai_reasoning_v2"


def test_stale_runtime_intelligence_degrades_ai_reasoning_v2_to_partial():
    _orchestrator, runtime = runtime_with_events()

    runtime.ai_reasoning_v2_engine.process(
        fusion(),
        market_state(),
        setup(),
        explanation(),
        timestamp=AI_NOW,
    )
    runtime.ai_reasoning_v2_engine.process(
        fusion(),
        market_state(),
        setup(),
        explanation(),
        timestamp=AI_NOW + timedelta(minutes=6),
    )

    assert runtime.ai_reasoning_v2_engine.updated_count == 1
    assert runtime.ai_reasoning_v2_engine.partial_count == 1


def test_duplicate_runtime_explanation_does_not_republish_ai_reasoning_v2():
    events = []
    orchestrator, runtime = runtime_with_events(events)

    close_one_runtime_candle(orchestrator)
    first = runtime.ai_reasoning_v2_engine.snapshot
    fusion_snapshot, state_snapshot, setup_snapshot, explanation_snapshot = current_intelligence(runtime)

    duplicate = runtime.ai_reasoning_v2_engine.process(
        fusion_snapshot,
        state_snapshot,
        setup_snapshot,
        explanation_snapshot,
        timestamp=explanation_snapshot.timestamp,
    )

    assert duplicate is first
    assert runtime.ai_reasoning_v2_engine.partial_count == 1
    assert events == [
        "fusion",
        "market_state",
        "setup",
        "chart_explanation",
        "ai_reasoning_v2",
    ]
