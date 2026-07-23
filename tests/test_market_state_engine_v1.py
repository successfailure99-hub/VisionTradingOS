from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from application.orchestrator import ApplicationOrchestrator
from core.event_bus import EventBus
from core.events import (
    MARKET_STATE_FAILED,
    MARKET_STATE_INVALID,
    MARKET_STATE_PARTIAL,
    MARKET_STATE_UPDATED,
)
from engines.market_context.enums import MarketBias
from engines.market_state import (
    MarketEvidenceQuality,
    MarketPhase,
    MarketStability,
    MarketState,
    MarketStateEngine,
    MarketStateLifecycle,
    StructuralConfidence,
    VolatilityState,
)
from engines.multi_timeframe_evidence_fusion import (
    EvidenceAgreement,
    EvidenceCompleteness,
    FusionDirection,
)
from tests.test_multi_timeframe_evidence_fusion_engine_v1 import (
    complete_evidence,
    fusion_engine,
)
from tests.test_tradingview_evidence_assembly_coordinator_v1 import live_tick
from tests.test_tradingview_evidence_mapping_engine_v1 import NOW


def market_state_engine(bus=None):
    item = MarketStateEngine(bus or EventBus(), instrument=RuntimeInstrument.NIFTY)
    item.start()
    return item


def fused(biases, *, timeframes=None, timestamp=NOW):
    timeframes = timeframes or tuple(f"{index + 1}m" for index in range(len(biases)))
    normalized_timeframes = tuple("3m" if item == "2m" else item for item in timeframes)
    item = fusion_engine(timeframes=normalized_timeframes)
    evidence = tuple(
        complete_evidence(timeframe, bias=bias, timestamp=timestamp)
        for timeframe, bias in zip(normalized_timeframes, biases)
    )
    return item.fuse(evidence, timestamp=timestamp)


def test_trending_market_state_from_complete_aligned_fusion():
    bus = EventBus()
    updated = []
    bus.subscribe(MARKET_STATE_UPDATED, lambda payload: updated.append(payload))
    item = market_state_engine(bus)
    fusion = fused(
        (MarketBias.BULLISH, MarketBias.BULLISH, MarketBias.BULLISH),
        timeframes=("1m", "5m", "15m"),
    )

    result = item.process(fusion, timestamp=NOW)

    assert result.market_state is MarketState.TRENDING
    assert result.market_phase is MarketPhase.MATURE
    assert result.market_stability is MarketStability.STABLE
    assert result.volatility_state is VolatilityState.NORMAL
    assert result.evidence_quality is MarketEvidenceQuality.HIGH
    assert result.confidence_level is StructuralConfidence.HIGH_STRUCTURE
    assert result.dominant_timeframe == "15m"
    assert updated == [result]
    assert item.snapshot().updated_count == 1
    assert result.broker_order_calls == 0
    assert result.live_order_submission_enabled is False


def test_ranging_market_state_from_neutral_alignment():
    item = market_state_engine()
    fusion = fused(
        (MarketBias.NEUTRAL, MarketBias.NEUTRAL, MarketBias.NEUTRAL),
        timeframes=("1m", "5m", "15m"),
    )

    result = item.process(fusion, timestamp=NOW)

    assert result.market_state is MarketState.RANGING
    assert result.volatility_state is VolatilityState.QUIET
    assert result.market_stability is MarketStability.STABLE


def test_transition_state_from_partial_fusion():
    bus = EventBus()
    partial = []
    bus.subscribe(MARKET_STATE_PARTIAL, lambda payload: partial.append(payload))
    item = market_state_engine(bus)
    fusion = fused((MarketBias.BULLISH,), timeframes=("1m",))
    fusion = replace(
        fusion,
        evidence_completeness=EvidenceCompleteness.PARTIAL,
        missing_timeframes=("5m",),
    )

    result = item.process(fusion, timestamp=NOW)

    assert result.market_state is MarketState.TRANSITION
    assert result.market_phase is MarketPhase.DEVELOPING
    assert result.market_stability is MarketStability.CHANGING
    assert result.evidence_quality is MarketEvidenceQuality.LOW
    assert partial == [result]


def test_expansion_state_from_minor_cross_timeframe_conflict():
    item = market_state_engine()
    fusion = fused(
        (MarketBias.BULLISH, MarketBias.BULLISH, MarketBias.BEARISH),
        timeframes=("1m", "5m", "15m"),
    )

    result = item.process(fusion, timestamp=NOW)

    assert result.market_state is MarketState.EXPANSION
    assert result.market_phase is MarketPhase.DEVELOPING
    assert result.market_stability is MarketStability.CHANGING


