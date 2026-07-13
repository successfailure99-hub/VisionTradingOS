"""
Tests for HistoricalWarmupCoordinator.
"""

from datetime import UTC, datetime, timedelta
from threading import RLock

import pytest

from application import ApplicationBootstrap
from application.historical_warmup import (
    HistoricalWarmupConfiguration,
    HistoricalWarmupCoordinator,
    HistoricalWarmupCoordinatorFactory,
    HistoricalWarmupStatus,
)
from brokers.zerodha.historical import ZerodhaHistoricalDataManager
from brokers.zerodha.instruments import ZerodhaInstrumentRecord, ZerodhaInstrumentResolution, ZerodhaInstrumentType
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


TS = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


class FakeHistoricalClient:
    def __init__(self, responses=None, fail=False):
        self.responses = list(responses or [])
        self.fail = fail
        self.calls = []

    def historical_data(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("historical failure {'api_key': 'secret'}")
        return self.responses.pop(0) if self.responses else []


class SequenceClock:
    def __init__(self, *values):
        self.values = list(values)

    def __call__(self):
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def raw(offset=0, close=101.0):
    at = TS + timedelta(minutes=offset)
    return dict(date=at, open=100.0, high=103.0, low=99.0, close=close, volume=10)


def resolution(instrument=Instrument.NIFTY, token=101):
    record = ZerodhaInstrumentRecord(token, token, instrument.value, instrument.value, Exchange.NSE, "INDICES", ZerodhaInstrumentType.INDEX, None, 0.0, 1, 0.05)
    return ZerodhaInstrumentResolution(instrument, record, ZerodhaInstrumentSubscription(token, instrument, Exchange.NSE))


def coordinator(client=None, config=None, clock=None):
    lifecycle = ApplicationBootstrap().create_application()
    manager = ZerodhaHistoricalDataManager(client=client or FakeHistoricalClient([[raw(0), raw(1)]]), clock=lambda: TS)
    item = HistoricalWarmupCoordinator(lifecycle=lifecycle, historical_manager=manager, resolutions=(resolution(),), configuration=config, clock=clock or (lambda: TS))
    return lifecycle, manager, item


def test_constructor_no_fetch_initial_status_factory_duplicates_and_running_required():
    lifecycle, manager, item = coordinator()
    assert item.snapshot().status is HistoricalWarmupStatus.CREATED
    assert manager.snapshot().fetch_count == 0
    assert isinstance(item._lock, type(RLock()))
    with pytest.raises(RuntimeError):
        item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=2))
    created = HistoricalWarmupCoordinatorFactory().create(lifecycle=lifecycle, historical_manager=manager, resolutions=(resolution(),))
    assert isinstance(created, HistoricalWarmupCoordinator)
    with pytest.raises(ValueError):
        HistoricalWarmupCoordinator(lifecycle=lifecycle, historical_manager=manager, resolutions=(resolution(), resolution()), clock=lambda: TS)
    with pytest.raises(ValueError):
        HistoricalWarmupCoordinator(lifecycle=lifecycle, historical_manager=manager, resolutions=(resolution(token=101), resolution(Instrument.BANKNIFTY, 101)), clock=lambda: TS)


def test_warmup_success_empty_partial_error_strict_gap_daily_levels_and_clear():
    previous = [raw(-1440), raw(-1439)]
    current = [raw(0), raw(2)]
    lifecycle, manager, item = coordinator(FakeHistoricalClient([previous, current]))
    lifecycle.start()
    snapshot = item.warm_up(
        start_at=TS,
        end_at=TS + timedelta(minutes=3),
        previous_day_start_at=TS - timedelta(days=1),
        previous_day_end_at=TS - timedelta(days=1, minutes=-2),
    )
    assert snapshot.status is HistoricalWarmupStatus.READY
    assert snapshot.operation_count == 1
    assert snapshot.successful_operation_count == 1
    assert snapshot.total_seeded_candles == 2
    assert snapshot.results[0].daily_ohlc is not None
    runtime_snapshot = lifecycle.orchestrator.snapshot().runtime_snapshots[0]
    assert runtime_snapshot.cpr is not None
    assert runtime_snapshot.camarilla is not None
    assert runtime_snapshot.vwap is None

    strict = HistoricalWarmupConfiguration(strict_gap_validation=True)
    lifecycle2, _, strict_item = coordinator(FakeHistoricalClient([[raw(0), raw(2)]]), strict)
    lifecycle2.start()
    strict_snapshot = strict_item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=3))
    assert strict_snapshot.status is HistoricalWarmupStatus.ERROR
    assert "secret" not in (strict_snapshot.last_error or "")

    lifecycle3, _, empty_item = coordinator(FakeHistoricalClient([[]]))
    lifecycle3.start()
    assert empty_item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=1)).status is HistoricalWarmupStatus.EMPTY
    cleared = item.clear()
    assert cleared.status is HistoricalWarmupStatus.CLEARED
    assert manager.snapshot().fetch_count == 2
    assert lifecycle.orchestrator.status.value == "running"


