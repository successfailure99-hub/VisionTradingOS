from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone

import pytest

from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from application.orchestrator import ApplicationOrchestrator
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import ADR_FAILED, ADR_INVALID, ADR_PARTIAL, ADR_UPDATED
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from engines.adr import ADREngine, ADRExpansionState, ADRExhaustionState, ADRRequest, ADRSnapshot
import engines.adr.engine as adr_engine_module
from engines.tradingview_evidence import EvidenceAvailability, TradingViewEvidenceMappingEngine
from engines.tradingview_evidence.models import TradingViewEvidenceRequest


NOW = datetime(2026, 7, 21, 9, 30, tzinfo=timezone.utc)


def daily_history(count: int, *, start: date = date(2026, 6, 1), range_points: float = 100.0) -> tuple[DailyOHLC, ...]:
    return tuple(
        DailyOHLC(
            trading_date=start + timedelta(days=index),
            open=1000.0,
            high=1050.0 + (range_points - 100.0),
            low=950.0,
            close=1010.0,
        )
        for index in range(count)
    )


def adr_request(*, period: int = 20, session_low: float = 1000.0, today_range: float = 50.0) -> ADRRequest:
    session_high = session_low + today_range
    return ADRRequest(
        trading_date=NOW.date(),
        instrument="NIFTY",
        daily_history=daily_history(period),
        latest_price=session_low if today_range == 0 else session_low + (today_range / 2),
        session_high=session_high,
        session_low=session_low,
        timestamp=NOW,
    )


def tick(timestamp: datetime, price: float = 1000.0) -> Tick:
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=10,
        bid_price=price - 0.5,
        ask_price=price + 0.5,
        open_interest=0,
    )


def test_adr_calculation_known_history_and_events():
    bus = EventBus()
    seen = []
    bus.subscribe(ADR_UPDATED, seen.append)
    engine = ADREngine(bus, instrument="NIFTY", period=20)

    result = engine.calculate(adr_request(today_range=50.0))

    assert isinstance(result, ADRSnapshot)
    assert result.instrument == "NIFTY"
    assert result.adr_period == 20
    assert result.adr_value == pytest.approx(100.0)
    assert result.today_high == pytest.approx(1050.0)
    assert result.today_low == pytest.approx(1000.0)
    assert result.today_range == pytest.approx(50.0)
    assert result.adr_high == pytest.approx(1100.0)
    assert result.adr_low == pytest.approx(950.0)
    assert result.range_consumed_pct == pytest.approx(50.0)
    assert result.range_remaining_pct == pytest.approx(50.0)
    assert result.expansion_state is ADRExpansionState.NORMAL
    assert result.exhaustion_state is ADRExhaustionState.NOT_EXHAUSTED
    assert engine.state is result
    assert engine.snapshot().calculation_count == 1
    assert seen == [result]


@pytest.mark.parametrize("period", (5, 10, 20, 50))
def test_supported_adr_periods_are_configurable(period):
    engine = ADREngine(EventBus(), instrument="NIFTY", period=period)
    result = engine.calculate(adr_request(period=period, today_range=25.0))

    assert result.adr_period == period
    assert result.adr_value == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("today_range", "consumed", "remaining", "expansion", "exhaustion"),
    (
        (0.0, 0.0, 100.0, ADRExpansionState.NOT_STARTED, ADRExhaustionState.NOT_STARTED),
        (25.0, 25.0, 75.0, ADRExpansionState.NORMAL, ADRExhaustionState.NOT_EXHAUSTED),
        (50.0, 50.0, 50.0, ADRExpansionState.NORMAL, ADRExhaustionState.NOT_EXHAUSTED),
        (75.0, 75.0, 25.0, ADRExpansionState.EXPANDING, ADRExhaustionState.NOT_EXHAUSTED),
        (100.0, 100.0, 0.0, ADRExpansionState.ADR_REACHED, ADRExhaustionState.EXHAUSTED),
        (120.0, 120.0, 0.0, ADRExpansionState.ADR_EXCEEDED, ADRExhaustionState.EXHAUSTED),
        (150.0, 150.0, 0.0, ADRExpansionState.EXTREME_EXPANSION, ADRExhaustionState.EXTREME),
    ),
)
def test_range_consumption_and_expansion_states(today_range, consumed, remaining, expansion, exhaustion):
    result = ADREngine(EventBus(), instrument="NIFTY", period=20).calculate(adr_request(today_range=today_range))

    assert result.range_consumed_pct == pytest.approx(consumed)
    assert result.range_remaining_pct == pytest.approx(remaining)
    assert result.expansion_state is expansion
    assert result.exhaustion_state is exhaustion


