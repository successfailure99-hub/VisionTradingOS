from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration
from application.runtime_contract import RuntimeIntegrityViolation
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import CANDLE_CLOSED
from core.models.candle import Candle
from core.models.tick import Tick


IST = ZoneInfo("Asia/Kolkata")
OPEN = datetime(2026, 8, 6, 9, 15, tzinfo=IST)


def tick(timestamp: datetime, *, price: float = 100.0, volume: int = 10) -> Tick:
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=volume,
        bid_price=price - 0.5,
        ask_price=price + 0.5,
        open_interest=0,
    )


def candle(offset: int, *, price: float = 100.0) -> Candle:
    start = OPEN + timedelta(minutes=offset)
    return Candle(
        symbol="NIFTY",
        timeframe="1m",
        start_time=start,
        end_time=start + timedelta(minutes=1),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=10,
    )


def orchestrator() -> ApplicationOrchestrator:
    item = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(timeframe="1m"))
    item.start()
    return item


def runtime_snapshot(item: ApplicationOrchestrator):
    return item.snapshot().runtime_snapshots[0]


def test_rc12_sparse_live_ticks_keep_runtime_history_integrity_visible():
    item = orchestrator()
    item.process_tick(tick(OPEN + timedelta(seconds=4), price=100.0))
    item.process_tick(tick(OPEN + timedelta(minutes=15, milliseconds=350), price=103.0))

    snapshot = runtime_snapshot(item)
    history = item.get_candle_history("NIFTY")

    assert len(history) == 15
    assert snapshot.candle_history_count == len(history)
    assert tuple(c.start_time for c in history) == tuple(OPEN + timedelta(minutes=i) for i in range(15))
    assert snapshot.runtime_contract_report is not None
    assert snapshot.runtime_contract_report.integrity_violations == ()


def test_rc12_duplicate_ticks_do_not_duplicate_runtime_history_or_closed_events():
    bus = EventBus()
    closed = []
    bus.subscribe(CANDLE_CLOSED, closed.append)
    item = ApplicationOrchestrator(bus, RuntimeConfiguration(timeframe="1m"))
    item.start()

    first = tick(OPEN, price=100.0)
    item.process_tick(first)
    item.process_tick(first)
    item.process_tick(tick(OPEN + timedelta(minutes=1), price=101.0))

    snapshot = runtime_snapshot(item)
    history = item.get_candle_history("NIFTY")

    assert len(history) == 1
    assert len(closed) == 1
    assert closed[0] == history[0]
    assert snapshot.candle_history_count == 1
    assert snapshot.runtime_contract_report.integrity_violations == ()


def test_rc12_out_of_order_ticks_are_rejected_without_mutating_history():
    item = orchestrator()
    item.process_tick(tick(OPEN, price=100.0))
    item.process_tick(tick(OPEN + timedelta(minutes=1), price=101.0))
    before = item.get_candle_history("NIFTY")

    with pytest.raises(ValueError, match="Stale tick received"):
        item.process_tick(tick(OPEN + timedelta(seconds=30), price=99.0))

    after = item.get_candle_history("NIFTY")
    snapshot = runtime_snapshot(item)

    assert after == before
    assert snapshot.candle_history_count == len(after)
    assert snapshot.runtime_contract_report.integrity_violations == ()


def test_rc12_runtime_contract_reports_corrupted_duplicate_candle_history():
    item = orchestrator()
    item.warm_up_candles("NIFTY", tuple(candle(index) for index in range(3)))
    runtime = item.get_runtime("NIFTY")
    runtime.candle_engine.history[Instrument.NIFTY].append(candle(1))

    snapshot = runtime.snapshot()
    report = snapshot.runtime_contract_report

    assert report is not None
    assert report.valid is False
    assert report.integrity_violations
    assert isinstance(report.integrity_violations[0], RuntimeIntegrityViolation)
    assert report.integrity_violations[0].invariant == "Runtime candle history has no duplicate candle timestamps"
    assert report.integrity_violations[0].producer == "CandleEngine"
    assert report.integrity_violations[0].consumer == "Runtime History"
    assert report.blocking_reason == "Candle: Runtime candle history has no duplicate candle timestamps"


def test_rc12_runtime_contract_reports_missing_candle_gap():
    item = orchestrator()
    item.warm_up_candles("NIFTY", (candle(0), candle(2)))

    snapshot = runtime_snapshot(item)
    report = snapshot.runtime_contract_report

    assert report is not None
    assert report.valid is False
    assert any(item.invariant == "Runtime candle history is continuous" for item in report.integrity_violations)


def test_rc12_event_bus_delivers_each_closed_candle_to_every_subscriber_once():
    bus = EventBus()
    first_listener = []
    second_listener = []
    bus.subscribe(CANDLE_CLOSED, first_listener.append)
    bus.subscribe(CANDLE_CLOSED, second_listener.append)
    item = ApplicationOrchestrator(bus, RuntimeConfiguration(timeframe="1m"))
    item.start()

    item.process_tick(tick(OPEN, price=100.0))
    item.process_tick(tick(OPEN + timedelta(minutes=2), price=102.0))

    history = item.get_candle_history("NIFTY")

    assert len(history) == 2
    assert first_listener == list(history)
    assert second_listener == list(history)


def test_rc12_repeated_runtime_snapshots_do_not_diverge_from_canonical_history():
    item = orchestrator()
    for minute in range(16):
        item.process_tick(tick(OPEN + timedelta(minutes=minute), price=100.0 + minute))

    with ThreadPoolExecutor(max_workers=4) as executor:
        snapshots = tuple(executor.map(lambda _: runtime_snapshot(item), range(8)))

    history_count = len(item.get_candle_history("NIFTY"))
    assert history_count == 15
    assert {snapshot.candle_history_count for snapshot in snapshots} == {history_count}
    assert all(snapshot.runtime_contract_report.integrity_violations == () for snapshot in snapshots)