def test_compression_quiet_volatile_and_balanced_states_are_deterministic():
    item = market_state_engine()
    base = fused(
        (MarketBias.BULLISH, MarketBias.BULLISH),
        timeframes=("1m", "5m"),
    )
    compression = replace(base, weak_timeframes=("1m",))
    quiet = replace(
        base,
        aligned_timeframes=(),
        conflicting_timeframes=(),
        weak_timeframes=("1m", "5m"),
    )
    volatile = fused(
        (MarketBias.BULLISH, MarketBias.BEARISH),
        timeframes=("1m", "5m"),
    )
    balanced = replace(base, evidence_completeness=EvidenceCompleteness.INSUFFICIENT)

    assert item.process(compression, timestamp=NOW).market_state is MarketState.COMPRESSION
    assert item.process(quiet, timestamp=NOW + timedelta(seconds=1)).market_state is MarketState.QUIET
    assert item.process(volatile, timestamp=NOW + timedelta(seconds=2)).market_state is MarketState.VOLATILE
    assert item.process(balanced, timestamp=NOW + timedelta(seconds=3)).market_state is MarketState.BALANCED


def test_missing_fusion_and_stale_fusion_publish_partial_without_exception():
    bus = EventBus()
    partial = []
    bus.subscribe(MARKET_STATE_PARTIAL, lambda payload: partial.append(payload))
    item = market_state_engine(bus)

    missing = item.process(None, timestamp=NOW)
    stale_fusion = fused(
        (MarketBias.BULLISH, MarketBias.BULLISH),
        timeframes=("1m", "5m"),
        timestamp=NOW,
    )
    stale = item.process(stale_fusion, timestamp=NOW + timedelta(minutes=6))

    assert missing.evidence_quality is MarketEvidenceQuality.INSUFFICIENT
    assert missing.market_state is MarketState.BALANCED
    assert stale.market_state is MarketState.TRANSITION
    assert stale.evidence_quality is MarketEvidenceQuality.LOW
    assert partial == [missing, stale]
    assert item.snapshot().partial_count == 2


def test_duplicate_publication_is_suppressed_and_snapshot_is_immutable():
    bus = EventBus()
    updated = []
    bus.subscribe(MARKET_STATE_UPDATED, lambda payload: updated.append(payload))
    item = market_state_engine(bus)
    fusion = fused(
        (MarketBias.BULLISH, MarketBias.BULLISH),
        timeframes=("1m", "5m"),
    )

    first = item.process(fusion, timestamp=NOW)
    second = item.process(fusion, timestamp=NOW)

    assert second is first
    assert updated == [first]
    assert item.snapshot().evaluation_count == 1
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        first.market_state = MarketState.VOLATILE


def test_same_observable_fusion_at_later_non_stale_timestamp_does_not_republish():
    bus = EventBus()
    updated = []
    bus.subscribe(MARKET_STATE_UPDATED, lambda payload: updated.append(payload))
    item = market_state_engine(bus)
    fusion = fused(
        (MarketBias.BULLISH, MarketBias.BULLISH),
        timeframes=("1m", "5m"),
    )

    first = item.process(fusion, timestamp=NOW)
    second = item.process(fusion, timestamp=NOW + timedelta(seconds=1))

    assert second is first
    assert updated == [first]
    assert item.snapshot().evaluation_count == 1
    assert item.snapshot().updated_count == 1


def test_identical_fusion_publishes_again_when_freshness_crosses_to_partial():
    bus = EventBus()
    updated = []
    partial = []
    bus.subscribe(MARKET_STATE_UPDATED, lambda payload: updated.append(payload))
    bus.subscribe(MARKET_STATE_PARTIAL, lambda payload: partial.append(payload))
    item = market_state_engine(bus)
    fusion = fused(
        (MarketBias.BULLISH, MarketBias.BULLISH),
        timeframes=("1m", "5m"),
    )

    first = item.process(fusion, timestamp=NOW)
    stale = item.process(fusion, timestamp=NOW + timedelta(minutes=6))

    assert first.market_state is MarketState.TRENDING
    assert stale is not first
    assert stale.market_state is MarketState.TRANSITION
    assert stale.evidence_quality is MarketEvidenceQuality.LOW
    assert updated == [first]
    assert partial == [stale]
    assert item.snapshot().evaluation_count == 2


