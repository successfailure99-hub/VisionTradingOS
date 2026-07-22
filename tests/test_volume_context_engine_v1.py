from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.event_bus import EventBus
from core.events import (
    TRADINGVIEW_EVIDENCE_MAPPED,
    VOLUME_CONTEXT_FAILED,
    VOLUME_CONTEXT_INVALID,
    VOLUME_CONTEXT_PARTIAL,
    VOLUME_CONTEXT_UPDATED,
)
from core.models.candle import Candle
from engines.tradingview_evidence import EvidenceAvailability, TradingViewEvidenceMappingEngine
from engines.tradingview_evidence.models import TradingViewEvidenceRequest
from engines.volume_context import (
    VolumeContextEngine,
    VolumeContextProfile,
    VolumeContextSnapshot,
    VolumeDirection,
    VolumeExhaustionState,
    VolumeExpansionState,
    VolumeStrength,
)
import engines.volume_context.engine as volume_engine_module
from tests.test_tradingview_evidence_mapping_engine_v1 import (
    NOW,
    camarilla,
    candle as evidence_candle,
    cpr,
    market_context,
    option_chain,
    price_action,
    vwap,
)


START = NOW - timedelta(minutes=21)


def make_candle(
    index: int,
    volume: int,
    *,
    close: float = 100.0,
    timeframe: str = "1m",
    symbol: str = "NIFTY",
) -> Candle:
    start = START + timedelta(minutes=index)
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        start_time=start,
        end_time=start + timedelta(minutes=1),
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=volume,
    )


def candles_from_volumes(
    volumes: list[int],
    *,
    timeframe: str = "1m",
    symbol: str = "NIFTY",
) -> tuple[Candle, ...]:
    return tuple(make_candle(index, volume, timeframe=timeframe, symbol=symbol) for index, volume in enumerate(volumes))


def warm_engine(engine: VolumeContextEngine, candles: tuple[Candle, ...]) -> VolumeContextSnapshot:
    result = None
    for item in candles:
        try:
            result = engine.process(item)
        except ValueError as exc:
            if "Insufficient candle history" not in str(exc):
                raise
    assert result is not None
    return result


def test_average_volume_relative_volume_and_events_are_deterministic():
    bus = EventBus()
    updates = []
    bus.subscribe(VOLUME_CONTEXT_UPDATED, updates.append)
    engine = VolumeContextEngine(bus, instrument="NIFTY", timeframe="1m")

    result = warm_engine(engine, candles_from_volumes([1000] * 20 + [1500]))

    assert result.lookback == 20
    assert result.average_volume == pytest.approx(1000.0)
    assert result.current_volume == 1500
    assert result.relative_volume == pytest.approx(1.5)
    assert result.volume_direction is VolumeDirection.INCREASING
    assert result.volume_strength is VolumeStrength.HIGH
    assert result.volume_expansion_state is VolumeExpansionState.EXPANDING
    assert result.volume_exhaustion_state is VolumeExhaustionState.NORMAL
    assert engine.state is result
    assert engine.snapshot().calculation_count == 1
    assert updates == [result]


