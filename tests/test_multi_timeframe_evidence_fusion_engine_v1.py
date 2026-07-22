from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from application.orchestrator import ApplicationOrchestrator
from core.event_bus import EventBus
from core.events import (
    MULTI_TIMEFRAME_EVIDENCE_PARTIAL,
    MULTI_TIMEFRAME_EVIDENCE_UPDATED,
)
from engines.adr.enums import ADRExhaustionState, ADRExpansionState
from engines.adr.models import ADRSnapshot
from engines.market_context.enums import EvidenceDirection, MarketBias
from engines.momentum_context.enums import (
    MomentumAcceleration,
    MomentumDirection,
    MomentumState,
    MomentumStrength,
)
from engines.momentum_context.models import MomentumContextSnapshot
from engines.moving_average_context.enums import (
    MovingAverageAlignment,
    MovingAverageCompressionState,
    MovingAverageExpansionState,
    MovingAverageSlope,
)
from engines.moving_average_context.models import MovingAverageContextSnapshot
from engines.multi_timeframe_evidence_fusion import (
    EvidenceAgreement,
    EvidenceCompleteness,
    EvidenceConflict,
    FusionDirection,
    MultiTimeframeEvidenceFusionEngine,
    MultiTimeframeEvidenceSnapshot,
)
from engines.tradingview_evidence import TradingViewEvidenceMappingEngine
from engines.volume_context.enums import (
    VolumeDirection,
    VolumeExhaustionState,
    VolumeExpansionState,
    VolumeStrength,
)
from engines.volume_context.models import VolumeContextSnapshot

from tests.test_tradingview_evidence_assembly_coordinator_v1 import live_tick
from tests.test_tradingview_evidence_mapping_engine_v1 import (
    NOW,
    candle,
    market_context,
    option_chain,
    price_action,
    request,
    vwap,
)


def complete_evidence(
    timeframe: str,
    *,
    bias: MarketBias = MarketBias.BULLISH,
    timestamp=NOW,
    source_timestamp=None,
):
    source_time = source_timestamp or timestamp
    context = replace(
        market_context(),
        timeframe=timeframe,
        timestamp=source_time,
        market_bias=bias,
        price_action_direction=_evidence_direction(bias),
    )
    action = replace(price_action(), timeframe=timeframe, updated_at=source_time)
    chain = replace(option_chain(), timestamp=source_time)
    item = TradingViewEvidenceMappingEngine(EventBus(), instrument="NIFTY", timeframe=timeframe)
    item.start()
    return item.map_evidence(
        request(
            evidence_id=f"evidence-{timeframe}",
            timestamp=timestamp,
            timeframe=timeframe,
            latest_candle=candle(end_time=source_time),
            vwap=vwap(timestamp=source_time),
            price_action=action,
            market_context=context,
            option_chain=chain,
            adr=adr(source_time),
            moving_average_context=moving_average(timeframe, source_time),
            momentum=momentum(timeframe, source_time),
            volume=volume(timeframe, source_time),
            correlation_id=f"corr-{timeframe}",
        )
    )


def adr(timestamp=NOW):
    return ADRSnapshot(
        trading_date=timestamp.date(),
        instrument="NIFTY",
        adr_period=20,
        adr_value=100.0,
        today_high=120.0,
        today_low=80.0,
        today_range=40.0,
        adr_high=150.0,
        adr_low=50.0,
        range_consumed_pct=40.0,
        range_remaining_pct=60.0,
        expansion_state=ADRExpansionState.NORMAL,
        exhaustion_state=ADRExhaustionState.NOT_EXHAUSTED,
        timestamp=timestamp,
    )


def moving_average(timeframe: str, timestamp=NOW):
    return MovingAverageContextSnapshot(
        trading_date=timestamp.date(),
        instrument="NIFTY",
        timeframe=timeframe,
        ema20=101.0,
        ema50=100.0,
        ema200=99.0,
        price_above_ema20=True,
        price_above_ema50=True,
        price_above_ema200=True,
        ema_alignment=MovingAverageAlignment.STRONG_BULLISH,
        ema_slope=MovingAverageSlope.RISING,
        compression_state=MovingAverageCompressionState.NORMAL,
        expansion_state=MovingAverageExpansionState.EXPANDING,
        timestamp=timestamp,
    )


def momentum(timeframe: str, timestamp=NOW):
    return MomentumContextSnapshot(
        trading_date=timestamp.date(),
        instrument="NIFTY",
        timeframe=timeframe,
        momentum_period=14,
        momentum_value=1.25,
        momentum_direction=MomentumDirection.RISING,
        momentum_strength=MomentumStrength.STRONG,
        momentum_acceleration=MomentumAcceleration.ACCELERATING,
        momentum_state=MomentumState.ACCELERATING,
        timestamp=timestamp,
    )


