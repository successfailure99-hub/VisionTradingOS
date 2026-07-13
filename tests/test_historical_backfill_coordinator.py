"""
Tests for HistoricalWarmupCoordinator backfill.
"""

from datetime import UTC, datetime, timedelta

import pytest

from application import ApplicationBootstrap
from application.historical_warmup import HistoricalWarmupCoordinator, HistoricalWarmupStatus
from brokers.zerodha.historical import ZerodhaHistoricalDataManager
from brokers.zerodha.instruments import ZerodhaInstrumentRecord, ZerodhaInstrumentResolution, ZerodhaInstrumentType
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.events import MARKET_UPDATED, NEW_TICK


TS = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


class FakeHistoricalClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.disconnected = False

    def historical_data(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0) if self.responses else []


class SequenceClock:
    def __init__(self, *values):
        self.values = list(values)

    def __call__(self):
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def raw(offset=0):
    at = TS + timedelta(minutes=offset)
    return dict(date=at, open=100.0, high=103.0, low=99.0, close=101.0 + offset, volume=10)


def resolution():
    record = ZerodhaInstrumentRecord(101, 101, "NIFTY", "NIFTY", Exchange.NSE, "INDICES", ZerodhaInstrumentType.INDEX, None, 0.0, 1, 0.05)
    return ZerodhaInstrumentResolution(Instrument.NIFTY, record, ZerodhaInstrumentSubscription(101, Instrument.NIFTY, Exchange.NSE))


def make_coordinator(client, events=None, clock=None):
    lifecycle = ApplicationBootstrap().create_application()
    if events:
        for name in (NEW_TICK, MARKET_UPDATED):
            lifecycle.orchestrator._event_bus.subscribe(name, events.append)
    lifecycle.start()
    manager = ZerodhaHistoricalDataManager(client=client, clock=lambda: TS)
    item = HistoricalWarmupCoordinator(lifecycle=lifecycle, historical_manager=manager, resolutions=(resolution(),), clock=clock or (lambda: TS))
    return lifecycle, item


def test_backfill_requires_history_and_fetches_from_last_candle_end():
    client = FakeHistoricalClient([[raw(0)]])
    lifecycle, item = make_coordinator(client)
    with pytest.raises(ValueError, match="warm_up"):
        item.backfill(instrument=Instrument.NIFTY, end_at=TS + timedelta(minutes=2))
    item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=1))
    client.responses.append([raw(1), raw(2)])
    snapshot = item.backfill(instrument=Instrument.NIFTY, end_at=TS + timedelta(minutes=2))
    assert snapshot.status is HistoricalWarmupStatus.READY
    assert client.calls[-1]["from_date"] == TS + timedelta(minutes=1)
    assert lifecycle.orchestrator.get_candle_history("NIFTY")[-1].start_time == TS + timedelta(minutes=1)


def test_backfill_idempotent_rejects_bad_end_wrong_instrument_and_no_live_side_effects():
    events = []
    client = FakeHistoricalClient([[raw(0)], [raw(1)], [raw(1)]])
    lifecycle, item = make_coordinator(client, events)
    item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=1))
    same_end = item.backfill(instrument=Instrument.NIFTY, end_at=TS + timedelta(minutes=1))
    assert same_end.results[0].seed_result.accepted_count == 0
    with pytest.raises(ValueError):
        item.backfill(instrument=Instrument.BANKNIFTY, end_at=TS + timedelta(minutes=2))
    first = item.backfill(instrument=Instrument.NIFTY, end_at=TS + timedelta(minutes=2))
    second = item.backfill(instrument=Instrument.NIFTY, end_at=TS + timedelta(minutes=2))
    assert first.total_seeded_candles == 2
    assert second.results[0].seed_result.accepted_count == 0
    assert events == []
    assert lifecycle.orchestrator.snapshot().runtime_snapshots[0].latest_order is None


@pytest.mark.parametrize(
    ("clock_value", "expected_error"),
    (
        ("not-a-datetime", TypeError),
        (datetime(2026, 7, 10, 9, 16), ValueError),
        (RuntimeError("startup clock failed {'secret': 'payload'}"), RuntimeError),
    ),
)
def test_backfill_startup_clock_failure_records_error(clock_value, expected_error):
    lifecycle, item = make_coordinator(FakeHistoricalClient([[raw(0)]]), clock=SequenceClock(clock_value))

    if isinstance(clock_value, Exception):
        with pytest.raises(expected_error) as exc:
            item.backfill(instrument=Instrument.NIFTY, end_at=TS + timedelta(minutes=1))
        assert exc.value is clock_value
    else:
        with pytest.raises(expected_error):
            item.backfill(instrument=Instrument.NIFTY, end_at=TS + timedelta(minutes=1))

    snapshot = item.snapshot()
    assert snapshot.status is HistoricalWarmupStatus.ERROR
    assert snapshot.operation_count == 1
    assert snapshot.failed_operation_count == 1
    assert snapshot.successful_operation_count == 0
    assert snapshot.started_at is None
    assert snapshot.results == ()
    assert snapshot.last_error is not None
    assert snapshot.status is not HistoricalWarmupStatus.VALIDATING


def test_backfill_completion_clock_failure_records_error_and_preserves_seeded_state():
    lifecycle, item = make_coordinator(FakeHistoricalClient([[raw(0)], [raw(1)]]))
    item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=1))
    clock_error = RuntimeError("completion clock failed {'secret': 'payload'}")
    item._clock = SequenceClock(TS, clock_error)

    with pytest.raises(RuntimeError) as exc:
        item.backfill(instrument=Instrument.NIFTY, end_at=TS + timedelta(minutes=2))

    assert exc.value is clock_error
    snapshot = item.snapshot()
    assert snapshot.status is HistoricalWarmupStatus.ERROR
    assert snapshot.failed_operation_count == 1
    assert snapshot.successful_operation_count == 1
    assert snapshot.last_error == "RuntimeError: completion clock failed"
    assert len(lifecycle.orchestrator.get_candle_history("NIFTY")) == 2
