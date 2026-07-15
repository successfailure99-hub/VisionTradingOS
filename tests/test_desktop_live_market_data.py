"""
Desktop live market-data composition tests.
"""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import desktop_main
from application.desktop_live_data import (
    DesktopLiveDataConfigurationError,
    create_dashboard_application,
    create_desktop_live_runtime,
    create_zerodha_session_manager,
    load_desktop_live_configuration,
)
from application.live_market_data import LiveMarketDataRuntimeFactory, LiveMarketDataRuntimeStatus
from brokers.zerodha.auth import ZerodhaCredentials, ZerodhaSessionManager
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 15, 9, 15, tzinfo=UTC)


def qt_app():
    return QApplication.instance() or QApplication([])


def live_env(**overrides):
    env = {
        "LIVE_MARKET_DATA_ENABLED": "true",
        "LIVE_MARKET_DATA_AUTO_CONNECT": "true",
        "ZERODHA_API_KEY": "desktop_api_key",
        "ZERODHA_API_SECRET": "desktop_api_secret",
        "ZERODHA_ACCESS_TOKEN": "desktop_access_token",
        "NIFTY_INSTRUMENT_TOKEN": "101",
        "BANKNIFTY_INSTRUMENT_TOKEN": "102",
        "SENSEX_INSTRUMENT_TOKEN": "103",
    }
    env.update(overrides)
    return env


class FakeAuthClient:
    def __init__(self, api_key, *, user_id="AB1234", fail_profile=False):
        self.api_key = api_key
        self.user_id = user_id
        self.fail_profile = fail_profile
        self.access_token = None

    def login_url(self):
        return "https://kite.example/login"

    def generate_session(self, request_token, api_secret):
        return {"access_token": "generated_access_token", "user_id": self.user_id}

    def set_access_token(self, access_token):
        self.access_token = access_token

    def profile(self):
        if self.fail_profile:
            raise RuntimeError(f"bad {self.api_key} {self.access_token}")
        return {"user_id": self.user_id}


class FakeTickerClient:
    def __init__(self):
        self.callbacks = {}
        self.connect_calls = 0
        self.close_calls = 0
        self.subscriptions = []
        self.modes = []
        self.submitted_orders = []

    def set_callbacks(self, **callbacks):
        self.callbacks = callbacks

    def connect(self, *, threaded=True):
        self.connect_calls += 1

    def close(self):
        self.close_calls += 1

    def subscribe(self, instrument_tokens):
        self.subscriptions.append(tuple(instrument_tokens))

    def unsubscribe(self, instrument_tokens):
        pass

    def set_mode(self, mode, instrument_tokens):
        self.modes.append((mode, tuple(instrument_tokens)))


def auth_factory(api_key):
    return FakeAuthClient(api_key)


def test_live_data_disabled_starts_without_runtime_and_unavailable_dashboard_view():
    qt_app()
    dashboard = create_dashboard_application(environ={"LIVE_MARKET_DATA_ENABLED": "false"})
    assert dashboard.live_market_data_runtime is None
    view = dashboard.main_window.refresh()
    assert view.live_market_data.available is False
    assert view.live_market_data.runtime_status == "Live market data not configured"
    dashboard.shutdown()


@pytest.mark.parametrize("value, expected", (("true", True), ("false", False)))
def test_enabled_flag_parsing(value, expected):
    env = live_env(LIVE_MARKET_DATA_ENABLED=value) if expected else {"LIVE_MARKET_DATA_ENABLED": value}
    settings = load_desktop_live_configuration(env)
    assert settings.enabled is expected


@pytest.mark.parametrize("name", ("LIVE_MARKET_DATA_ENABLED", "LIVE_MARKET_DATA_AUTO_CONNECT"))
def test_invalid_boolean_rejection(name):
    env = live_env(**{name: "yes"})
    with pytest.raises(DesktopLiveDataConfigurationError, match=f"{name} must be 'true' or 'false'"):
        load_desktop_live_configuration(env)