def volume(timeframe: str, timestamp=NOW):
    return VolumeContextSnapshot(
        trading_date=timestamp.date(),
        instrument="NIFTY",
        timeframe=timeframe,
        lookback=20,
        average_volume=1000.0,
        current_volume=1500,
        relative_volume=1.5,
        volume_direction=VolumeDirection.INCREASING,
        volume_strength=VolumeStrength.HIGH,
        volume_expansion_state=VolumeExpansionState.EXPANDING,
        volume_exhaustion_state=VolumeExhaustionState.NORMAL,
        timestamp=timestamp,
    )


def _evidence_direction(bias: MarketBias):
    if bias is MarketBias.BULLISH:
        return EvidenceDirection.BULLISH
    if bias is MarketBias.BEARISH:
        return EvidenceDirection.BEARISH
    if bias is MarketBias.NEUTRAL:
        return EvidenceDirection.NEUTRAL
    return EvidenceDirection.UNKNOWN


def fusion_engine(bus=None, timeframes=("1m", "5m", "15m")):
    item = MultiTimeframeEvidenceFusionEngine(
        bus or EventBus(),
        instrument=RuntimeInstrument.NIFTY,
        expected_timeframes=timeframes,
    )
    item.start()
    return item


def test_all_timeframes_agree_publishes_complete_immutable_snapshot():
    bus = EventBus()
    updated = []
    bus.subscribe(MULTI_TIMEFRAME_EVIDENCE_UPDATED, lambda payload: updated.append(payload))
    item = fusion_engine(bus)

    result = item.fuse(
        (
            complete_evidence("1m", bias=MarketBias.BULLISH),
            complete_evidence("5m", bias=MarketBias.BULLISH),
            complete_evidence("15m", bias=MarketBias.BULLISH),
        ),
        timestamp=NOW,
    )

    assert isinstance(result, MultiTimeframeEvidenceSnapshot)
    assert result.evidence_agreement is EvidenceAgreement.FULL_ALIGNMENT
    assert result.evidence_conflict is EvidenceConflict.NONE
    assert result.evidence_completeness is EvidenceCompleteness.COMPLETE
    assert result.dominant_timeframe == "15m"
    assert result.alignment_score == 100.0
    assert result.conflict_score == 0.0
    assert result.aligned_timeframes == ("1m", "5m", "15m")
    assert updated == [result]
    assert item.snapshot().updated_count == 1
    assert result.broker_order_calls == 0
    assert result.live_order_submission_enabled is False
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.alignment_score = 0.0


def test_one_timeframe_conflicts_without_calculating_indicators():
    item = fusion_engine(timeframes=("1m", "5m", "15m"))

    result = item.fuse(
        (
            complete_evidence("1m", bias=MarketBias.BULLISH),
            complete_evidence("5m", bias=MarketBias.BULLISH),
            complete_evidence("15m", bias=MarketBias.BEARISH),
        ),
        timestamp=NOW,
    )

    assert result.evidence_agreement is EvidenceAgreement.PARTIAL_ALIGNMENT
    assert result.evidence_conflict is EvidenceConflict.MINOR
    assert result.dominant_timeframe == "5m"
    assert result.aligned_timeframes == ("1m", "5m")
    assert result.conflicting_timeframes == ("15m",)
    assert result.strategy_calls == 0
    assert result.risk_calls == 0


def test_missing_timeframe_and_missing_evidence_publish_partial():
    bus = EventBus()
    partial = []
    bus.subscribe(MULTI_TIMEFRAME_EVIDENCE_PARTIAL, lambda payload: partial.append(payload))
    item = fusion_engine(bus, timeframes=("1m", "5m", "15m"))
    incomplete = complete_evidence("1m", bias=MarketBias.NEUTRAL)

    result = item.fuse((incomplete,), timestamp=NOW)

    assert result.evidence_completeness is EvidenceCompleteness.PARTIAL
    assert result.evidence_agreement is EvidenceAgreement.PARTIAL_ALIGNMENT
    assert result.missing_timeframes == ("5m", "15m")
    assert partial == [result]
    assert item.snapshot().partial_count == 1


def test_stale_evidence_is_partial_and_not_fabricated_as_complete():
    stale = complete_evidence("1m", bias=MarketBias.BULLISH, source_timestamp=NOW - timedelta(minutes=10))
    fresh = complete_evidence("5m", bias=MarketBias.BULLISH)
    item = fusion_engine(timeframes=("1m", "5m"))

    result = item.fuse((stale, fresh), timestamp=NOW)

    assert result.evidence_completeness is EvidenceCompleteness.PARTIAL
    assert result.stale_timeframes == ("1m",)
    assert "1m" in result.weak_timeframes


def test_duplicate_publication_is_suppressed_and_output_is_deterministic():
    bus = EventBus()
    updated = []
    bus.subscribe(MULTI_TIMEFRAME_EVIDENCE_UPDATED, lambda payload: updated.append(payload))
    item = fusion_engine(bus, timeframes=("1m", "5m"))
    evidence = (
        complete_evidence("1m", bias=MarketBias.BULLISH),
        complete_evidence("5m", bias=MarketBias.BULLISH),
    )

    first = item.fuse(evidence, timestamp=NOW)
    second = item.fuse(evidence, timestamp=NOW)

    assert first is second
    assert first.source_fingerprint == second.source_fingerprint
    assert updated == [first]
    assert item.snapshot().fusion_count == 1