@pytest.mark.parametrize(
    ("last_two", "expected"),
    (
        ([1000, 1100], VolumeDirection.INCREASING),
        ([1000, 900], VolumeDirection.DECREASING),
        ([1000, 1050], VolumeDirection.STABLE),
        ([1000, 950], VolumeDirection.STABLE),
    ),
)
def test_direction_transitions_respect_stability_threshold(last_two, expected):
    volumes = [1000] * 19 + last_two

    result = warm_engine(VolumeContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"), candles_from_volumes(volumes))

    assert result.volume_direction is expected


@pytest.mark.parametrize(
    ("current_volume", "strength", "expansion", "exhaustion"),
    (
        (700, VolumeStrength.LOW, VolumeExpansionState.COMPRESSED, VolumeExhaustionState.NORMAL),
        (1000, VolumeStrength.NORMAL, VolumeExpansionState.NORMAL, VolumeExhaustionState.NORMAL),
        (1600, VolumeStrength.HIGH, VolumeExpansionState.EXPANDING, VolumeExhaustionState.NORMAL),
        (2600, VolumeStrength.EXTREME, VolumeExpansionState.CLIMACTIC, VolumeExhaustionState.EXHAUSTED),
    ),
)
def test_strength_expansion_and_exhaustion_states(current_volume, strength, expansion, exhaustion):
    result = warm_engine(
        VolumeContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"),
        candles_from_volumes([1000] * 20 + [current_volume]),
    )

    assert result.volume_strength is strength
    assert result.volume_expansion_state is expansion
    assert result.volume_exhaustion_state is exhaustion


def test_configurable_lookback_allows_future_profiles_without_code_changes():
    profile = VolumeContextProfile(lookback=5)
    engine = VolumeContextEngine(EventBus(), instrument="NIFTY", timeframe="1m", profile=profile)

    result = warm_engine(engine, candles_from_volumes([100, 200, 300, 400, 500, 600]))

    assert engine.lookback == 5
    assert result.lookback == 5
    assert result.average_volume == pytest.approx(300.0)
    assert result.relative_volume == pytest.approx(2.0)


def test_invalid_and_insufficient_history_publish_contract_events():
    bus = EventBus()
    partial = []
    invalid = []
    bus.subscribe(VOLUME_CONTEXT_PARTIAL, partial.append)
    bus.subscribe(VOLUME_CONTEXT_INVALID, invalid.append)
    engine = VolumeContextEngine(bus, instrument="NIFTY", timeframe="1m")

    with pytest.raises(ValueError, match="Insufficient candle history"):
        engine.process(make_candle(0, 1000))
    assert partial == [engine.snapshot()]
    assert engine.state is None

    with pytest.raises(ValueError, match="non-negative integer"):
        engine.process(make_candle(1, -1))
    assert invalid[-1] == engine.snapshot()
    assert engine.state is None


def test_zero_reference_average_is_invalid_not_failed():
    bus = EventBus()
    invalid = []
    failed = []
    bus.subscribe(VOLUME_CONTEXT_INVALID, invalid.append)
    bus.subscribe(VOLUME_CONTEXT_FAILED, failed.append)
    engine = VolumeContextEngine(bus, instrument="NIFTY", timeframe="1m")

    with pytest.raises(ValueError, match="Average volume"):
        warm_engine(engine, candles_from_volumes([0] * 20 + [100]))

    assert invalid[-1] == engine.snapshot()
    assert failed == []
    assert engine.state is None


def test_gap_candle_history_is_accepted_without_calendar_continuity_requirement():
    engine = VolumeContextEngine(EventBus(), instrument="NIFTY", timeframe="1m")
    history = list(candles_from_volumes([1000] * 20))
    gap_candle = replace(make_candle(60, 2000), open=120.0, high=121.0, low=119.0, close=120.0)
    history.append(gap_candle)

    result = warm_engine(engine, tuple(history))

    assert result.timestamp == gap_candle.end_time
    assert result.relative_volume == pytest.approx(2.0)
    assert engine.candle_count == 21


def test_overlapping_candle_is_rejected_as_invalid_history_rewrite():
    bus = EventBus()
    invalid = []
    bus.subscribe(VOLUME_CONTEXT_INVALID, invalid.append)
    engine = VolumeContextEngine(bus, instrument="NIFTY", timeframe="1m")
    history = candles_from_volumes([1000] * 21)
    warm_engine(engine, history)
    latest = history[-1]
    overlapping = replace(
        make_candle(21, 1300),
        start_time=latest.end_time - timedelta(seconds=30),
        end_time=latest.end_time + timedelta(seconds=30),
    )

    with pytest.raises(ValueError, match="Overlapping volume candle"):
        engine.process(overlapping)

    assert invalid[-1] == engine.snapshot()
    assert engine.snapshot().invalid_count == 1
    assert engine.candle_count == 21


def test_stale_candle_is_rejected_as_invalid_history_rewrite():
    bus = EventBus()
    invalid = []
    bus.subscribe(VOLUME_CONTEXT_INVALID, invalid.append)
    engine = VolumeContextEngine(bus, instrument="NIFTY", timeframe="1m")
    history = candles_from_volumes([1000] * 21)
    warm_engine(engine, history)

    with pytest.raises(ValueError, match="Stale volume candle"):
        engine.process(history[-2])

    assert invalid[-1] == engine.snapshot()
    assert engine.snapshot().invalid_count == 1
    assert engine.candle_count == 21


def test_same_end_time_correction_replaces_latest_candle_without_growing_history():
    bus = EventBus()
    updates = []
    bus.subscribe(VOLUME_CONTEXT_UPDATED, updates.append)
    engine = VolumeContextEngine(bus, instrument="NIFTY", timeframe="1m")
    history = candles_from_volumes([1000] * 21)
    first = warm_engine(engine, history)
    corrected = replace(history[-1], volume=2500)

    second = engine.process(corrected)

    assert second is not first
    assert engine.state is second
    assert engine.candle_count == 21
    assert engine.snapshot().calculation_count == 2
    assert updates == [first, second]
    assert second.current_volume == 2500


def test_same_end_time_correction_cannot_overlap_previous_finalized_candle():
    bus = EventBus()
    invalid = []
    bus.subscribe(VOLUME_CONTEXT_INVALID, invalid.append)
    engine = VolumeContextEngine(
        bus,
        instrument="NIFTY",
        timeframe="5m",
        profile=VolumeContextProfile(lookback=1),
    )
    previous = Candle(
        symbol="NIFTY",
        timeframe="5m",
        start_time=NOW.replace(hour=9, minute=15, second=0, microsecond=0),
        end_time=NOW.replace(hour=9, minute=20, second=0, microsecond=0),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1000,
    )
    latest = Candle(
        symbol="NIFTY",
        timeframe="5m",
        start_time=NOW.replace(hour=9, minute=20, second=0, microsecond=0),
        end_time=NOW.replace(hour=9, minute=25, second=0, microsecond=0),
        open=101.0,
        high=102.0,
        low=100.0,
        close=101.0,
        volume=1000,
    )
    malformed_replacement = Candle(
        symbol="NIFTY",
        timeframe="5m",
        start_time=NOW.replace(hour=9, minute=18, second=0, microsecond=0),
        end_time=latest.end_time,
        open=102.0,
        high=103.0,
        low=101.0,
        close=102.0,
        volume=1200,
    )
    first = warm_engine(engine, (previous, latest))

    with pytest.raises(ValueError, match="Overlapping volume candle"):
        engine.process(malformed_replacement)

    assert invalid[-1] == engine.snapshot()
    assert engine.candle_count == 2
    assert engine.state is first
    assert engine.snapshot().invalid_count == 1
    assert engine.snapshot().calculation_count == 1


def test_snapshot_is_immutable_and_duplicate_candle_is_idempotent():
    bus = EventBus()
    updates = []
    bus.subscribe(VOLUME_CONTEXT_UPDATED, updates.append)
    engine = VolumeContextEngine(bus, instrument="NIFTY", timeframe="1m")
    history = candles_from_volumes([1000] * 21)
    first = warm_engine(engine, history)

    second = engine.process(history[-1])

    assert second is first
    assert engine.snapshot().calculation_count == 1
    assert updates == [first]
    with pytest.raises(FrozenInstanceError):
        first.relative_volume = 1.0


def test_unexpected_failure_publishes_failed_event(monkeypatch):
    bus = EventBus()
    failed = []
    bus.subscribe(VOLUME_CONTEXT_FAILED, failed.append)
    engine = VolumeContextEngine(bus, instrument="NIFTY", timeframe="1m")

    def fail_snapshot(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(volume_engine_module, "VolumeContextSnapshot", fail_snapshot)

    with pytest.raises(RuntimeError, match="boom"):
        warm_engine(engine, candles_from_volumes([1000] * 21))

    assert engine.state is None
    assert failed[-1] == engine.snapshot()


def test_runtime_creates_one_volume_context_engine_per_timeframe_lane():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m", "15m", "30m")),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    assert tuple(runtime.volume_context_engines) == (
        TimeFrame.ONE_MINUTE,
        TimeFrame.FIVE_MINUTES,
        TimeFrame.FIFTEEN_MINUTES,
        TimeFrame.THIRTY_MINUTES,
    )
    assert runtime.volume_context_engine is runtime.volume_context_engines[TimeFrame.ONE_MINUTE]
    assert len({id(engine) for engine in runtime.volume_context_engines.values()}) == 4
    assert orchestrator.market_data_engine is orchestrator.market_data_engine


def test_runtime_warm_up_updates_primary_volume_context_without_breaking_legacy_timeframe():
    orchestrator = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(timeframe="1m"))
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    runtime.warm_up_candles(candles_from_volumes([1000] * 20 + [1500]), replace=True)
    snapshot = runtime.snapshot()

    assert snapshot.timeframe == "1m"
    assert snapshot.volume_context is runtime.volume_context_engine.state
    assert snapshot.volume_context is not None
    assert snapshot.volume_context_diagnostics.calculation_count == 1


