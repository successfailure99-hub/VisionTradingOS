from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from application.orchestrator import ApplicationOrchestrator
from core.event_bus import EventBus
from core.events import (
    SETUP_CLASSIFICATION_FAILED,
    SETUP_CLASSIFICATION_INVALID,
    SETUP_CLASSIFICATION_PARTIAL,
    SETUP_CLASSIFICATION_UPDATED,
)
from engines.expert_setup_classification import (
    ExpertSetup,
    ExpertSetupClassificationEngine,
    SetupClassificationLifecycle,
    SetupQuality,
    SetupStability,
    SetupStrength,
)
from engines.market_context.enums import MarketBias
from engines.market_state import (
    MarketEvidenceQuality,
    MarketStability,
    MarketState,
    StructuralConfidence,
    VolatilityState,
)
from engines.multi_timeframe_evidence_fusion import (
    EvidenceAgreement,
    EvidenceCompleteness,
    EvidenceConflict,
)
from tests.test_market_state_engine_v1 import fused, market_state_engine
from tests.test_tradingview_evidence_assembly_coordinator_v1 import live_tick
from tests.test_tradingview_evidence_mapping_engine_v1 import NOW


def setup_engine(bus=None):
    item = ExpertSetupClassificationEngine(bus or EventBus(), instrument=RuntimeInstrument.NIFTY)
    item.start()
    return item


def setup_inputs(biases=(MarketBias.BULLISH, MarketBias.BULLISH), *, timeframes=("1m", "5m"), timestamp=NOW):
    fusion = fused(biases, timeframes=timeframes, timestamp=timestamp)
    state = market_state_engine().process(fusion, timestamp=timestamp)
    return fusion, state


def classify(fusion, state, *, timestamp=NOW):
    return setup_engine().process(fusion, state, timestamp=timestamp)


def test_trend_continuation_setup_is_descriptive_and_read_only():
    fusion, state = setup_inputs()
    state = replace(
        state,
        confidence_level=StructuralConfidence.MEDIUM_STRUCTURE,
        source_fingerprint="trend-continuation",
    )

    result = classify(fusion, state)

    assert result.primary_setup is ExpertSetup.TREND_CONTINUATION
    assert result.setup_strength is SetupStrength.STRONG
    assert result.setup_quality is SetupQuality.HIGH
    assert result.setup_stability is SetupStability.STABLE
    assert result.trade_decision_generated is False
    assert result.strategy_calls == 0
    assert result.confidence_calls == 0
    assert result.risk_calls == 0
    assert result.execution_calls == 0
    assert result.broker_order_calls == 0
    assert result.live_order_submission_enabled is False


def test_pullback_breakout_failed_breakout_trend_day_and_range_day_classifications():
    trend_fusion, trend_state = setup_inputs()
    pullback_state = replace(
        trend_state,
        market_state=MarketState.TRANSITION,
        market_stability=MarketStability.CHANGING,
        source_fingerprint="pullback",
    )
    breakout_fusion = replace(
        trend_fusion,
        evidence_conflict=EvidenceConflict.MINOR,
        evidence_agreement=EvidenceAgreement.PARTIAL_ALIGNMENT,
        conflicting_timeframes=("1m",),
        source_fingerprint="breakout-fusion",
    )
    breakout_state = replace(
        trend_state,
        market_state=MarketState.TRANSITION,
        market_stability=MarketStability.CHANGING,
        source_fingerprint="breakout",
    )
    failed_fusion = replace(
        trend_fusion,
        evidence_conflict=EvidenceConflict.MAJOR,
        conflicting_timeframes=("1m",),
        source_fingerprint="failed-fusion",
    )
    failed_state = replace(
        trend_state,
        market_state=MarketState.VOLATILE,
        market_stability=MarketStability.UNSTABLE,
        volatility_state=VolatilityState.VOLATILE,
        source_fingerprint="failed",
    )
    range_fusion, range_state = setup_inputs((MarketBias.NEUTRAL, MarketBias.NEUTRAL))

    assert classify(trend_fusion, pullback_state).primary_setup is ExpertSetup.PULLBACK_CONTINUATION
    assert classify(breakout_fusion, breakout_state).primary_setup is ExpertSetup.BREAKOUT
    assert classify(failed_fusion, failed_state).primary_setup is ExpertSetup.FAILED_BREAKOUT
    assert classify(trend_fusion, trend_state).primary_setup is ExpertSetup.TREND_DAY
    assert classify(range_fusion, range_state).primary_setup is ExpertSetup.RANGE_DAY


