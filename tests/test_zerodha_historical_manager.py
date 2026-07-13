"""
Tests for Zerodha historical data manager.
"""

from datetime import UTC, datetime, timedelta
from threading import RLock

import pytest

from brokers.zerodha.historical import ZerodhaHistoricalDataManager, ZerodhaHistoricalRequest, ZerodhaHistoricalStatus
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def raw(at=NOW, close=105.0):
    return dict(date=at, open=100.0, high=110.0, low=90.0, close=close, volume=10)


def request(end=None):
    return ZerodhaHistoricalRequest(101, Instrument.NIFTY, Exchange.NSE, TimeFrame.FIVE_MINUTES, NOW, end or NOW + timedelta(minutes=20))


class FakeClient:
    def __init__(self, responses=None, fail=False):
        self.responses = list(responses or [[raw(NOW), raw(NOW + timedelta(minutes=10)), raw(NOW + timedelta(minutes=10))]])
        self.fail = fail
        self.calls = []

    def historical_data(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("client failed {'raw': 'payload'} real_secret")
        return self.responses.pop(0) if self.responses else []


class SequenceClock:
    def __init__(self, *values):
        self.values = list(values)

    def __call__(self):
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_initial_fetch_success_counters_gap_duplicate_and_flags():
    client = FakeClient()
    manager = ZerodhaHistoricalDataManager(client=client, clock=lambda: NOW)
    assert manager.snapshot().status is ZerodhaHistoricalStatus.CREATED
    result = manager.fetch(request())
    assert client.calls[0]["interval"] == "5minute"
    assert client.calls[0]["continuous"] is False
    assert client.calls[0]["oi"] is False
    assert result.source_record_count == 3
    assert result.normalized_count == 2
    assert result.duplicate_count == 1
    assert len(result.gaps) >= 2
    snapshot = manager.snapshot()
    assert snapshot.status is ZerodhaHistoricalStatus.READY
    assert snapshot.fetch_count == 1
    assert snapshot.successful_fetch_count == 1
    assert snapshot.total_source_records == 3
    assert isinstance(manager._lock, type(RLock()))


def test_malformed_rows_continue_empty_failure_preserves_last_result_and_clear():
    manager = ZerodhaHistoricalDataManager(client=FakeClient([[raw(), dict(date=NOW, open=0, high=1, low=1, close=1, volume=1)]]), clock=lambda: NOW)
    first = manager.fetch(request())
    assert first.rejected_count == 1
    manager._client = FakeClient([[]])
    empty = manager.fetch(request())
    assert empty.candles == ()
    assert manager.snapshot().status is ZerodhaHistoricalStatus.EMPTY
    previous = manager.snapshot().last_result
    manager._client = FakeClient(fail=True)
    with pytest.raises(RuntimeError):
        manager.fetch(request())
    snapshot = manager.snapshot()
    assert snapshot.status is ZerodhaHistoricalStatus.ERROR
    assert snapshot.failed_fetch_count == 1
    assert snapshot.last_result is previous
    assert "{" not in snapshot.last_error
    manager.clear()
    assert manager.snapshot().fetch_count == 0
    assert manager.snapshot().last_result is None


def test_invalid_response_fetch_resolution_and_multiple_chunks():
    client = FakeClient([[], []])
    manager = ZerodhaHistoricalDataManager(client=client, clock=lambda: NOW)
    manager.fetch(request(NOW + timedelta(days=150)))
    assert len(client.calls) == 2
    manager._client = type("BadClient", (), {"historical_data": lambda self, **kwargs: "bad"})()
    with pytest.raises(TypeError):
        manager.fetch(request())
    from brokers.zerodha.instruments import ZerodhaInstrumentRecord, ZerodhaInstrumentResolution, ZerodhaInstrumentType
    from brokers.zerodha.market_data import ZerodhaInstrumentSubscription

    record = ZerodhaInstrumentRecord(101, 1, "NIFTY 50", "NIFTY 50", Exchange.NSE, "INDICES", ZerodhaInstrumentType.INDEX, None, 0.0, 1, 0.05)
    resolution = ZerodhaInstrumentResolution(Instrument.NIFTY, record, ZerodhaInstrumentSubscription(101, Instrument.NIFTY, Exchange.NSE))
    manager._client = FakeClient([[raw()]])
    result = manager.fetch_resolution(resolution, timeframe=TimeFrame.FIVE_MINUTES, start_at=NOW, end_at=NOW + timedelta(minutes=5))
    assert result.request.instrument_token == 101


@pytest.mark.parametrize(
    ("bad_clock_value", "expected_error"),
    (
        ("not-a-datetime", TypeError),
        (datetime(2026, 7, 12, 9, 16), ValueError),
        (RuntimeError("clock failed {'secret': 'payload'}"), RuntimeError),
    ),
)
def test_startup_clock_failure_enters_error_and_preserves_previous_state(bad_clock_value, expected_error):
    clock = SequenceClock(NOW, NOW + timedelta(seconds=1), bad_clock_value)
    manager = ZerodhaHistoricalDataManager(client=FakeClient([[raw()]]), clock=clock)
    previous_result = manager.fetch(request(NOW + timedelta(minutes=5)))
    previous_snapshot = manager.snapshot()
    attempted_request = request(NOW + timedelta(minutes=10))

    if isinstance(bad_clock_value, Exception):
        with pytest.raises(expected_error) as exc:
            manager.fetch(attempted_request)
        assert exc.value is bad_clock_value
    else:
        with pytest.raises(expected_error):
            manager.fetch(attempted_request)

    snapshot = manager.snapshot()
    assert snapshot.status is ZerodhaHistoricalStatus.ERROR
    assert snapshot.fetch_count == 2
    assert snapshot.failed_fetch_count == 1
    assert snapshot.successful_fetch_count == 1
    assert snapshot.last_request is attempted_request
    assert snapshot.last_result is previous_result
    assert snapshot.last_started_at == previous_snapshot.last_started_at
    assert snapshot.last_completed_at == previous_snapshot.last_completed_at
    assert snapshot.total_source_records == previous_snapshot.total_source_records
    assert snapshot.total_normalized_candles == previous_snapshot.total_normalized_candles
    assert snapshot.last_error is not None
    assert "{" not in snapshot.last_error
    assert snapshot.status is not ZerodhaHistoricalStatus.FETCHING


def test_completion_clock_failure_enters_error_without_committing_partial_result():
    clock_error = RuntimeError("completion clock failed {'raw': 'payload'}")
    manager = ZerodhaHistoricalDataManager(client=FakeClient([[raw()]]), clock=SequenceClock(NOW, clock_error))

    with pytest.raises(RuntimeError) as exc:
        manager.fetch(request(NOW + timedelta(minutes=5)))

    assert exc.value is clock_error
    snapshot = manager.snapshot()
    assert snapshot.status is ZerodhaHistoricalStatus.ERROR
    assert snapshot.fetch_count == 1
    assert snapshot.failed_fetch_count == 1
    assert snapshot.successful_fetch_count == 0
    assert snapshot.total_source_records == 0
    assert snapshot.total_normalized_candles == 0
    assert snapshot.last_request == request(NOW + timedelta(minutes=5))
    assert snapshot.last_result is None
    assert snapshot.last_started_at == NOW
    assert snapshot.last_completed_at is None
    assert snapshot.last_error == "RuntimeError: completion clock failed"
