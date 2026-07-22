from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.event_bus import EventBus
from core.events import (
    MOMENTUM_CONTEXT_FAILED,
    MOMENTUM_CONTEXT_INVALID,
    MOMENTUM_CONTEXT_PARTIAL,
    MOMENTUM_CONTEXT_UPDATED,
    TRADINGVIEW_EVIDENCE_MAPPED,
)
from core.models.candle import Candle
from engines.momentum_context import (
    MomentumAcceleration,
    MomentumContextEngine,
    MomentumContextProfile,
    MomentumContextSnapshot,
    MomentumDirection,
    MomentumState,
    MomentumStrength,
)
import engines.momentum_context.engine as momentum_engine_module
from engines.tradingview_evidence import EvidenceAvailability, TradingViewEvidenceMappingEngine
from engines.tradingview_evidence.models import TradingViewEvidenceRequest
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


START = NOW - timedelta(minutes=20)


def make_candle(index: int, close: float, *, timeframe: str = "1m", symbol: str = "NIFTY") -> Candle:
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
        volume=1000 + index,
    )


def candles_from_closes(closes: list[float], *, timeframe: str = "1m", symbol: str = "NIFTY") -> tuple[Candle, ...]:
    return tuple(make_candle(index, close, timeframe=timeframe, symbol=symbol) for index, close in enumerate(closes))


def warm_engine(engine: MomentumContextEngine, candles: tuple[Candle, ...]) -> MomentumContextSnapshot:
    result = None
    for item in candles:
        try:
            result = engine.process(item)
        except ValueError as exc:
            if "Insufficient candle history" not in str(exc):
                raise
    assert result is not None
    return result


def test_momentum_calculation_known_history_and_events():
    bus = EventBus()
    updates = []
    bus.subscribe(MOMENTUM_CONTEXT_UPDATED, updates.append)
    engine = MomentumContextEngine(bus, instrument="NIFTY", timeframe="1m")

    result = warm_engine(engine, candles_from_closes([100.0 + index for index in range(15)]))

    assert result.momentum_period == 14
    assert result.momentum_value == pytest.approx(14.0)
    assert result.momentum_direction is MomentumDirection.RISING
    assert result.momentum_strength is MomentumStrength.EXTREME
    assert result.momentum_acceleration is MomentumAcceleration.STABLE
    assert result.momentum_state is MomentumState.STABLE
    assert engine.state is result
    assert engine.snapshot().calculation_count == 1
    assert updates == [result]