def test_compression_expansion_trap_reversal_liquidity_and_no_quality_setups():
    base_fusion, base_state = setup_inputs()
    compression_state = replace(
        base_state,
        market_state=MarketState.COMPRESSION,
        market_stability=MarketStability.CHANGING,
        source_fingerprint="compression",
    )
    expansion_state = replace(
        base_state,
        market_state=MarketState.EXPANSION,
        market_stability=MarketStability.CHANGING,
        source_fingerprint="expansion",
    )
    trap_fusion = replace(
        base_fusion,
        evidence_conflict=EvidenceConflict.MAJOR,
        conflicting_timeframes=("5m",),
        source_fingerprint="trap-fusion",
    )
    trap_state = replace(
        base_state,
        market_state=MarketState.TRANSITION,
        volatility_state=VolatilityState.VOLATILE,
        market_stability=MarketStability.UNSTABLE,
        source_fingerprint="trap-state",
    )
    bear_fusion, bear_state = setup_inputs((MarketBias.BEARISH, MarketBias.BEARISH))
    bear_trap_fusion = replace(
        bear_fusion,
        evidence_conflict=EvidenceConflict.MAJOR,
        conflicting_timeframes=("5m",),
        source_fingerprint="bear-trap-fusion",
    )
    bear_trap_state = replace(
        bear_state,
        market_state=MarketState.TRANSITION,
        volatility_state=VolatilityState.VOLATILE,
        market_stability=MarketStability.UNSTABLE,
        source_fingerprint="bear-trap-state",
    )
    reversal_state = replace(trap_state, source_fingerprint="reversal")
    sweep_fusion = replace(
        base_fusion,
        weak_timeframes=("1m",),
        conflicting_timeframes=("5m",),
        source_fingerprint="sweep-fusion",
    )
    sweep_state = replace(base_state, market_state=MarketState.QUIET, source_fingerprint="sweep-state")
    insufficient_fusion = replace(
        base_fusion,
        evidence_completeness=EvidenceCompleteness.INSUFFICIENT,
        source_fingerprint="insufficient-fusion",
    )

    assert classify(base_fusion, compression_state).primary_setup is ExpertSetup.COMPRESSION
    assert classify(base_fusion, expansion_state).primary_setup is ExpertSetup.EXPANSION
    assert classify(trap_fusion, trap_state).primary_setup is ExpertSetup.BULL_TRAP
    assert classify(bear_trap_fusion, bear_trap_state).primary_setup is ExpertSetup.BEAR_TRAP
    assert classify(replace(trap_fusion, summaries=(), dominant_timeframe="NONE"), reversal_state).primary_setup is ExpertSetup.REVERSAL_ATTEMPT
    assert classify(sweep_fusion, sweep_state).primary_setup is ExpertSetup.LIQUIDITY_SWEEP
    assert classify(insufficient_fusion, base_state).primary_setup is ExpertSetup.NO_QUALITY_SETUP


def test_partial_market_state_missing_and_stale_fusion_publish_partial():
    bus = EventBus()
    partial = []
    bus.subscribe(SETUP_CLASSIFICATION_PARTIAL, lambda payload: partial.append(payload))
    item = setup_engine(bus)
    fusion, state = setup_inputs()
    partial_state = replace(
        state,
        evidence_quality=MarketEvidenceQuality.LOW,
        market_state=MarketState.TRANSITION,
        source_fingerprint="partial-state",
    )

    first = item.process(fusion, partial_state, timestamp=NOW)
    missing = item.process(None, partial_state, timestamp=NOW + timedelta(seconds=1))
    stale = item.process(fusion, state, timestamp=NOW + timedelta(minutes=6))

    assert first.primary_setup is ExpertSetup.NO_QUALITY_SETUP
    assert missing.primary_setup is ExpertSetup.NO_QUALITY_SETUP
    assert stale.primary_setup is ExpertSetup.NO_QUALITY_SETUP
    assert partial == [first, missing, stale]
    assert item.snapshot().partial_count == 3


def test_duplicate_publication_idempotency_and_immutable_snapshot():
    bus = EventBus()
    updated = []
    bus.subscribe(SETUP_CLASSIFICATION_UPDATED, lambda payload: updated.append(payload))
    item = setup_engine(bus)
    fusion, state = setup_inputs()

    first = item.process(fusion, state, timestamp=NOW)
    second = item.process(fusion, state, timestamp=NOW + timedelta(seconds=1))

    assert second is first
    assert updated == [first]
    assert item.snapshot().classification_count == 1
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        first.primary_setup = ExpertSetup.BREAKOUT