def test_near_identical_fusion_fluctuation_does_not_oscillate_market_state():
    bus = EventBus()
    updated = []
    bus.subscribe(MARKET_STATE_UPDATED, lambda payload: updated.append(payload))
    item = market_state_engine(bus)
    trend = fused(
        (MarketBias.BULLISH, MarketBias.BULLISH),
        timeframes=("1m", "5m"),
    )
    tiny_fluctuation = replace(trend, evidence_agreement=EvidenceAgreement.MIXED)

    first = item.process(trend, timestamp=NOW)
    second = item.process(tiny_fluctuation, timestamp=NOW + timedelta(seconds=1))
    third = item.process(trend, timestamp=NOW + timedelta(seconds=2))
    fourth = item.process(tiny_fluctuation, timestamp=NOW + timedelta(seconds=3))

    assert first.market_state is MarketState.TRENDING
    assert second is first
    assert third is first
    assert fourth is first
    assert updated == [first]
    assert item.snapshot().evaluation_count == 1


def test_material_fusion_change_updates_market_state_reproducibly():
    item = market_state_engine()
    trend = fused(
        (MarketBias.BULLISH, MarketBias.BULLISH),
        timeframes=("1m", "5m"),
    )
    strong_conflict = fused(
        (MarketBias.BULLISH, MarketBias.BEARISH),
        timeframes=("1m", "5m"),
    )

    first = item.process(trend, timestamp=NOW)
    second = item.process(strong_conflict, timestamp=NOW + timedelta(seconds=1))
    repeated = market_state_engine().process(strong_conflict, timestamp=NOW + timedelta(seconds=1))

    assert first.market_state is MarketState.TRENDING
    assert second.market_state is MarketState.VOLATILE
    assert second.market_phase is repeated.market_phase
    assert second.market_stability is repeated.market_stability
    assert second.volatility_state is repeated.volatility_state
    assert second.evidence_quality is repeated.evidence_quality


def test_invalid_input_publishes_invalid_and_preserves_lifecycle_recovery():
    bus = EventBus()
    invalid = []
    bus.subscribe(MARKET_STATE_INVALID, lambda payload: invalid.append(payload))
    item = market_state_engine(bus)

    with pytest.raises(TypeError):
        item.process(object(), timestamp=NOW)

    assert item.snapshot().invalid_count == 1
    assert len(invalid) == 1
    assert invalid[0].invalid_count == 1
    assert item.snapshot().lifecycle_state is MarketStateLifecycle.READY
    valid = item.process(
        fused((MarketBias.BULLISH, MarketBias.BULLISH), timeframes=("1m", "5m")),
        timestamp=NOW,
    )
    assert valid.market_state is MarketState.TRENDING
    assert item.snapshot().lifecycle_state is MarketStateLifecycle.ACTIVE


def test_unexpected_failure_publishes_failed_event(monkeypatch):
    bus = EventBus()
    failed = []
    bus.subscribe(MARKET_STATE_FAILED, lambda payload: failed.append(payload))
    item = market_state_engine(bus)

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("engines.market_state.engine._market_state", fail)

    with pytest.raises(RuntimeError):
        item.process(
            fused((MarketBias.BULLISH, MarketBias.BULLISH), timeframes=("1m", "5m")),
            timestamp=NOW,
        )

    assert item.snapshot().failed_count == 1
    assert item.snapshot().lifecycle_state is MarketStateLifecycle.FAILED
    assert len(failed) == 1
    assert failed[0].failed_count == 1


def test_runtime_integrates_one_market_state_engine_per_instrument_after_fusion():
    bus = EventBus()
    partial = []
    bus.subscribe(MARKET_STATE_PARTIAL, lambda payload: partial.append(payload))
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

    snapshot = runtime.snapshot().market_state
    assert runtime.market_state_engine is runtime.market_state_engine
    assert snapshot.evaluation_count == 1
    assert snapshot.last_snapshot is not None
    assert snapshot.last_snapshot.instrument is RuntimeInstrument.NIFTY
    assert partial == [snapshot.last_snapshot]


def test_market_state_engine_consumes_fusion_only_and_has_no_indicator_calculations():
    source = "engines/market_state/engine.py"
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
        "BUY",
        "SELL",
        "ENTRY",
        "EXIT",
    )
    assert all(term not in text for term in forbidden)
