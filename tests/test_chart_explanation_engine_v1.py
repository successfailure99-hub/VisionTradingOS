from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from application.orchestrator import ApplicationOrchestrator
from core.event_bus import EventBus
from core.events import (
    CHART_EXPLANATION_FAILED,
    CHART_EXPLANATION_INVALID,
    CHART_EXPLANATION_PARTIAL,
    CHART_EXPLANATION_UPDATED,
)
from engines.chart_explanation import (
    ChartExplanationEngine,
    ChartExplanationLifecycle,
    ChartExplanationSnapshot,
    ExplanationQuality,
)
from engines.expert_setup_classification import ExpertSetup
from engines.market_context.enums import MarketBias
from engines.market_state import (
    MarketEvidenceQuality,
    MarketStability,
    MarketState,
    VolatilityState,
)
from engines.multi_timeframe_evidence_fusion import EvidenceConflict
from tests.test_expert_setup_classification_engine_v1 import setup_engine
from tests.test_market_state_engine_v1 import fused, market_state_engine
from tests.test_tradingview_evidence_assembly_coordinator_v1 import live_tick
from tests.test_tradingview_evidence_mapping_engine_v1 import NOW


def explanation_engine(bus=None):
    item = ChartExplanationEngine(bus or EventBus(), instrument=RuntimeInstrument.NIFTY)
    item.start()
    return item


def intelligence_inputs(biases=(MarketBias.BULLISH, MarketBias.BULLISH), *, timeframes=("1m", "5m"), timestamp=NOW):
    fusion = fused(biases, timeframes=timeframes, timestamp=timestamp)
    state = market_state_engine().process(fusion, timestamp=timestamp)
    setup = setup_engine().process(fusion, state, timestamp=timestamp)
    return fusion, state, setup


def explain(fusion, state, setup, *, timestamp=NOW):
    return explanation_engine().process(fusion, state, setup, timestamp=timestamp)


def test_trend_continuation_explanation_is_deterministic_and_read_only():
    fusion, state, setup = intelligence_inputs()

    result = explain(fusion, state, setup)
    repeated = explain(fusion, state, setup)

    assert isinstance(result, ChartExplanationSnapshot)
    assert result == repeated
    assert result.headline == "Bullish Trend Continuation"
    assert "trending" in result.market_summary
    assert "trend_day" in result.market_summary
    assert result.explanation_quality is ExplanationQuality.HIGH
    assert result.trade_decision_generated is False
    assert result.strategy_calls == 0
    assert result.confidence_calls == 0
    assert result.risk_calls == 0
    assert result.execution_calls == 0
    assert result.broker_order_calls == 0
    assert result.live_order_submission_enabled is False
    forbidden = ("BUY", "SELL", "LONG", "SHORT", "ENTRY", "EXIT", "TARGET", "STOP LOSS")
    text = " ".join(
        (
            result.headline,
            result.market_summary,
            result.primary_setup_explanation,
            *result.supporting_evidence,
            *result.conflicting_evidence,
            *result.risk_notes,
        )
    ).upper()
    assert all(term not in text for term in forbidden)


def test_range_breakout_failed_breakout_bull_trap_and_partial_headlines():
    range_fusion, range_state, range_setup = intelligence_inputs((MarketBias.NEUTRAL, MarketBias.NEUTRAL))
    trend_fusion, trend_state, _ = intelligence_inputs()
    breakout_fusion = replace(
        trend_fusion,
        evidence_conflict=EvidenceConflict.MINOR,
        conflicting_timeframes=("1m",),
        source_fingerprint="breakout-fusion",
    )
    breakout_state = replace(
        trend_state,
        market_state=MarketState.TRANSITION,
        market_stability=MarketStability.CHANGING,
        source_fingerprint="breakout-state",
    )
    breakout_setup = setup_engine().process(breakout_fusion, breakout_state, timestamp=NOW)
    failed_fusion = replace(
        breakout_fusion,
        evidence_conflict=EvidenceConflict.MAJOR,
        conflict_score=60.0,
        source_fingerprint="failed-fusion",
    )
    failed_state = replace(
        breakout_state,
        market_state=MarketState.VOLATILE,
        market_stability=MarketStability.UNSTABLE,
        volatility_state=VolatilityState.VOLATILE,
        source_fingerprint="failed-state",
    )
    failed_setup = setup_engine().process(failed_fusion, failed_state, timestamp=NOW)
    trap_fusion = replace(
        trend_fusion,
        evidence_conflict=EvidenceConflict.MAJOR,
        conflicting_timeframes=("5m",),
        conflict_score=40.0,
        source_fingerprint="trap-fusion",
    )
    trap_state = replace(
        trend_state,
        market_state=MarketState.TRANSITION,
        market_stability=MarketStability.UNSTABLE,
        volatility_state=VolatilityState.VOLATILE,
        source_fingerprint="trap-state",
    )
    trap_setup = setup_engine().process(trap_fusion, trap_state, timestamp=NOW)
    partial_setup = replace(range_setup, setup_quality=range_setup.setup_quality, source_fingerprint="partial-setup")

    assert explain(range_fusion, range_state, range_setup).headline == "Range-Bound Market"
    assert explain(breakout_fusion, breakout_state, breakout_setup).headline == "Breakout Attempt"
    assert explain(failed_fusion, failed_state, failed_setup).headline == "Failed Breakout"
    assert explain(trap_fusion, trap_state, trap_setup).headline == "Bull Trap"
    assert explain(range_fusion, replace(range_state, evidence_quality=MarketEvidenceQuality.LOW), partial_setup).headline == "Low-Quality Setup"