def test_same_observable_setup_with_different_upstream_fingerprints_does_not_republish():
    bus = EventBus()
    updated = []
    bus.subscribe(SETUP_CLASSIFICATION_UPDATED, lambda payload: updated.append(payload))
    item = setup_engine(bus)
    fusion, state = setup_inputs()

    first = item.process(fusion, state, timestamp=NOW)
    fingerprint_changed_fusion = replace(fusion, source_fingerprint="changed-fusion")
    fingerprint_changed_state = replace(state, source_fingerprint="changed-market-state")
    second = item.process(
        fingerprint_changed_fusion,
        fingerprint_changed_state,
        timestamp=NOW + timedelta(seconds=1),
    )

    assert second is first
    assert updated == [first]
    assert item.snapshot().classification_count == 1
    assert item.snapshot().updated_count == 1


def test_complete_setup_publishes_partial_when_market_state_later_becomes_stale():
    bus = EventBus()
    updated = []
    partial = []
    bus.subscribe(SETUP_CLASSIFICATION_UPDATED, lambda payload: updated.append(payload))
    bus.subscribe(SETUP_CLASSIFICATION_PARTIAL, lambda payload: partial.append(payload))
    item = setup_engine(bus)
    fusion, state = setup_inputs()
    fresh_fusion = replace(fusion, timestamp=NOW + timedelta(minutes=6), source_fingerprint="fresh-fusion")

    first = item.process(fusion, state, timestamp=NOW)
    stale = item.process(fresh_fusion, state, timestamp=NOW + timedelta(minutes=6))

    assert first.primary_setup is ExpertSetup.TREND_DAY
    assert stale.primary_setup is ExpertSetup.NO_QUALITY_SETUP
    assert stale is not first
    assert updated == [first]
    assert partial == [stale]
    assert item.snapshot().classification_count == 2


def test_near_identical_inputs_do_not_oscillate_breakout_to_failed_breakout():
    item = setup_engine()
    trend_fusion, trend_state = setup_inputs()
    breakout_fusion = replace(
        trend_fusion,
        evidence_conflict=EvidenceConflict.MINOR,
        evidence_agreement=EvidenceAgreement.PARTIAL_ALIGNMENT,
        conflicting_timeframes=("1m",),
        source_fingerprint="breakout-fusion",
    )
    breakout_state = replace(
        trend_state,
        market_state=MarketState.TRANSITION,
        market_stability=MarketStability.CHANGING,
        source_fingerprint="breakout-state",
    )
    noisy_failed_fusion = replace(
        breakout_fusion,
        evidence_conflict=EvidenceConflict.MAJOR,
        conflict_score=20.0,
        source_fingerprint="noisy-failed-fusion",
    )
    noisy_failed_state = replace(
        breakout_state,
        market_state=MarketState.VOLATILE,
        market_stability=MarketStability.UNSTABLE,
        volatility_state=VolatilityState.VOLATILE,
        source_fingerprint="noisy-failed-state",
    )

    first = item.process(breakout_fusion, breakout_state, timestamp=NOW)
    second = item.process(noisy_failed_fusion, noisy_failed_state, timestamp=NOW + timedelta(seconds=1))
    third = item.process(breakout_fusion, breakout_state, timestamp=NOW + timedelta(seconds=2))
    fourth = item.process(noisy_failed_fusion, noisy_failed_state, timestamp=NOW + timedelta(seconds=3))

    assert first.primary_setup is ExpertSetup.BREAKOUT
    assert second.primary_setup is ExpertSetup.BREAKOUT
    assert third.primary_setup is ExpertSetup.BREAKOUT
    assert fourth.primary_setup is ExpertSetup.BREAKOUT


