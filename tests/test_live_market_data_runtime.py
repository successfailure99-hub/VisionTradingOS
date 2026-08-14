"""
Tests for live market-data runtime lifecycle.
"""

from datetime import UTC, datetime, timedelta
from threading import RLock

import pytest

from application.bootstrap import ApplicationBootstrap
from application.live_market_data import LiveFeedWatchdogState, LiveMarketDataConfiguration, LiveMarketDataRuntime, LiveMarketDataRuntimeStatus
from brokers.zerodha.auth import ZerodhaCredentials, ZerodhaSessionManager
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaWebSocketStatus, ZerodhaWebSocketManager
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


class FakeAuthClient:
    def set_access_token(self, access_token):
        self.access_token = access_token

    def profile(self):
        return {"user_id": "AB1234"}

    def login_url(self):
        return "https://kite"

    def generate_session(self, request_token, api_secret):
        return {"access_token": "access_token", "user_id": "AB1234"}


class FakeTickerClient:
    def __init__(self):
        self.callbacks = None
        self.connect_calls = 0
        self.close_calls = 0

    def set_callbacks(self, **callbacks):
        self.callbacks = callbacks

    def connect(self, *, threaded=True):
        self.connect_calls += 1

    def close(self):
        self.close_calls += 1

    def subscribe(self, instrument_tokens):
        pass

    def unsubscribe(self, instrument_tokens):
        pass

    def set_mode(self, mode, instrument_tokens):
        pass


def sub(instrument=Instrument.NIFTY, token=101):
    return ZerodhaInstrumentSubscription(token, instrument, Exchange.NSE)


def config(subscription=sub(), **overrides):
    values = {"api_key": "api_key_secret", "subscriptions": (subscription,), "watchdog_interval_seconds": 3600.0}
    values.update(overrides)
    return LiveMarketDataConfiguration(**values)


def auth(expires_at=NOW + timedelta(hours=1)):
    manager = ZerodhaSessionManager(ZerodhaCredentials("api_key", "api_secret"), client=FakeAuthClient(), clock=lambda: NOW)
    authenticated_at = expires_at - timedelta(hours=1) if expires_at <= NOW else NOW
    manager.restore_session(user_id="AB1234", access_token="access_secret", authenticated_at=authenticated_at, expires_at=expires_at)
    return manager


def lifecycle(running=True):
    manager = ApplicationBootstrap().create_application()
    if running:
        manager.start()
    return manager


def runtime(app=None, session=None, configuration=None, ticker=None, clock=None):
    app = app or lifecycle()
    session = session or auth()
    configuration = configuration or config()
    ticker = ticker or FakeTickerClient()
    clock = clock or (lambda: NOW)
    websocket = ZerodhaWebSocketManager(
        api_key=configuration.api_key,
        session=session.session,
        tick_consumer=app.orchestrator.process_tick,
        subscriptions=configuration.subscriptions,
        client=ticker,
        clock=clock,
    )
    return LiveMarketDataRuntime(
        lifecycle=app,
        session_manager=session,
        configuration=configuration,
        websocket_manager=websocket,
        clock=clock,
    ), ticker


def raw_tick(timestamp, *, price=25000.0, volume=100):
    return {
        "instrument_token": 101,
        "last_price": price,
        "exchange_timestamp": timestamp,
        "volume": volume,
    }


def test_validate_requires_running_lifecycle_authenticated_session_and_matching_config():
    stopped, _ = runtime(app=lifecycle(running=False))
    with pytest.raises(RuntimeError):
        stopped.validate()

    expired_session_manager = auth(NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="expired"):
        runtime(session=expired_session_manager)

    mismatch_config = config(sub(Instrument.BANKNIFTY, 102))
    mismatched_runtime, _ = runtime(configuration=mismatch_config)

    with pytest.raises(
        ValueError,
        match="subscription instrument is not configured",
    ):
        mismatched_runtime.validate()


def test_successful_validate_start_stop_restart_and_counters():
    subject, ticker = runtime()

    assert subject.status is LiveMarketDataRuntimeStatus.CREATED
    assert subject.validate().status is LiveMarketDataRuntimeStatus.READY
    assert ticker.connect_calls == 0
    assert subject.start().status is LiveMarketDataRuntimeStatus.STARTING
    assert ticker.connect_calls == 1
    assert subject.watchdog_worker_running is True
    assert subject.start().start_count == 1
    assert subject.watchdog_worker_start_count == 1
    ticker.callbacks["on_connect"](None, {})
    assert subject.snapshot().status is LiveMarketDataRuntimeStatus.RUNNING
    assert subject.stop().status is LiveMarketDataRuntimeStatus.STOPPED
    assert ticker.close_calls == 1
    assert subject.watchdog_worker_running is False
    assert subject.stop().stop_count == 1
    assert subject.lifecycle.is_running() is True
    assert subject.session_manager.is_authenticated() is True

    websocket = subject.websocket_manager
    subject.restart()
    assert subject.websocket_manager is websocket
    assert subject.websocket_manager.registry.tokens() == (101,)