def test_missing_inputs_and_stale_setup_publish_partial():
    bus = EventBus()
    partial = []
    bus.subscribe(CHART_EXPLANATION_PARTIAL, lambda payload: partial.append(payload))
    item = explanation_engine(bus)
    fusion, state, setup = intelligence_inputs()

    missing_fusion = item.process(None, state, setup, timestamp=NOW)
    missing_state = item.process(fusion, None, setup, timestamp=NOW + timedelta(seconds=1))
    missing_setup = item.process(fusion, state, None, timestamp=NOW + timedelta(seconds=2))
    stale = item.process(fusion, state, setup, timestamp=NOW + timedelta(minutes=6))

    assert missing_fusion.explanation_quality is ExplanationQuality.LOW
    assert missing_state.explanation_quality is ExplanationQuality.LOW
    assert missing_setup.explanation_quality is ExplanationQuality.LOW
    assert stale.explanation_quality is ExplanationQuality.LOW
    assert [item.headline for item in partial] == [
        "Low-Quality Setup",
        "Low-Quality Setup",
        "Low-Quality Setup",
        "Low-Quality Setup",
    ]
    assert item.snapshot().partial_count == 4


def test_duplicate_publication_is_suppressed_and_snapshot_is_immutable():
    bus = EventBus()
    updated = []
    bus.subscribe(CHART_EXPLANATION_UPDATED, lambda payload: updated.append(payload))
    item = explanation_engine(bus)
    fusion, state, setup = intelligence_inputs()

    first = item.process(fusion, state, setup, timestamp=NOW)
    second = item.process(fusion, state, setup, timestamp=NOW + timedelta(seconds=1))

    assert second is first
    assert updated == [first]
    assert item.snapshot().explanation_count == 1
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        first.headline = "Changed"


def test_invalid_input_and_unexpected_failure_publish_canonical_events(monkeypatch):
    bus = EventBus()
    invalid = []
    failed = []
    bus.subscribe(CHART_EXPLANATION_INVALID, lambda payload: invalid.append(payload))
    bus.subscribe(CHART_EXPLANATION_FAILED, lambda payload: failed.append(payload))
    item = explanation_engine(bus)
    fusion, state, setup = intelligence_inputs()

    with pytest.raises(TypeError):
        item.process(object(), state, setup, timestamp=NOW)

    assert item.snapshot().invalid_count == 1
    assert invalid[0].invalid_count == 1
    assert item.snapshot().lifecycle_state is ChartExplanationLifecycle.READY

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("engines.chart_explanation.engine._headline", fail)
    with pytest.raises(RuntimeError):
        item.process(fusion, state, setup, timestamp=NOW)

    assert item.snapshot().failed_count == 1
    assert item.snapshot().lifecycle_state is ChartExplanationLifecycle.FAILED
    assert failed[0].failed_count == 1


def test_runtime_integrates_one_chart_explanation_engine_after_setup_classification():
    bus = EventBus()
    partial = []
    bus.subscribe(CHART_EXPLANATION_PARTIAL, lambda payload: partial.append(payload))
    orchestrator = ApplicationOrchestrator(
        bus,
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.NIFTY,),
            timeframes=("1m",),
        ),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    orchestrator.warm_up_candles(RuntimeInstrument.NIFTY, ())
    orchestrator.process_tick(live_tick())
    orchestrator.process_tick(live_tick(timestamp=NOW + timedelta(minutes=1), price=101.0))

    snapshot = runtime.snapshot().chart_explanation
    assert runtime.chart_explanation_engine is runtime.chart_explanation_engine
    assert snapshot.explanation_count == 1
    assert snapshot.last_snapshot is not None
    assert snapshot.last_snapshot.instrument is RuntimeInstrument.NIFTY
    assert partial == [snapshot.last_snapshot]


def test_chart_explanation_consumes_only_intelligence_snapshots():
    source = "engines/chart_explanation/engine.py"
    text = open(source, encoding="utf-8").read()

    forbidden = (
        "engines.price_action",
        "engines.cpr",
        "engines.camarilla",
        "engines.vwap",
        "engines.adr",
        "engines.moving_average_context",
        "engines.momentum_context",
        "engines.volume_context",
        "engines.option_chain",
        "calculate_",
        "on_tick",
    )
    assert all(term not in text for term in forbidden)
    assert "MultiTimeframeEvidenceSnapshot" in text
    assert "MarketStateSnapshot" in text
    assert "ExpertSetupClassificationSnapshot" in text