def test_material_strong_conflict_changes_setup_to_failed_breakout():
    item = setup_engine()
    trend_fusion, trend_state = setup_inputs()
    breakout_fusion = replace(
        trend_fusion,
        evidence_conflict=EvidenceConflict.MINOR,
        evidence_agreement=EvidenceAgreement.PARTIAL_ALIGNMENT,
        conflicting_timeframes=("1m",),
        source_fingerprint="breakout-fusion",
    )
    breakout_state = replace(
        trend_state,
        market_state=MarketState.TRANSITION,
        market_stability=MarketStability.CHANGING,
        source_fingerprint="breakout-state",
    )
    material_fusion = replace(
        breakout_fusion,
        evidence_conflict=EvidenceConflict.MAJOR,
        conflict_score=60.0,
        source_fingerprint="material-fusion",
    )
    material_state = replace(
        breakout_state,
        market_state=MarketState.VOLATILE,
        market_stability=MarketStability.UNSTABLE,
        volatility_state=VolatilityState.VOLATILE,
        source_fingerprint="material-state",
    )

    first = item.process(breakout_fusion, breakout_state, timestamp=NOW)
    second = item.process(material_fusion, material_state, timestamp=NOW + timedelta(seconds=1))

    assert first.primary_setup is ExpertSetup.BREAKOUT
    assert second.primary_setup is ExpertSetup.FAILED_BREAKOUT


def test_primary_setup_exclusivity_prevents_impossible_combinations():
    trend_fusion, trend_state = setup_inputs()
    trend = classify(trend_fusion, trend_state)
    range_fusion, range_state = setup_inputs((MarketBias.NEUTRAL, MarketBias.NEUTRAL))
    range_day = classify(range_fusion, range_state)
    breakout_fusion = replace(
        trend_fusion,
        evidence_conflict=EvidenceConflict.MINOR,
        evidence_agreement=EvidenceAgreement.PARTIAL_ALIGNMENT,
        conflicting_timeframes=("1m",),
        source_fingerprint="breakout-fusion",
    )
    breakout_state = replace(
        trend_state,
        market_state=MarketState.TRANSITION,
        market_stability=MarketStability.CHANGING,
        source_fingerprint="breakout-state",
    )
    breakout = classify(breakout_fusion, breakout_state)
    failed = classify(
        replace(breakout_fusion, evidence_conflict=EvidenceConflict.MAJOR, source_fingerprint="failed-fusion"),
        replace(
            breakout_state,
            market_state=MarketState.VOLATILE,
            market_stability=MarketStability.UNSTABLE,
            volatility_state=VolatilityState.VOLATILE,
            source_fingerprint="failed-state",
        ),
    )

    assert trend.primary_setup is ExpertSetup.TREND_DAY
    assert trend.secondary_setup is not ExpertSetup.RANGE_DAY
    assert range_day.primary_setup is ExpertSetup.RANGE_DAY
    assert range_day.secondary_setup is not ExpertSetup.TREND_DAY
    assert breakout.primary_setup is ExpertSetup.BREAKOUT
    assert breakout.secondary_setup is not ExpertSetup.FAILED_BREAKOUT
    assert failed.primary_setup is ExpertSetup.FAILED_BREAKOUT
    assert failed.secondary_setup is not ExpertSetup.BREAKOUT


def test_invalid_input_and_unexpected_failure_publish_canonical_events(monkeypatch):
    bus = EventBus()
    invalid = []
    failed = []
    bus.subscribe(SETUP_CLASSIFICATION_INVALID, lambda payload: invalid.append(payload))
    bus.subscribe(SETUP_CLASSIFICATION_FAILED, lambda payload: failed.append(payload))
    item = setup_engine(bus)
    fusion, state = setup_inputs()

    with pytest.raises(TypeError):
        item.process(object(), state, timestamp=NOW)

    assert item.snapshot().invalid_count == 1
    assert invalid[0].invalid_count == 1
    assert item.snapshot().lifecycle_state is SetupClassificationLifecycle.READY

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("engines.expert_setup_classification.engine._primary_setup", fail)
    with pytest.raises(RuntimeError):
        item.process(fusion, state, timestamp=NOW)

    assert item.snapshot().failed_count == 1
    assert item.snapshot().lifecycle_state is SetupClassificationLifecycle.FAILED
    assert failed[0].failed_count == 1


def test_runtime_integrates_one_setup_classification_engine_after_market_state():
    bus = EventBus()
    partial = []
    bus.subscribe(SETUP_CLASSIFICATION_PARTIAL, lambda payload: partial.append(payload))
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

    snapshot = runtime.snapshot().setup_classification
    assert runtime.setup_classification_engine is runtime.setup_classification_engine
    assert snapshot.classification_count == 1
    assert snapshot.last_snapshot is not None
    assert snapshot.last_snapshot.instrument is RuntimeInstrument.NIFTY
    assert partial == [snapshot.last_snapshot]


def test_setup_classification_consumes_only_fusion_and_market_state():
    source = "engines/expert_setup_classification/engine.py"
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