def test_invalid_and_insufficient_history_are_rejected_without_state_mutation():
    bus = EventBus()
    partial = []
    bus.subscribe(ADR_PARTIAL, partial.append)
    engine = ADREngine(bus, instrument="NIFTY", period=20)

    with pytest.raises(ValueError, match="Insufficient daily history"):
        engine.calculate(ADRRequest(
            trading_date=NOW.date(),
            instrument="NIFTY",
            daily_history=daily_history(19),
            latest_price=1000.0,
            session_high=1010.0,
            session_low=990.0,
            timestamp=NOW,
        ))
    assert engine.state is None
    assert engine.snapshot().partial_count == 1
    assert partial

    with pytest.raises(ValueError):
        engine.calculate(adr_request(period=20, session_low=1000.0, today_range=float("nan")))
    assert engine.state is None

    with pytest.raises(ValueError, match="duplicate"):
        engine.calculate(ADRRequest(
            trading_date=NOW.date(),
            instrument="NIFTY",
            daily_history=(daily_history(1)[0], daily_history(1)[0], *daily_history(19, start=date(2026, 6, 2))),
            latest_price=1000.0,
            session_high=1010.0,
            session_low=990.0,
            timestamp=NOW,
        ))


@pytest.mark.parametrize(
    "daily_ohlc",
    (
        DailyOHLC(date(2026, 6, 1), open=1000.0, high=950.0, low=950.0, close=950.0),
        DailyOHLC(date(2026, 6, 1), open=1000.0, high=float("nan"), low=950.0, close=1000.0),
        DailyOHLC(date(2026, 6, 1), open=-1000.0, high=1050.0, low=950.0, close=1000.0),
    ),
)
def test_invalid_daily_ohlc_values_publish_invalid_event(daily_ohlc):
    bus = EventBus()
    invalid = []
    bus.subscribe(ADR_INVALID, invalid.append)
    engine = ADREngine(bus, instrument="NIFTY", period=20)
    history = (daily_ohlc, *daily_history(19, start=date(2026, 6, 2)))

    with pytest.raises(ValueError):
        engine.calculate(ADRRequest(
            trading_date=NOW.date(),
            instrument="NIFTY",
            daily_history=history,
            latest_price=1000.0,
            session_high=1010.0,
            session_low=990.0,
            timestamp=NOW,
        ))

    assert engine.state is None
    assert engine.snapshot().invalid_count == 1
    assert invalid == [engine.snapshot()]