def test_websocket_status_mapping_and_snapshot_safety():
    subject, ticker = runtime()
    subject.validate()
    subject.start()
    assert subject.snapshot().status is LiveMarketDataRuntimeStatus.STARTING
    ticker.callbacks["on_reconnect"](None, 1)
    assert subject.snapshot().status is LiveMarketDataRuntimeStatus.STARTING
    ticker.callbacks["on_noreconnect"](None)
    snapshot = subject.snapshot()
    assert snapshot.status is LiveMarketDataRuntimeStatus.ERROR
    assert "api_key_secret" not in repr(snapshot)
    assert "access_secret" not in repr(snapshot)
    assert isinstance(subject._lock, type(RLock()))


def test_start_errors_are_redacted():
    subject, ticker = runtime()

    def failing_connect(*, threaded=True):
        raise RuntimeError("bad api_key_secret access_secret")

    ticker.connect = failing_connect
    with pytest.raises(RuntimeError):
        subject.start()

    assert "api_key_secret" not in subject.snapshot().last_error
    assert "access_secret" not in subject.snapshot().last_error


def test_watchdog_detects_silent_stall_drives_retry_and_requires_fresh_tick(tmp_path):
    current = [datetime(2026, 7, 15, 4, 0, tzinfo=UTC)]
    subject, ticker = runtime(
        session=auth(current[0] + timedelta(hours=1)),
        configuration=config(stale_data_seconds=120, feed_trace_path=tmp_path / "feed.jsonl"),
        clock=lambda: current[0],
    )
    subject.start()
    ticker.callbacks["on_connect"](None, {})

    waiting = subject.poll_watchdog()
    assert waiting.watchdog_state is LiveFeedWatchdogState.WAITING_FIRST_TICK
    assert waiting.watchdog_blocks_decisions is False

    ticker.callbacks["on_ticks"](None, (raw_tick(current[0], price=25000.0, volume=100),))
    healthy = subject.poll_watchdog()
    assert healthy.watchdog_state is LiveFeedWatchdogState.HEALTHY

    current[0] = current[0] + timedelta(seconds=121)
    stale = subject.poll_watchdog()
    assert stale.watchdog_state is LiveFeedWatchdogState.RECONNECT_SCHEDULED
    assert stale.watchdog_blocks_decisions is True
    assert subject.websocket_manager.snapshot().status is ZerodhaWebSocketStatus.RECONNECT_WAIT
    assert ticker.close_calls == 1

    before_due = subject.poll_watchdog()
    assert ticker.connect_calls == 1
    assert before_due.watchdog_state is LiveFeedWatchdogState.RECONNECT_SCHEDULED

    current[0] = current[0] + timedelta(seconds=2)
    reconnecting = subject.poll_watchdog()
    assert ticker.connect_calls == 2
    assert reconnecting.watchdog_state is LiveFeedWatchdogState.RECONNECTING
    ticker.callbacks["on_connect"](None, {})

    verifying = subject.poll_watchdog()
    assert verifying.watchdog_state is LiveFeedWatchdogState.VERIFYING_FRESH_TICK
    assert verifying.watchdog_blocks_decisions is True

    ticker.callbacks["on_ticks"](None, (raw_tick(current[0], price=25001.0, volume=100),))
    recovered = subject.poll_watchdog()
    assert recovered.watchdog_state is LiveFeedWatchdogState.RECOVERED
    assert recovered.watchdog_blocks_decisions is False

    trace = (tmp_path / "feed.jsonl").read_text(encoding="utf-8")
    assert "STALL_DETECTED" in trace
    assert "RECONNECT_SCHEDULED" in trace
    assert "FRESH_TICK_CONFIRMED" in trace
    assert "api_key_secret" not in trace
    assert "access_secret" not in trace


