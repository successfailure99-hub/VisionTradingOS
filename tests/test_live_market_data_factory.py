"""
Tests for live market-data runtime factory.
"""

from datetime import UTC, datetime, timedelta

import pytest

from application.bootstrap import ApplicationBootstrap
from application.live_market_data import LiveMarketDataConfiguration, LiveMarketDataRuntimeFactory, LiveMarketDataRuntimeStatus
from brokers.zerodha.auth import ZerodhaCredentials, ZerodhaSessionManager
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaWebSocketManager
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


class FakeAuthClient:
    def login_url(self):
        return "https://kite"

    def generate_session(self, request_token, api_secret):
        return {"access_token": "access_token", "user_id": "AB1234"}

    def set_access_token(self, access_token):
        self.access_token = access_token

    def profile(self):
        return {"user_id": "AB1234"}


class FakeTickerClient:
    def __init__(self):
        self.callbacks = None
        self.connect_calls = 0

    def set_callbacks(self, **callbacks):
        self.callbacks = callbacks

    def connect(self, *, threaded=True):
        self.connect_calls += 1

    def close(self):
        pass

    def subscribe(self, instrument_tokens):
        pass

    def unsubscribe(self, instrument_tokens):
        pass

    def set_mode(self, mode, instrument_tokens):
        pass


def subscription():
    return ZerodhaInstrumentSubscription(101, Instrument.NIFTY, Exchange.NSE)


def configuration(auto_connect=False):
    return LiveMarketDataConfiguration("api_key", (subscription(),), auto_connect=auto_connect)


def session_manager(expires_at=NOW + timedelta(hours=1)):
    manager = ZerodhaSessionManager(ZerodhaCredentials("api_key", "api_secret"), client=FakeAuthClient(), clock=lambda: NOW)
    authenticated_at = expires_at - timedelta(hours=1) if expires_at <= NOW else NOW
    manager.restore_session(user_id="AB1234", access_token="access_token", authenticated_at=authenticated_at, expires_at=expires_at)
    return manager


def lifecycle(running=True):
    manager = ApplicationBootstrap().create_application()
    if running:
        manager.start()
    return manager


def test_factory_validates_inputs_and_requires_authenticated_session():
    factory = LiveMarketDataRuntimeFactory(clock=lambda: NOW)

    with pytest.raises(TypeError):
        factory.create(lifecycle=object(), session_manager=session_manager(), configuration=configuration())
    with pytest.raises(TypeError):
        factory.create(lifecycle=lifecycle(), session_manager=object(), configuration=configuration())
    with pytest.raises(TypeError):
        factory.create(lifecycle=lifecycle(), session_manager=session_manager(), configuration=object())

    unauthenticated = ZerodhaSessionManager(ZerodhaCredentials("api_key", "api_secret"), client=FakeAuthClient(), clock=lambda: NOW)
    with pytest.raises(RuntimeError):
        factory.create(lifecycle=lifecycle(), session_manager=unauthenticated, configuration=configuration())
    with pytest.raises(RuntimeError):
        factory.create(lifecycle=lifecycle(), session_manager=session_manager(NOW - timedelta(seconds=1)), configuration=configuration())


def test_factory_reuses_supplied_objects_and_does_not_auto_connect_by_default():
    ticker = FakeTickerClient()
    app_lifecycle = lifecycle()
    auth = session_manager()

    runtime = LiveMarketDataRuntimeFactory(clock=lambda: NOW).create(
        lifecycle=app_lifecycle,
        session_manager=auth,
        configuration=configuration(),
        ticker_client=ticker,
    )

    assert runtime.lifecycle is app_lifecycle
    assert runtime.session_manager is auth
    assert runtime.websocket_manager.registry.tokens() == (101,)
    assert ticker.connect_calls == 0
    assert runtime.status is LiveMarketDataRuntimeStatus.CREATED


def test_factory_auto_connect_validates_and_connects_without_stopping_lifecycle():
    ticker = FakeTickerClient()
    app_lifecycle = lifecycle()

    runtime = LiveMarketDataRuntimeFactory(clock=lambda: NOW).create(
        lifecycle=app_lifecycle,
        session_manager=session_manager(),
        configuration=configuration(auto_connect=True),
        ticker_client=ticker,
    )

    assert runtime.status is LiveMarketDataRuntimeStatus.STARTING
    assert ticker.connect_calls == 1
    assert app_lifecycle.is_running() is True


def test_factory_creates_exactly_one_websocket_manager_and_uses_process_tick_adapter():
    created = []

    def websocket_factory(**kwargs):
        manager = ZerodhaWebSocketManager(**kwargs)
        created.append(manager)
        return manager

    app_lifecycle = lifecycle()
    runtime = LiveMarketDataRuntimeFactory(websocket_manager_factory=websocket_factory, clock=lambda: NOW).create(
        lifecycle=app_lifecycle,
        session_manager=session_manager(),
        configuration=configuration(),
        ticker_client=FakeTickerClient(),
    )

    assert len(created) == 1
    assert runtime.websocket_manager is created[0]
    assert runtime.lifecycle.orchestrator is app_lifecycle.orchestrator