def test_unexpected_calculation_failure_publishes_failed_event(monkeypatch):
    bus = EventBus()
    failed = []
    bus.subscribe(ADR_FAILED, failed.append)
    engine = ADREngine(bus, instrument="NIFTY", period=20)

    def fail_snapshot(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(adr_engine_module, "ADRSnapshot", fail_snapshot)

    with pytest.raises(RuntimeError, match="boom"):
        engine.calculate(adr_request(today_range=50.0))

    assert engine.state is None
    assert engine.snapshot().last_error == "ADR calculation failed."
    assert failed == [engine.snapshot()]


def test_snapshot_is_immutable_and_duplicate_request_is_idempotent():
    engine = ADREngine(EventBus(), instrument="NIFTY", period=20)
    request = adr_request(today_range=50.0)

    first = engine.calculate(request)
    second = engine.calculate(request)

    assert second is first
    assert engine.snapshot().calculation_count == 1
    with pytest.raises(FrozenInstanceError):
        first.adr_value = 1.0


def test_same_observable_adr_snapshot_does_not_publish_duplicate_update():
    bus = EventBus()
    updates = []
    bus.subscribe(ADR_UPDATED, updates.append)
    engine = ADREngine(bus, instrument="NIFTY", period=20)
    first = engine.calculate(adr_request(today_range=50.0))
    second = engine.calculate(ADRRequest(
        trading_date=NOW.date(),
        instrument="NIFTY",
        daily_history=daily_history(20),
        latest_price=1020.0,
        session_high=1050.0,
        session_low=1000.0,
        timestamp=NOW + timedelta(seconds=1),
    ))

    assert second is first
    assert updates == [first]
    assert engine.snapshot().calculation_count == 1


def test_session_end_same_range_keeps_final_adr_state_stable():
    engine = ADREngine(EventBus(), instrument="NIFTY", period=20)
    session_end = datetime(2026, 7, 21, 15, 30, tzinfo=timezone.utc)
    first = engine.calculate(ADRRequest(
        trading_date=session_end.date(),
        instrument="NIFTY",
        daily_history=daily_history(20),
        latest_price=1030.0,
        session_high=1050.0,
        session_low=1000.0,
        timestamp=session_end,
    ))
    second = engine.calculate(ADRRequest(
        trading_date=session_end.date(),
        instrument="NIFTY",
        daily_history=daily_history(20),
        latest_price=1025.0,
        session_high=1050.0,
        session_low=1000.0,
        timestamp=session_end + timedelta(seconds=10),
    ))

    assert second is first
    assert second.range_consumed_pct == pytest.approx(50.0)
    assert second.expansion_state is ADRExpansionState.NORMAL


def test_gap_day_daily_history_is_valid_historical_input():
    history = tuple(
        DailyOHLC(
            trading_date=date(2026, 6, 1) + timedelta(days=index * 2),
            open=1000.0,
            high=1050.0,
            low=950.0,
            close=1010.0,
        )
        for index in range(20)
    )

    result = ADREngine(EventBus(), instrument="NIFTY", period=20).calculate(ADRRequest(
        trading_date=NOW.date(),
        instrument="NIFTY",
        daily_history=history,
        latest_price=1025.0,
        session_high=1050.0,
        session_low=1000.0,
        timestamp=NOW,
    ))

    assert result.adr_value == pytest.approx(100.0)
    assert result.range_consumed_pct == pytest.approx(50.0)


def test_runtime_updates_adr_automatically_from_existing_daily_history_and_ticks():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,), adr_period=20),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    for item in daily_history(20):
        orchestrator.process_daily_ohlc(RuntimeInstrument.NIFTY, item)

    snapshot = orchestrator.process_tick(tick(NOW, price=1000.0))

    assert runtime.adr_engine.state is not None
    assert snapshot.adr is runtime.adr_engine.state
    assert snapshot.adr.adr_value == pytest.approx(100.0)
    assert snapshot.adr_diagnostics.last_snapshot is snapshot.adr


def test_runtime_repeated_ticks_inside_unchanged_range_publish_one_adr_update():
    bus = EventBus()
    updates = []
    bus.subscribe(ADR_UPDATED, updates.append)
    orchestrator = ApplicationOrchestrator(
        bus,
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,), adr_period=20),
    )
    orchestrator.start()
    for item in daily_history(20):
        orchestrator.process_daily_ohlc(RuntimeInstrument.NIFTY, item)

    for offset in range(3):
        orchestrator.process_tick(tick(NOW + timedelta(seconds=offset), price=1000.0))

    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    assert len(updates) == 1
    assert runtime.adr_engine.snapshot().calculation_count == 1


def test_tradingview_evidence_consumes_adr_snapshot_when_available():
    bus = EventBus()
    mapping_engine = TradingViewEvidenceMappingEngine(bus, instrument="NIFTY", timeframe="1m")
    mapping_engine.start()
    adr = ADREngine(bus, instrument="NIFTY", period=20).calculate(adr_request(today_range=50.0))
    candle = Candle(
        symbol="NIFTY",
        timeframe="1m",
        start_time=NOW - timedelta(minutes=1),
        end_time=NOW,
        open=1000.0,
        high=1010.0,
        low=990.0,
        close=1000.0,
        volume=100,
    )

    result = mapping_engine.map_evidence(
        TradingViewEvidenceRequest(
            evidence_id="adr-evidence",
            timestamp=NOW,
            instrument=RuntimeInstrument.NIFTY,
            timeframe="1m",
            latest_price=1000.0,
            latest_candle=candle,
            camarilla=None,
            cpr=None,
            vwap=None,
            adr=adr,
            price_action=None,
            market_context=None,
            option_chain=None,
        )
    )

    assert result.adr_status.availability is EvidenceAvailability.AVAILABLE
    assert result.adr_observation is adr
    assert "adr" not in result.missing_evidence


def test_runtime_evidence_integration_includes_adr_after_closed_candle():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,), adr_period=20),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    for item in daily_history(20):
        orchestrator.process_daily_ohlc(RuntimeInstrument.NIFTY, item)

    orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 15, tzinfo=timezone.utc), price=1000.0))
    orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 16, tzinfo=timezone.utc), price=1001.0))

    evidence = runtime.tradingview_evidence_snapshot().last_evidence
    assert evidence is not None
    assert evidence.adr_status.availability is EvidenceAvailability.AVAILABLE
    assert evidence.adr_observation is runtime.adr_engine.state