@pytest.mark.parametrize(
    "missing_name",
    (
        "ZERODHA_API_KEY",
        "ZERODHA_API_SECRET",
        "ZERODHA_ACCESS_TOKEN",
        "NIFTY_INSTRUMENT_TOKEN",
        "BANKNIFTY_INSTRUMENT_TOKEN",
        "SENSEX_INSTRUMENT_TOKEN",
    ),
)
def test_enabled_configuration_lists_missing_variables_only(missing_name):
    env = live_env()
    env[missing_name] = ""
    with pytest.raises(DesktopLiveDataConfigurationError) as error:
        load_desktop_live_configuration(env)
    message = str(error.value)
    assert missing_name in message
    assert "desktop_api_secret" not in message
    assert "desktop_access_token" not in message


@pytest.mark.parametrize("value", ("0", "-1", "abc"))
def test_invalid_integer_tokens_are_rejected(value):
    with pytest.raises(DesktopLiveDataConfigurationError, match="NIFTY_INSTRUMENT_TOKEN must be a positive integer"):
        load_desktop_live_configuration(live_env(NIFTY_INSTRUMENT_TOKEN=value))


def test_duplicate_tokens_are_rejected():
    with pytest.raises(DesktopLiveDataConfigurationError, match="duplicate instrument token|Instrument tokens must be unique"):
        load_desktop_live_configuration(live_env(BANKNIFTY_INSTRUMENT_TOKEN="101"))


def test_supported_subscriptions_map_correctly_and_secrets_are_redacted_from_repr():
    settings = load_desktop_live_configuration(live_env())
    assert [(sub.instrument, sub.exchange, sub.mode.value, sub.instrument_token) for sub in settings.subscriptions] == [
        (Instrument.NIFTY, Exchange.NSE, "full", 101),
        (Instrument.BANKNIFTY, Exchange.NSE, "full", 102),
        (Instrument.SENSEX, Exchange.BSE, "full", 103),
    ]
    rendered = repr(settings)
    assert "desktop_api_key" not in rendered
    assert "desktop_api_secret" not in rendered
    assert "desktop_access_token" not in rendered


def test_session_restore_uses_existing_manager_and_redacts_authentication_errors():
    settings = load_desktop_live_configuration(live_env())

    def failing_factory(api_key):
        return FakeAuthClient(api_key, fail_profile=True)

    with pytest.raises(DesktopLiveDataConfigurationError) as error:
        create_zerodha_session_manager(settings, auth_client_factory=failing_factory, clock=lambda: NOW)

    message = str(error.value)
    assert "Zerodha authentication failed" in message
    assert "desktop_api_key" not in message
    assert "desktop_api_secret" not in message
    assert "desktop_access_token" not in message


def test_authenticated_session_required_and_expired_session_rejected():
    settings = load_desktop_live_configuration(live_env(LIVE_MARKET_DATA_AUTO_CONNECT="false"))
    dashboard = create_dashboard_application(
        environ={"LIVE_MARKET_DATA_ENABLED": "false"},
    )
    with pytest.raises(DesktopLiveDataConfigurationError, match="authenticated Zerodha session is required"):
        create_desktop_live_runtime(lifecycle=dashboard.lifecycle, settings=settings, session_manager=None)

    expired = ZerodhaSessionManager(ZerodhaCredentials("desktop_api_key", "desktop_api_secret"), client=FakeAuthClient("desktop_api_key"), clock=lambda: NOW)
    expired.restore_session(
        user_id="AB1234",
        access_token="desktop_access_token",
        authenticated_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(hours=1),
    )
    with pytest.raises(DesktopLiveDataConfigurationError, match="expired"):
        create_desktop_live_runtime(
            lifecycle=dashboard.lifecycle,
            settings=settings,
            session_manager=expired,
            ticker_client=FakeTickerClient(),
        )
    dashboard.shutdown()


