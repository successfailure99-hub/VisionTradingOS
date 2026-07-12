"""
Tests for DashboardApplication live runtime ownership.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from application import ApplicationBootstrap, RuntimeStatus
from application.live_market_data import (
    LiveMarketDataConfiguration,
    LiveMarketDataRuntime,
    LiveMarketDataRuntimeFactory,
    LiveMarketDataRuntimeSnapshot,
    LiveMarketDataRuntimeStatus,
)
from brokers.zerodha.auth import ZerodhaCredentials, ZerodhaSessionManager
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from dashboard.application import DashboardApplication


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def app():
    return QApplication.instance() or QApplication([])


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
        self.close_calls = 0
        self.submitted_orders = []

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


class FakeLiveRuntime(LiveMarketDataRuntime):
    def __init__(self, status=LiveMarketDataRuntimeStatus.RUNNING, fail_stop=False):
        self._status = status
        self.fail_stop = fail_stop
        self.stop_calls = 0
        self.start_calls = 0
        self.session_authenticated = True
        self.subscriptions = (101,)

    @property
    def status(self):
        return self._status

    def snapshot(self):
        return LiveMarketDataRuntimeSnapshot(
            status=self._status,
            ready=self._status in {
                LiveMarketDataRuntimeStatus.READY,
                LiveMarketDataRuntimeStatus.STARTING,
                LiveMarketDataRuntimeStatus.RUNNING,
                LiveMarketDataRuntimeStatus.STOPPING,
            },
            running=self._status is LiveMarketDataRuntimeStatus.RUNNING,
            configured_instruments=(),
            configured_tokens=(),
            websocket=None,
            start_count=0,
            stop_count=self.stop_calls,
            last_started_at=None,
            last_stopped_at=None,
            last_error=None,
        )

    def start(self):
        self.start_calls += 1
        return self.snapshot()

    def stop(self):
        self.stop_calls += 1
        if self.fail_stop:
            raise RuntimeError("live stop failed")
        self._status = LiveMarketDataRuntimeStatus.STOPPED
        return self.snapshot()


def test_existing_offline_construction_and_run_behavior_remain_valid(monkeypatch):
    app()
    lifecycle = ApplicationBootstrap().create_application()
    dashboard = DashboardApplication(lifecycle)
    monkeypatch.setattr(dashboard._qt_app, "exec", lambda: 0)
    assert dashboard.live_market_data_runtime is None
    assert dashboard.run() == 0
    assert lifecycle.status is RuntimeStatus.STOPPED


def test_supplied_runtime_is_reused_passed_to_window_and_not_auto_started():
    app()
    lifecycle = ApplicationBootstrap().create_application()
    runtime = FakeLiveRuntime(LiveMarketDataRuntimeStatus.CREATED)
    dashboard = DashboardApplication(lifecycle, live_market_data_runtime=runtime)
    assert dashboard.live_market_data_runtime is runtime
    assert dashboard.main_window._live_market_data_runtime is runtime
    assert runtime.start_calls == 0
    with pytest.raises(TypeError):
        DashboardApplication(lifecycle, live_market_data_runtime=object())


def test_shutdown_stops_refresh_active_live_runtime_then_lifecycle_and_is_idempotent():
    app()
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    runtime = FakeLiveRuntime(LiveMarketDataRuntimeStatus.RUNNING)
    dashboard = DashboardApplication(lifecycle, live_market_data_runtime=runtime)
    dashboard.main_window.start_refresh()
    dashboard.shutdown()
    dashboard.shutdown()
    assert not dashboard.main_window._timer.isActive()
    assert runtime.stop_calls == 1
    assert lifecycle.status is RuntimeStatus.STOPPED
    assert runtime.session_authenticated is True
    assert runtime.subscriptions == (101,)


def test_stopped_runtime_is_not_redundantly_stopped():
    app()
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    runtime = FakeLiveRuntime(LiveMarketDataRuntimeStatus.STOPPED)
    DashboardApplication(lifecycle, live_market_data_runtime=runtime).shutdown()
    assert runtime.stop_calls == 0
    assert lifecycle.status is RuntimeStatus.STOPPED


def test_live_stop_failure_still_attempts_lifecycle_stop_and_preserves_first_exception():
    app()
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    runtime = FakeLiveRuntime(LiveMarketDataRuntimeStatus.RUNNING, fail_stop=True)
    dashboard = DashboardApplication(lifecycle, live_market_data_runtime=runtime)
    with pytest.raises(RuntimeError, match="live stop failed"):
        dashboard.shutdown()
    assert lifecycle.status is RuntimeStatus.STOPPED


def test_end_to_end_offscreen_dashboard_observes_live_runtime_without_credentials_or_orders():
    app()
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    auth = ZerodhaSessionManager(ZerodhaCredentials("api_key", "api_secret"), client=FakeAuthClient(), clock=lambda: NOW)
    auth.restore_session(
        user_id="AB1234",
        access_token="access_token",
        authenticated_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    ticker = FakeTickerClient()
    configuration = LiveMarketDataConfiguration(
        "api_key",
        (ZerodhaInstrumentSubscription(101, Instrument.NIFTY, Exchange.NSE),),
        auto_connect=False,
    )
    runtime = LiveMarketDataRuntimeFactory(clock=lambda: NOW).create(
        lifecycle=lifecycle,
        session_manager=auth,
        configuration=configuration,
        ticker_client=ticker,
    )
    dashboard = DashboardApplication(lifecycle, live_market_data_runtime=runtime)

    assert ticker.connect_calls == 0
    runtime.validate()
    runtime.start()
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](
        None,
        (
            {
                "instrument_token": 101,
                "last_price": 25000.0,
                "exchange_timestamp": NOW,
                "volume": 10,
                "depth": {"buy": [{"price": 24999.0}], "sell": [{"price": 25001.0}]},
            },
        ),
    )
    view = dashboard.main_window.refresh()

    assert view.live_market_data.runtime_status == "Running"
    assert view.live_market_data.connected is True
    assert view.live_market_data.subscription_count == 1
    assert view.live_market_data.raw_tick_count == 1
    assert view.live_market_data.normalized_tick_count == 1
    assert view.live_market_data.delivered_tick_count == 1
    assert dashboard.main_window._instrument_panels["NIFTY"]["market"]._labels["Last"].text() == "25000.00"
    assert view.runtime.safety_mode == "Analysis Only"
    assert view.runtime.broker_mode == "Dry Run"
    rendered = repr(view)
    assert "api_secret" not in rendered
    assert "access_token" not in rendered
    assert ticker.submitted_orders == []

    dashboard.shutdown()
    assert runtime.status is LiveMarketDataRuntimeStatus.STOPPED
    assert lifecycle.status is RuntimeStatus.STOPPED
    assert auth.is_authenticated() is True