def test_permutation_invariance_forward_reverse_order_snapshot_fingerprint_and_publication():
    timeframes = ("1m", "5m", "15m", "30m", "1D")
    forward_evidence = tuple(complete_evidence(timeframe, bias=MarketBias.BULLISH) for timeframe in timeframes)
    reverse_evidence = tuple(reversed(forward_evidence))
    forward_bus = EventBus()
    reverse_bus = EventBus()
    forward_events = []
    reverse_events = []
    forward_bus.subscribe(MULTI_TIMEFRAME_EVIDENCE_UPDATED, lambda payload: forward_events.append(payload))
    reverse_bus.subscribe(MULTI_TIMEFRAME_EVIDENCE_UPDATED, lambda payload: reverse_events.append(payload))
    forward_engine = fusion_engine(forward_bus, timeframes=timeframes)
    reverse_engine = fusion_engine(reverse_bus, timeframes=timeframes)

    forward = forward_engine.fuse(forward_evidence, timestamp=NOW)
    reverse = reverse_engine.fuse(reverse_evidence, timestamp=NOW)
    duplicate = forward_engine.fuse(reverse_evidence, timestamp=NOW)

    assert forward == reverse
    assert forward.source_fingerprint == reverse.source_fingerprint
    assert duplicate is forward
    assert forward_events == [forward]
    assert reverse_events == [reverse]
    assert forward_engine.snapshot().fusion_count == 1
    assert reverse_engine.snapshot().fusion_count == 1


def test_five_lane_conflict_classification_is_reproducible():
    item = fusion_engine(timeframes=("1m", "5m", "15m", "30m", "1D"))

    result = item.fuse(
        (
            complete_evidence("1m", bias=MarketBias.BULLISH),
            complete_evidence("5m", bias=MarketBias.BULLISH),
            complete_evidence("15m", bias=MarketBias.BEARISH),
            complete_evidence("30m", bias=MarketBias.BEARISH),
            complete_evidence("1D", bias=MarketBias.BULLISH),
        ),
        timestamp=NOW,
    )

    assert result.evidence_agreement is EvidenceAgreement.PARTIAL_ALIGNMENT
    assert result.evidence_conflict is EvidenceConflict.MINOR
    assert result.dominant_timeframe == "1D"
    assert result.aligned_timeframes == ("1m", "5m", "1D")
    assert result.conflicting_timeframes == ("15m", "30m")
    assert result.alignment_score == 60.0
    assert result.conflict_score == 40.0


def test_complete_lane_that_ages_before_fusion_degrades_to_partial_without_exception():
    bus = EventBus()
    partial = []
    bus.subscribe(MULTI_TIMEFRAME_EVIDENCE_PARTIAL, lambda payload: partial.append(payload))
    item = fusion_engine(bus, timeframes=("1m", "5m"))
    old_complete = complete_evidence("1m", bias=MarketBias.BULLISH, timestamp=NOW)
    current_complete = complete_evidence(
        "5m",
        bias=MarketBias.BULLISH,
        timestamp=NOW + timedelta(minutes=6),
    )

    result = item.fuse((old_complete, current_complete), timestamp=NOW + timedelta(minutes=6))

    assert result.evidence_completeness is EvidenceCompleteness.PARTIAL
    assert result.stale_timeframes == ("1m",)
    assert result.summaries[0].stale_evidence == ("tradingview_evidence",)
    assert partial == [result]
    assert item.snapshot().partial_count == 1
    assert item.snapshot().invalid_count == 0


def test_invalid_input_publishes_invalid_and_preserves_previous_state():
    item = fusion_engine(timeframes=("1m",))
    first = item.fuse((complete_evidence("1m"),), timestamp=NOW)

    with pytest.raises(TypeError):
        item.fuse((object(),), timestamp=NOW)

    snapshot = item.snapshot()
    assert snapshot.invalid_count == 1
    assert snapshot.last_snapshot is first


def test_runtime_integrates_one_fusion_engine_per_instrument_after_closed_candle():
    bus = EventBus()
    partial = []
    bus.subscribe(MULTI_TIMEFRAME_EVIDENCE_PARTIAL, lambda payload: partial.append(payload))
    orchestrator = ApplicationOrchestrator(
        bus,
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.NIFTY,),
            timeframes=("1m", "5m"),
        ),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    orchestrator.warm_up_candles(RuntimeInstrument.NIFTY, ())
    orchestrator.process_tick(live_tick())
    orchestrator.process_tick(live_tick(timestamp=NOW + timedelta(minutes=1), price=101.0))

    snapshot = runtime.snapshot().multi_timeframe_evidence
    assert orchestrator.market_data_engine is orchestrator.market_data_engine
    assert set(runtime.tradingview_evidence_engines) == set(runtime.candle_engines)
    assert snapshot.fusion_count == 1
    assert snapshot.last_snapshot.evidence_completeness is EvidenceCompleteness.PARTIAL
    assert snapshot.last_snapshot.missing_timeframes == ("5m",)
    assert partial == [snapshot.last_snapshot]