def test_previous_day_bounds_must_be_supplied_together_and_failures_are_safe():
    lifecycle, _, item = coordinator(FakeHistoricalClient(fail=True))
    lifecycle.start()
    with pytest.raises(ValueError):
        item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=1), previous_day_start_at=TS - timedelta(days=1))
    snapshot = item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=1))
    assert snapshot.status is HistoricalWarmupStatus.ERROR
    assert "{" not in snapshot.last_error
    assert "secret" not in snapshot.last_error


@pytest.mark.parametrize(
    ("clock_value", "expected_error"),
    (
        ("not-a-datetime", TypeError),
        (datetime(2026, 7, 10, 9, 16), ValueError),
        (RuntimeError("startup clock failed {'secret': 'payload'}"), RuntimeError),
    ),
)
def test_warmup_startup_clock_failure_records_error_without_leaving_validating(clock_value, expected_error):
    lifecycle, _, item = coordinator(clock=SequenceClock(clock_value))
    lifecycle.start()

    if isinstance(clock_value, Exception):
        with pytest.raises(expected_error) as exc:
            item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=1))
        assert exc.value is clock_value
    else:
        with pytest.raises(expected_error):
            item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=1))

    snapshot = item.snapshot()
    assert snapshot.status is HistoricalWarmupStatus.ERROR
    assert snapshot.operation_count == 1
    assert snapshot.failed_operation_count == 1
    assert snapshot.successful_operation_count == 0
    assert snapshot.started_at is None
    assert snapshot.results == ()
    assert snapshot.last_error is not None
    assert "{" not in snapshot.last_error
    assert snapshot.status is not HistoricalWarmupStatus.VALIDATING


def test_warmup_completion_clock_failure_records_error_and_preserves_runtime_state():
    clock_error = RuntimeError("completion clock failed {'secret': 'payload'}")
    lifecycle, _, item = coordinator(FakeHistoricalClient([[raw(0)]]), clock=SequenceClock(TS, clock_error))
    lifecycle.start()

    with pytest.raises(RuntimeError) as exc:
        item.warm_up(start_at=TS, end_at=TS + timedelta(minutes=1))

    assert exc.value is clock_error
    snapshot = item.snapshot()
    assert snapshot.status is HistoricalWarmupStatus.ERROR
    assert snapshot.operation_count == 1
    assert snapshot.failed_operation_count == 1
    assert snapshot.successful_operation_count == 0
    assert snapshot.results == ()
    assert snapshot.last_error == "RuntimeError: completion clock failed"
    assert len(lifecycle.orchestrator.get_candle_history("NIFTY")) == 1


def test_warmup_nested_failure_preserves_original_exception_when_error_clock_fails():
    lifecycle, _, item = coordinator(clock=SequenceClock(TS, RuntimeError("error clock failed")))
    lifecycle.start()

    with pytest.raises(ValueError, match="previous-day bounds"):
        item.warm_up(
            start_at=TS,
            end_at=TS + timedelta(minutes=1),
            previous_day_start_at=TS - timedelta(days=1),
        )

    snapshot = item.snapshot()
    assert snapshot.status is HistoricalWarmupStatus.ERROR
    assert snapshot.operation_count == 1
    assert snapshot.failed_operation_count == 1
    assert snapshot.successful_operation_count == 0
    assert snapshot.last_error == "ValueError: previous-day bounds must be supplied together"
    assert snapshot.completed_at is None