def test_multi_timeframe_volume_context_lanes_are_isolated():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m")),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    one_minute = warm_engine(
        runtime.volume_context_engines[TimeFrame.ONE_MINUTE],
        candles_from_volumes([1000] * 20 + [2000], timeframe="1m"),
    )
    five_minute = warm_engine(
        runtime.volume_context_engines[TimeFrame.FIVE_MINUTES],
        candles_from_volumes([2000] * 20 + [1000], timeframe="5m"),
    )

    assert one_minute.volume_direction is VolumeDirection.INCREASING
    assert five_minute.volume_direction is VolumeDirection.DECREASING
    assert runtime.volume_context_engines[TimeFrame.ONE_MINUTE].state is one_minute
    assert runtime.volume_context_engines[TimeFrame.FIVE_MINUTES].state is five_minute


def test_tradingview_evidence_consumes_volume_context_without_calculating_it():
    bus = EventBus()
    mapped = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_MAPPED, mapped.append)
    engine = TradingViewEvidenceMappingEngine(bus, instrument="NIFTY", timeframe="1m")
    engine.start()
    volume_context = warm_engine(
        VolumeContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"),
        candles_from_volumes([1000] * 20 + [2000]),
    )

    result = engine.map_evidence(TradingViewEvidenceRequest(
        evidence_id="volume-context-evidence",
        timestamp=NOW,
        instrument=RuntimeInstrument.NIFTY,
        timeframe="1m",
        latest_price=400.0,
        latest_candle=evidence_candle(),
        camarilla=camarilla(),
        cpr=cpr(),
        vwap=vwap(),
        adr=None,
        price_action=price_action(),
        market_context=market_context(),
        option_chain=option_chain(),
        moving_average_context=None,
        momentum=None,
        volume=volume_context,
    ))

    assert result.volume_status.availability is EvidenceAvailability.AVAILABLE
    assert result.volume_observation is volume_context
    assert result.volume_context_observation is volume_context
    assert mapped == [result]