def test_runtime_factory_receives_lifecycle_session_configuration_and_dashboard_receives_runtime():
    qt_app()
    ticker = FakeTickerClient()
    dashboard = create_dashboard_application(
        environ=live_env(LIVE_MARKET_DATA_AUTO_CONNECT="false"),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        ticker_client=ticker,
        clock=lambda: NOW,
    )
    runtime = dashboard.live_market_data_runtime
    assert runtime is not None
    assert runtime.lifecycle is dashboard.lifecycle
    assert runtime.session_manager.is_authenticated() is True
    assert runtime.configuration.auto_connect is False
    assert runtime.configuration.subscriptions == runtime.websocket_manager.registry.all()
    assert dashboard.main_window._live_market_data_runtime is runtime
    assert ticker.connect_calls == 0
    dashboard.shutdown()


def test_auto_connect_starts_runtime_exactly_once_and_run_does_not_duplicate_start(monkeypatch):
    qt_app()
    ticker = FakeTickerClient()
    dashboard = create_dashboard_application(
        environ=live_env(),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        ticker_client=ticker,
        clock=lambda: NOW,
    )
    assert ticker.connect_calls == 1
    monkeypatch.setattr(dashboard._qt_app, "exec", lambda: 0)
    assert dashboard.run() == 0
    assert ticker.connect_calls == 1


def test_configured_mode_exposes_three_subscription_rows_and_preserves_safety_modes():
    qt_app()
    dashboard = create_dashboard_application(
        environ=live_env(LIVE_MARKET_DATA_AUTO_CONNECT="false"),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        ticker_client=FakeTickerClient(),
        clock=lambda: NOW,
    )
    view = dashboard.main_window.refresh()
    assert view.live_market_data.available is True
    assert view.live_market_data.subscription_count == 3
    assert [row.instrument for row in view.live_market_data.subscription_rows] == ["NIFTY", "BANKNIFTY", "SENSEX"]
    assert view.runtime.broker_mode == "Dry Run"
    assert view.runtime.safety_mode == "Analysis Only"
    dashboard.shutdown()


def test_tick_delivery_reaches_orchestrator_and_rejected_tick_sets_safe_error_state():
    qt_app()
    ticker = FakeTickerClient()
    dashboard = create_dashboard_application(
        environ=live_env(),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        ticker_client=ticker,
        clock=lambda: NOW,
    )
    runtime = dashboard.live_market_data_runtime
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
            {"instrument_token": 999, "last_price": 1.0, "exchange_timestamp": NOW},
        ),
    )
    view = dashboard.main_window.refresh()
    assert view.markets[0].last_price == 25000.0
    snapshot = runtime.snapshot()
    assert snapshot.websocket.raw_tick_count == 2
    assert snapshot.websocket.delivered_tick_count == 1
    assert snapshot.websocket.rejected_tick_count == 1
    assert "desktop_api_key" not in (snapshot.websocket.last_error or "")
    assert "desktop_access_token" not in (snapshot.websocket.last_error or "")
    assert ticker.submitted_orders == []
    dashboard.shutdown()


def test_shutdown_stops_runtime_once_and_is_idempotent():
    qt_app()
    ticker = FakeTickerClient()
    dashboard = create_dashboard_application(
        environ=live_env(),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        ticker_client=ticker,
        clock=lambda: NOW,
    )
    ticker.callbacks["on_connect"](None, {})
    dashboard.shutdown()
    dashboard.shutdown()
    assert ticker.close_calls == 1
    assert dashboard.live_market_data_runtime.status is LiveMarketDataRuntimeStatus.STOPPED


def test_desktop_main_importable_returns_integer_for_offline_and_sanitized_failure(monkeypatch, capsys):
    qt_app()
    monkeypatch.setenv("LIVE_MARKET_DATA_ENABLED", "false")
    with patch("desktop_main.create_dashboard_application") as create:
        dashboard = create_dashboard_application(environ={"LIVE_MARKET_DATA_ENABLED": "false"})
        create.return_value = dashboard
        monkeypatch.setattr(dashboard, "run", lambda: 0)
        assert desktop_main.main() == 0
        dashboard.shutdown()

    monkeypatch.setenv("LIVE_MARKET_DATA_ENABLED", "true")
    with patch("desktop_main.create_dashboard_application", side_effect=DesktopLiveDataConfigurationError("Missing environment variables: ZERODHA_API_KEY")):
        assert desktop_main.main() == 1
    assert "ZERODHA_API_KEY" in capsys.readouterr().out
