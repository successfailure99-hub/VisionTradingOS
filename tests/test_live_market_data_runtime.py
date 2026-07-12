"""
Tests for live market-data runtime lifecycle.
"""

from datetime import UTC, datetime, timedelta
from threading import RLock

import pytest

from application.bootstrap import ApplicationBootstrap
from application.live_market_data import LiveMarketDataConfiguration, LiveMarketDataRuntime, LiveMarketDataRuntimeStatus
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


def config(subscription=sub()):
    return LiveMarketDataConfiguration("api_key_secret", (subscription,))


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


def runtime(app=None, session=None, configuration=None, ticker=None):
    app = app or lifecycle()
    session = session or auth()
    configuration = configuration or config()
    ticker = ticker or FakeTickerClient()
    websocket = ZerodhaWebSocketManager(
        api_key=configuration.api_key,
        session=session.session,
        tick_consumer=app.orchestrator.process_tick,
        subscriptions=configuration.subscriptions,
        client=ticker,
        clock=lambda: NOW,
    )
    return LiveMarketDataRuntime(
        lifecycle=app,
        session_manager=session,
        configuration=configuration,
        websocket_manager=websocket,
        clock=lambda: NOW,
    ), ticker


def test_validate_requires_running_lifecycle_authenticated_session_and_matching_config():
    stopped, _ = runtime(app=lifecycle(running=False))
    with pytest.raises(RuntimeError):
        stopped.validate()

    expired_session = auth(NOW - timedelta(seconds=1))
    with pytest.raises(RuntimeError):
        runtime(session=expired_session)

    mismatch_config = config(sub(Instrument.BANKNIFTY, 102))
    with pytest.raises(ValueError):
        runtime(configuration=mismatch_config)


def test_successful_validate_start_stop_restart_and_counters():
    subject, ticker = runtime()

    assert subject.status is LiveMarketDataRuntimeStatus.CREATED
    assert subject.validate().status is LiveMarketDataRuntimeStatus.READY
    assert ticker.connect_calls == 0
    assert subject.start().status is LiveMarketDataRuntimeStatus.STARTING
    assert ticker.connect_calls == 1
    assert subject.start().start_count == 1
    ticker.callbacks["on_connect"](None, {})
    assert subject.snapshot().status is LiveMarketDataRuntimeStatus.RUNNING
    assert subject.stop().status is LiveMarketDataRuntimeStatus.STOPPED
    assert ticker.close_calls == 1
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
