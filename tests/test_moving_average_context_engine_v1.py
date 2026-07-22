from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core.enums.timeframe import TimeFrame
from core.event_bus import EventBus
from core.events import (
    MA_CONTEXT_FAILED,
    MA_CONTEXT_INVALID,
    MA_CONTEXT_PARTIAL,
    MA_CONTEXT_UPDATED,
    TRADINGVIEW_EVIDENCE_MAPPED,
)
from core.models.candle import Candle
from engines.moving_average_context import (
    MovingAverageAlignment,
    MovingAverageCompressionState,
    MovingAverageContextEngine,
    MovingAverageContextProfile,
    MovingAverageContextSnapshot,
    MovingAverageExpansionState,
    MovingAverageSlope,
)
import engines.moving_average_context.engine as ma_engine_module
from engines.tradingview_evidence import EvidenceAvailability, PriceLocation, TradingViewEvidenceMappingEngine
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


START = NOW - timedelta(minutes=220)


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


def warm_engine(engine: MovingAverageContextEngine, candles: tuple[Candle, ...]) -> MovingAverageContextSnapshot:
    result = None
    for item in candles:
        try:
            result = engine.process(item)
        except ValueError as exc:
            if "Insufficient candle history" not in str(exc):
                raise
    assert result is not None
    return result


def expected_ema(values: list[float], period: int) -> float:
    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for value in values[period:]:
        ema = ((value - ema) * multiplier) + ema
    return round(ema, 2)


def test_ema_correctness_known_candle_history_and_events():
    bus = EventBus()
    updates = []
    bus.subscribe(MA_CONTEXT_UPDATED, updates.append)
    engine = MovingAverageContextEngine(bus, instrument="NIFTY", timeframe="1m")
    closes = [100.0 + index for index in range(220)]

    result = warm_engine(engine, candles_from_closes(closes))

    assert result.ema20 == pytest.approx(expected_ema(closes, 20))
    assert result.ema50 == pytest.approx(expected_ema(closes, 50))
    assert result.ema200 == pytest.approx(expected_ema(closes, 200))
    assert result.price_above_ema20 is True
    assert result.price_above_ema50 is True
    assert result.price_above_ema200 is True
    assert result.ema_alignment is MovingAverageAlignment.STRONG_BULLISH
    assert engine.state is result
    assert engine.snapshot().calculation_count == 21
    assert updates[-1] is result


def test_configurable_profile_requires_default_ema_periods_and_allows_extension():
    profile = MovingAverageContextProfile((20, 50, 100, 200))
    engine = MovingAverageContextEngine(EventBus(), instrument="NIFTY", timeframe="1m", profile=profile)

    result = warm_engine(engine, candles_from_closes([100.0 + index for index in range(220)]))

    assert engine.periods == (20, 50, 100, 200)
    assert tuple(item.period for item in result.ema_values) == (20, 50, 100, 200)
    with pytest.raises(ValueError, match="requires EMA 20"):
        MovingAverageContextProfile((20, 50))