def test_watchdog_uses_successfully_delivered_nifty_timestamp_not_other_tokens(tmp_path):
    current = [datetime(2026, 7, 15, 4, 0, tzinfo=UTC)]
    delivered = []
    app = lifecycle()
    session = auth(current[0] + timedelta(hours=1))
    configuration = config(
        subscriptions=(sub(Instrument.NIFTY, 101), sub(Instrument.BANKNIFTY, 102)),
        stale_data_seconds=120,
        feed_trace_path=tmp_path / "feed.jsonl",
    )
    ticker = FakeTickerClient()
    websocket = ZerodhaWebSocketManager(
        api_key=configuration.api_key,
        session=session.session,
        tick_consumer=delivered.append,
        subscriptions=configuration.subscriptions,
        client=ticker,
        clock=lambda: current[0],
    )
    subject = LiveMarketDataRuntime(
        lifecycle=app,
        session_manager=session,
        configuration=configuration,
        websocket_manager=websocket,
        clock=lambda: current[0],
    )
    websocket.connect()
    ticker.callbacks["on_connect"](None, {})

    ticker.callbacks["on_ticks"](None, (raw_tick(current[0], price=52000.0, volume=100) | {"instrument_token": 102},))
    waiting = subject.poll_watchdog()

    assert delivered
    assert websocket.snapshot().last_delivered_market_timestamp(102) == current[0]
    assert websocket.snapshot().last_delivered_market_timestamp(101) is None
    assert waiting.watchdog_state is LiveFeedWatchdogState.WAITING_FIRST_TICK
    assert waiting.last_delivered_market_timestamp is None


def test_watchdog_treats_normalized_but_undelivered_nifty_as_stale(tmp_path):
    current = [datetime(2026, 7, 15, 4, 0, tzinfo=UTC)]
    should_fail = [False]

    def consumer(tick):
        if should_fail[0]:
            raise RuntimeError("runtime consumer unavailable")

    subject, ticker = runtime(
        session=auth(current[0] + timedelta(hours=1)),
        configuration=config(stale_data_seconds=120, feed_trace_path=tmp_path / "feed.jsonl"),
        clock=lambda: current[0],
    )
    subject.websocket_manager._tick_consumer = consumer
    subject.start()
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (raw_tick(current[0], price=25000.0, volume=100),))
    assert subject.poll_watchdog().watchdog_state is LiveFeedWatchdogState.HEALTHY

    should_fail[0] = True
    current[0] = current[0] + timedelta(seconds=121)
    ticker.callbacks["on_ticks"](None, (raw_tick(current[0], price=25001.0, volume=101),))
    stale = subject.poll_watchdog()

    assert subject.websocket_manager.snapshot().last_tick_at == current[0]
    assert stale.watchdog_state is LiveFeedWatchdogState.RECONNECT_SCHEDULED
    assert stale.last_delivered_market_timestamp == datetime(2026, 7, 15, 4, 0, tzinfo=UTC)


def test_watchdog_worker_drives_retry_without_dashboard_refresh(tmp_path):
    current = [datetime(2026, 7, 15, 4, 0, tzinfo=UTC)]
    subject, ticker = runtime(
        session=auth(current[0] + timedelta(hours=1)),
        configuration=config(stale_data_seconds=120, feed_trace_path=tmp_path / "feed.jsonl"),
        clock=lambda: current[0],
    )
    subject.start()
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (raw_tick(current[0], price=25000.0, volume=100),))

    subject._watchdog_worker.tick_once()
    current[0] = current[0] + timedelta(seconds=121)
    subject._watchdog_worker.tick_once()

    assert subject.snapshot().watchdog_state is LiveFeedWatchdogState.RECONNECT_SCHEDULED
    assert subject.websocket_manager.snapshot().status is ZerodhaWebSocketStatus.RECONNECT_WAIT
    assert ticker.connect_calls == 1

    current[0] = current[0] + timedelta(seconds=2)
    subject._watchdog_worker.tick_once()

    assert ticker.connect_calls == 2
    assert subject.snapshot().watchdog_state is LiveFeedWatchdogState.RECONNECTING


def test_watchdog_does_not_recover_outside_active_session(tmp_path):
    current = [datetime(2026, 7, 18, 4, 0, tzinfo=UTC)]
    subject, ticker = runtime(
        session=auth(current[0] + timedelta(hours=1)),
        configuration=config(stale_data_seconds=1, feed_trace_path=tmp_path / "feed.jsonl"),
        clock=lambda: current[0],
    )
    subject.start()
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (raw_tick(datetime(2026, 7, 15, 4, 0, tzinfo=UTC)),))

    snapshot = subject.poll_watchdog()
    assert snapshot.watchdog_state is LiveFeedWatchdogState.MARKET_CLOSED
    assert subject.websocket_manager.snapshot().status is ZerodhaWebSocketStatus.CONNECTED
    assert ticker.connect_calls == 1