@pytest.mark.parametrize(
    ("closes", "expected"),
    (
        ([100.0 + index for index in range(15)], MomentumDirection.RISING),
        ([130.0 - index for index in range(15)], MomentumDirection.FALLING),
        ([100.0 for _ in range(15)], MomentumDirection.FLAT),
    ),
)
def test_direction_states_from_engine_output(closes, expected):
    result = warm_engine(MomentumContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"), candles_from_closes(closes))

    assert result.momentum_direction is expected


@pytest.mark.parametrize(
    ("final_close", "expected"),
    (
        (100.05, MomentumStrength.WEAK),
        (100.50, MomentumStrength.NORMAL),
        (101.00, MomentumStrength.STRONG),
        (102.00, MomentumStrength.EXTREME),
    ),
)
def test_strength_classification_is_deterministic(final_close, expected):
    closes = [100.0 for _ in range(14)] + [final_close]

    result = warm_engine(MomentumContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"), candles_from_closes(closes))

    assert result.momentum_strength is expected


@pytest.mark.parametrize(
    ("closes", "acceleration", "state"),
    (
        ([100.0, 100.0] + [100.0 for _ in range(12)] + [101.0, 103.0], MomentumAcceleration.ACCELERATING, MomentumState.ACCELERATING),
        ([100.0, 100.0] + [100.0 for _ in range(12)] + [103.0, 101.0], MomentumAcceleration.DECELERATING, MomentumState.DECELERATING),
        ([100.0, 100.0] + [100.0 for _ in range(12)] + [103.0, 99.0], MomentumAcceleration.DECELERATING, MomentumState.REVERSING),
        ([100.0 for _ in range(16)], MomentumAcceleration.STABLE, MomentumState.STABLE),
    ),
)
def test_acceleration_and_state_transitions_are_deterministic(closes, acceleration, state):
    result = warm_engine(MomentumContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"), candles_from_closes(closes))

    assert result.momentum_acceleration is acceleration
    assert result.momentum_state is state


def test_configurable_period_allows_future_profiles_without_code_changes():
    profile = MomentumContextProfile(period=5)
    engine = MomentumContextEngine(EventBus(), instrument="NIFTY", timeframe="1m", profile=profile)

    result = warm_engine(engine, candles_from_closes([100.0, 101.0, 102.0, 103.0, 104.0, 110.0]))

    assert engine.period == 5
    assert result.momentum_period == 5
    assert result.momentum_value == pytest.approx(10.0)


def test_invalid_and_insufficient_history_publish_contract_events():
    bus = EventBus()
    partial = []
    invalid = []
    bus.subscribe(MOMENTUM_CONTEXT_PARTIAL, partial.append)
    bus.subscribe(MOMENTUM_CONTEXT_INVALID, invalid.append)
    engine = MomentumContextEngine(bus, instrument="NIFTY", timeframe="1m")

    with pytest.raises(ValueError, match="Insufficient candle history"):
        engine.process(make_candle(0, 100.0))
    assert partial == [engine.snapshot()]
    assert engine.state is None

    with pytest.raises(ValueError, match="greater than zero"):
        engine.process(make_candle(1, -1.0))
    assert invalid[-1] == engine.snapshot()
    assert engine.state is None


def test_gap_candle_history_is_accepted_without_calendar_continuity_requirement():
    engine = MomentumContextEngine(EventBus(), instrument="NIFTY", timeframe="1m")
    history = list(candles_from_closes([100.0 + index for index in range(14)]))
    gap_candle = replace(make_candle(60, 120.0), volume=2000)
    history.append(gap_candle)

    result = warm_engine(engine, tuple(history))

    assert result.timestamp == gap_candle.end_time
    assert result.momentum_value == pytest.approx(20.0)
    assert engine.candle_count == 15


def test_overlapping_candle_is_rejected_as_invalid_history_rewrite():
    bus = EventBus()
    invalid = []
    bus.subscribe(MOMENTUM_CONTEXT_INVALID, invalid.append)
    engine = MomentumContextEngine(bus, instrument="NIFTY", timeframe="1m")
    history = candles_from_closes([100.0 + index for index in range(15)])
    warm_engine(engine, history)
    latest = history[-1]
    overlapping = replace(
        make_candle(15, 130.0),
        start_time=latest.end_time - timedelta(seconds=30),
        end_time=latest.end_time + timedelta(seconds=30),
    )

    with pytest.raises(ValueError, match="Overlapping momentum candle"):
        engine.process(overlapping)

    assert invalid[-1] == engine.snapshot()
    assert engine.snapshot().invalid_count == 1
    assert engine.candle_count == 15


def test_stale_candle_is_rejected_as_invalid_history_rewrite():
    bus = EventBus()
    invalid = []
    bus.subscribe(MOMENTUM_CONTEXT_INVALID, invalid.append)
    engine = MomentumContextEngine(bus, instrument="NIFTY", timeframe="1m")
    history = candles_from_closes([100.0 + index for index in range(15)])
    warm_engine(engine, history)

    with pytest.raises(ValueError, match="Stale momentum candle"):
        engine.process(history[-2])

    assert invalid[-1] == engine.snapshot()
    assert engine.snapshot().invalid_count == 1
    assert engine.candle_count == 15


def test_same_end_time_correction_replaces_latest_candle_without_growing_history():
    bus = EventBus()
    updates = []
    bus.subscribe(MOMENTUM_CONTEXT_UPDATED, updates.append)
    engine = MomentumContextEngine(bus, instrument="NIFTY", timeframe="1m")
    history = candles_from_closes([100.0 + index for index in range(15)])
    first = warm_engine(engine, history)
    corrected = replace(history[-1], open=150.0, high=151.0, low=149.0, close=150.0, volume=9999)

    second = engine.process(corrected)

    assert second is not first
    assert engine.state is second
    assert engine.candle_count == 15
    assert engine.snapshot().calculation_count == 2
    assert updates == [first, second]
    assert second.timestamp == corrected.end_time


def test_unexpected_failure_publishes_failed_event(monkeypatch):
    bus = EventBus()
    failed = []
    bus.subscribe(MOMENTUM_CONTEXT_FAILED, failed.append)
    engine = MomentumContextEngine(bus, instrument="NIFTY", timeframe="1m")

    def fail_snapshot(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(momentum_engine_module, "MomentumContextSnapshot", fail_snapshot)

    with pytest.raises(RuntimeError, match="boom"):
        warm_engine(engine, candles_from_closes([100.0 + index for index in range(15)]))

    assert engine.state is None
    assert failed[-1] == engine.snapshot()


def test_snapshot_is_immutable_and_duplicate_candle_is_idempotent():
    bus = EventBus()
    updates = []
    bus.subscribe(MOMENTUM_CONTEXT_UPDATED, updates.append)
    engine = MomentumContextEngine(bus, instrument="NIFTY", timeframe="1m")
    history = candles_from_closes([100.0 + index for index in range(15)])
    first = warm_engine(engine, history)

    second = engine.process(history[-1])

    assert second is first
    assert engine.snapshot().calculation_count == 1
    assert updates == [first]
    with pytest.raises(FrozenInstanceError):
        first.momentum_value = 1.0


def test_runtime_creates_one_momentum_context_engine_per_timeframe_lane():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m", "15m", "30m")),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    assert tuple(runtime.momentum_context_engines) == (
        TimeFrame.ONE_MINUTE,
        TimeFrame.FIVE_MINUTES,
        TimeFrame.FIFTEEN_MINUTES,
        TimeFrame.THIRTY_MINUTES,
    )
    assert runtime.momentum_context_engine is runtime.momentum_context_engines[TimeFrame.ONE_MINUTE]
    assert len({id(engine) for engine in runtime.momentum_context_engines.values()}) == 4
    assert orchestrator.market_data_engine is orchestrator.market_data_engine


def test_runtime_warm_up_updates_primary_momentum_context_without_breaking_legacy_timeframe():
    orchestrator = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(timeframe="1m"))
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    runtime.warm_up_candles(candles_from_closes([100.0 + index for index in range(15)]), replace=True)
    snapshot = runtime.snapshot()

    assert snapshot.timeframe == "1m"
    assert snapshot.momentum_context is runtime.momentum_context_engine.state
    assert snapshot.momentum_context is not None
    assert snapshot.momentum_context_diagnostics.calculation_count == 1


def test_multi_timeframe_momentum_context_lanes_are_isolated():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m")),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    one_minute = warm_engine(
        runtime.momentum_context_engines[TimeFrame.ONE_MINUTE],
        candles_from_closes([100.0 + index for index in range(15)], timeframe="1m"),
    )
    five_minute = warm_engine(
        runtime.momentum_context_engines[TimeFrame.FIVE_MINUTES],
        candles_from_closes([130.0 - index for index in range(15)], timeframe="5m"),
    )

    assert one_minute.momentum_direction is MomentumDirection.RISING
    assert five_minute.momentum_direction is MomentumDirection.FALLING
    assert runtime.momentum_context_engines[TimeFrame.ONE_MINUTE].state is one_minute
    assert runtime.momentum_context_engines[TimeFrame.FIVE_MINUTES].state is five_minute


def test_tradingview_evidence_consumes_momentum_context_without_calculating_it():
    bus = EventBus()
    mapped = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_MAPPED, mapped.append)
    engine = TradingViewEvidenceMappingEngine(bus, instrument="NIFTY", timeframe="1m")
    engine.start()
    momentum_context = warm_engine(
        MomentumContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"),
        candles_from_closes([100.0 + index for index in range(15)]),
    )

    result = engine.map_evidence(TradingViewEvidenceRequest(
        evidence_id="momentum-context-evidence",
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
        momentum=momentum_context,
    ))

    assert result.momentum_status.availability is EvidenceAvailability.AVAILABLE
    assert result.momentum_observation is momentum_context
    assert result.momentum_context_observation is momentum_context
    assert mapped == [result]