@pytest.mark.parametrize(
    ("closes", "expected"),
    (
        ([100.0 + index for index in range(220)], MovingAverageAlignment.STRONG_BULLISH),
        ([300.0 - index for index in range(220)], MovingAverageAlignment.STRONG_BEARISH),
        ([100.0 for _ in range(220)], MovingAverageAlignment.NEUTRAL),
    ),
)
def test_alignment_states_from_engine_output(closes, expected):
    result = warm_engine(MovingAverageContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"), candles_from_closes(closes))

    assert result.ema_alignment is expected


@pytest.mark.parametrize(
    ("price", "ema20", "ema50", "ema200", "expected"),
    (
        (99.0, 105.0, 100.0, 95.0, MovingAverageAlignment.BULLISH),
        (101.0, 95.0, 100.0, 105.0, MovingAverageAlignment.BEARISH),
    ),
)
def test_bullish_and_bearish_alignment_are_context_not_trade_signals(price, ema20, ema50, ema200, expected):
    assert ma_engine_module._alignment(price, ema20, ema50, ema200) is expected


@pytest.mark.parametrize(
    ("series", "expected"),
    (
        ((100.0, 100.0, 100.0), MovingAverageSlope.FLAT),
        ((100.0, 101.0, 102.0), MovingAverageSlope.RISING),
        ((102.0, 101.0, 100.0), MovingAverageSlope.FALLING),
        ((100.0, 101.0, 103.0), MovingAverageSlope.ACCELERATING),
        ((100.0, 102.0, 103.0), MovingAverageSlope.DECELERATING),
    ),
)
def test_slope_classification_is_deterministic(series, expected):
    assert ma_engine_module._slope(series) is expected


def test_compression_and_expansion_states_are_deterministic():
    compressed = warm_engine(
        MovingAverageContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"),
        candles_from_closes([100.0 for _ in range(220)]),
    )
    expanding = warm_engine(
        MovingAverageContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"),
        candles_from_closes([100.0 for _ in range(200)] + [120.0 + index for index in range(20)]),
    )

    assert compressed.compression_state is MovingAverageCompressionState.COMPRESSED
    assert compressed.expansion_state is MovingAverageExpansionState.NORMAL
    assert expanding.compression_state is MovingAverageCompressionState.EXPANDING
    assert expanding.expansion_state is MovingAverageExpansionState.EXPANDING


def test_invalid_and_insufficient_history_publish_contract_events():
    bus = EventBus()
    partial = []
    invalid = []
    bus.subscribe(MA_CONTEXT_PARTIAL, partial.append)
    bus.subscribe(MA_CONTEXT_INVALID, invalid.append)
    engine = MovingAverageContextEngine(bus, instrument="NIFTY", timeframe="1m")

    with pytest.raises(ValueError, match="Insufficient candle history"):
        engine.process(make_candle(0, 100.0))
    assert partial == [engine.snapshot()]
    assert engine.state is None

    with pytest.raises(ValueError, match="greater than zero"):
        engine.process(make_candle(1, -1.0))
    assert invalid[-1] == engine.snapshot()
    assert engine.state is None


def test_unexpected_failure_publishes_failed_event(monkeypatch):
    bus = EventBus()
    failed = []
    bus.subscribe(MA_CONTEXT_FAILED, failed.append)
    engine = MovingAverageContextEngine(bus, instrument="NIFTY", timeframe="1m")

    def fail_snapshot(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ma_engine_module, "MovingAverageContextSnapshot", fail_snapshot)

    with pytest.raises(RuntimeError, match="boom"):
        warm_engine(engine, candles_from_closes([100.0 + index for index in range(220)]))

    assert engine.state is None
    assert failed[-1] == engine.snapshot()


def test_snapshot_is_immutable_and_duplicate_candle_is_idempotent():
    bus = EventBus()
    updates = []
    bus.subscribe(MA_CONTEXT_UPDATED, updates.append)
    engine = MovingAverageContextEngine(bus, instrument="NIFTY", timeframe="1m")
    history = candles_from_closes([100.0 + index for index in range(220)])
    first = warm_engine(engine, history)

    second = engine.process(history[-1])

    assert second is first
    assert engine.snapshot().calculation_count == 21
    assert updates.count(first) == 1
    with pytest.raises(FrozenInstanceError):
        first.ema20 = 1.0


def test_runtime_creates_one_moving_average_context_engine_per_timeframe_lane():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m", "15m", "30m")),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    assert tuple(runtime.moving_average_context_engines) == (
        TimeFrame.ONE_MINUTE,
        TimeFrame.FIVE_MINUTES,
        TimeFrame.FIFTEEN_MINUTES,
        TimeFrame.THIRTY_MINUTES,
    )
    assert runtime.moving_average_context_engine is runtime.moving_average_context_engines[TimeFrame.ONE_MINUTE]
    assert len({id(engine) for engine in runtime.moving_average_context_engines.values()}) == 4
    assert orchestrator.market_data_engine is orchestrator.market_data_engine


def test_runtime_warm_up_updates_primary_moving_average_context_without_breaking_legacy_timeframe():
    orchestrator = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(timeframe="1m"))
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    runtime.warm_up_candles(candles_from_closes([100.0 + index for index in range(220)]), replace=True)
    snapshot = runtime.snapshot()

    assert snapshot.timeframe == "1m"
    assert snapshot.moving_average_context is runtime.moving_average_context_engine.state
    assert snapshot.moving_average_context is not None
    assert snapshot.moving_average_context_diagnostics.calculation_count == 21


def test_multi_timeframe_moving_average_context_lanes_are_isolated():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m")),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    one_minute = warm_engine(
        runtime.moving_average_context_engines[TimeFrame.ONE_MINUTE],
        candles_from_closes([100.0 + index for index in range(220)], timeframe="1m"),
    )
    five_minute = warm_engine(
        runtime.moving_average_context_engines[TimeFrame.FIVE_MINUTES],
        candles_from_closes([300.0 - index for index in range(220)], timeframe="5m"),
    )

    assert one_minute.ema_alignment is MovingAverageAlignment.STRONG_BULLISH
    assert five_minute.ema_alignment is MovingAverageAlignment.STRONG_BEARISH
    assert runtime.moving_average_context_engines[TimeFrame.ONE_MINUTE].state is one_minute
    assert runtime.moving_average_context_engines[TimeFrame.FIVE_MINUTES].state is five_minute


def test_tradingview_evidence_consumes_moving_average_context_without_calculating_it():
    bus = EventBus()
    mapped = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_MAPPED, mapped.append)
    engine = TradingViewEvidenceMappingEngine(bus, instrument="NIFTY", timeframe="1m")
    engine.start()
    ma_context = warm_engine(
        MovingAverageContextEngine(EventBus(), instrument="NIFTY", timeframe="1m"),
        candles_from_closes([100.0 + index for index in range(220)]),
    )

    result = engine.map_evidence(TradingViewEvidenceRequest(
        evidence_id="ma-context-evidence",
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
        moving_average_context=ma_context,
    ))

    assert result.moving_average_status.availability is EvidenceAvailability.AVAILABLE
    assert result.moving_average_context_observation is ma_context
    assert tuple(item.period for item in result.moving_average_observations) == (20, 50, 200)
    assert result.moving_average_observations[0].price_location is PriceLocation.ABOVE
    assert mapped == [result]
