"""
Desktop live market-data composition tests.
"""

import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
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
from application.reference_data_bootstrap import resolve_reference_bootstrap_bounds
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
        "LIVE_FUTURES_VWAP_ENABLED": "false",
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
        self.unsubscriptions = []
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
        self.unsubscriptions.append(tuple(instrument_tokens))

    def set_mode(self, mode, instrument_tokens):
        self.modes.append((mode, tuple(instrument_tokens)))


class FailingSubscribeTickerClient(FakeTickerClient):
    def subscribe(self, instrument_tokens):
        self.subscriptions.append(tuple(instrument_tokens))
        raise RuntimeError("subscription failed with desktop_access_token")


class FakeHistoricalClient:
    def __init__(self):
        self.calls = []

    def historical_data(self, **kwargs):
        self.calls.append(kwargs)
        start = kwargs["from_date"]
        return [
            dict(date=start, open=100.0, high=103.0, low=99.0, close=101.0, volume=10),
            dict(date=start + timedelta(minutes=1), open=101.0, high=104.0, low=100.0, close=102.0, volume=10),
        ]


class FakeInstrumentClient:
    def __init__(self, records):
        self.records = tuple(records)
        self.calls = []

    def instruments(self, exchange=None):
        self.calls.append(exchange)
        return [record for record in self.records if exchange is None or record.get("exchange") == exchange]


def auth_factory(api_key):
    return FakeAuthClient(api_key)


def historical_factory_factory(store):
    def factory(*, api_key, access_token):
        client = FakeHistoricalClient()
        store.append(client)
        return client

    return factory


def instrument_factory_factory(store, records):
    def factory(*, api_key, access_token):
        client = FakeInstrumentClient(records)
        store.append(client)
        return client

    return factory


def futures_records(*, invalid_nifty_exchange_token=None):
    july = datetime(2026, 7, 30, tzinfo=UTC).date()
    records = []
    if invalid_nifty_exchange_token is not None:
        records.append(
            {
                "instrument_token": 299,
                "exchange_token": invalid_nifty_exchange_token,
                "tradingsymbol": "NIFTY26JULBADFUT",
                "name": "NIFTY",
                "exchange": "NFO",
                "segment": "NFO-FUT",
                "instrument_type": "FUT",
                "expiry": july,
            }
        )
    records.extend(
        [
            {
                "instrument_token": 201,
                "exchange_token": 1201,
                "tradingsymbol": "NIFTY26JULFUT",
                "name": "NIFTY",
                "exchange": "NFO",
                "segment": "NFO-FUT",
                "instrument_type": "FUT",
                "expiry": july,
            },
            {
                "instrument_token": 202,
                "exchange_token": 1202,
                "tradingsymbol": "BANKNIFTY26JULFUT",
                "name": "BANKNIFTY",
                "exchange": "NFO",
                "segment": "NFO-FUT",
                "instrument_type": "FUT",
                "expiry": july,
            },
            {
                "instrument_token": 203,
                "exchange_token": 1203,
                "tradingsymbol": "SENSEX26JULFUT",
                "name": "SENSEX",
                "exchange": "BFO",
                "segment": "BFO-FUT",
                "instrument_type": "FUT",
                "expiry": july,
            },
            {
                "instrument_token": 301,
                "exchange_token": 1301,
                "tradingsymbol": "NIFTY26JUL25000CE",
                "name": "NIFTY",
                "exchange": "NFO",
                "segment": "NFO-OPT",
                "instrument_type": "CE",
                "expiry": july,
            },
            {
                "instrument_token": 401,
                "exchange_token": 1401,
                "tradingsymbol": "NIFTYBEES",
                "name": "NIFTYBEES",
                "exchange": "NSE",
                "segment": "NSE",
                "instrument_type": "EQ",
                "expiry": None,
            },
        ]
    )
    return records


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


def test_reference_bootstrap_bounds_skip_weekends_and_exclude_building_minute():
    monday = datetime(2026, 7, 20, 9, 17, tzinfo=ZoneInfo("Asia/Kolkata"))
    bounds = resolve_reference_bootstrap_bounds(monday)
    assert bounds.previous_start.astimezone(bounds.previous_start.tzinfo).date().isoformat() == "2026-07-17"
    assert bounds.current_start is not None
    assert bounds.current_end is not None
    assert bounds.current_end.minute == 16


def test_desktop_startup_bootstraps_reference_data_per_instrument_when_available():
    qt_app()
    ticker = FakeTickerClient()
    historical_clients = []
    dashboard = create_dashboard_application(
        environ=live_env(LIVE_MARKET_DATA_AUTO_CONNECT="false"),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        historical_client_factory=historical_factory_factory(historical_clients),
        ticker_client=ticker,
        clock=lambda: NOW,
    )
    view = dashboard.main_window.refresh()
    assert len(historical_clients) == 1
    assert len(historical_clients[0].calls) == 6
    assert [market.symbol for market in view.markets] == ["NIFTY", "BANKNIFTY", "SENSEX"]
    for market in view.markets:
        assert market.cpr_pivot is not None
        assert market.camarilla_h3 is not None
        assert market.vwap is not None
    dashboard.shutdown()


def test_futures_vwap_discovers_valid_contracts_warms_vwap_and_surfaces_source_metadata():
    qt_app()
    ticker = FakeTickerClient()
    historical_clients = []
    instrument_clients = []
    dashboard = create_dashboard_application(
        environ=live_env(
            LIVE_MARKET_DATA_AUTO_CONNECT="false",
            LIVE_FUTURES_VWAP_ENABLED="true",
            REFERENCE_DATA_BOOTSTRAP_ENABLED="false",
        ),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        instrument_client_factory=instrument_factory_factory(instrument_clients, futures_records()),
        historical_client_factory=historical_factory_factory(historical_clients),
        ticker_client=ticker,
        clock=lambda: NOW,
    )
    view = dashboard.main_window.refresh()
    assert dashboard.live_futures_vwap_runtime is not None
    snapshot = dashboard.live_futures_vwap_runtime.snapshot()
    assert snapshot.started is True
    assert snapshot.futures_token_count == 3
    assert {item.underlying for item in snapshot.instruments if item.subscription_active} == {
        Instrument.NIFTY,
        Instrument.BANKNIFTY,
        Instrument.SENSEX,
    }
    assert ticker.subscriptions[-1] == (201, 202, 203)
    assert ticker.modes[-1][1] == (201, 202, 203)
    assert view.markets[0].vwap is not None
    assert view.markets[0].vwap_source == "NIFTY26JULFUT"
    assert view.markets[0].vwap_source_type == "Futures Proxy"
    assert view.markets[0].vwap_source_exchange == "NFO"
    assert view.markets[0].vwap_subscription_active is True
    assert view.markets[0].vwap_historical_candles_loaded == 2
    assert view.markets[0].vwap_historical_volume > 0
    assert view.markets[0].vwap_historical_seed_complete is True
    assert view.markets[0].vwap_bootstrap_time is not None
    assert view.markets[0].vwap_current_accumulated_volume == view.markets[0].vwap_source_volume
    assert view.markets[0].latest_candle_close is None
    assert instrument_clients[0].calls == ["NFO", "NFO", "BFO"]
    dashboard.shutdown()
    dashboard.shutdown()
    assert ticker.unsubscriptions.count((201, 202, 203)) == 1


def test_futures_vwap_bootstraps_once_after_open_edge_before_first_live_delta():
    qt_app()
    ticker = FakeTickerClient()
    historical_clients = []
    current = [datetime(2026, 7, 15, 9, 15, 1, tzinfo=ZoneInfo("Asia/Kolkata"))]
    dashboard = create_dashboard_application(
        environ=live_env(
            LIVE_MARKET_DATA_AUTO_CONNECT="false",
            LIVE_FUTURES_VWAP_ENABLED="true",
            REFERENCE_DATA_BOOTSTRAP_ENABLED="false",
        ),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: current[0]),
        instrument_client_factory=instrument_factory_factory([], futures_records()),
        historical_client_factory=historical_factory_factory(historical_clients),
        ticker_client=ticker,
        clock=lambda: current[0],
    )
    assert historical_clients[0].calls == []
    current[0] = datetime(2026, 7, 15, 9, 17, 5, tzinfo=ZoneInfo("Asia/Kolkata"))
    ticker.callbacks["on_ticks"](
        None,
        (
            {
                "instrument_token": 201,
                "last_price": 25333.0,
                "exchange_timestamp": current[0],
                "volume_traded": 30,
            },
        ),
    )
    view = dashboard.main_window.refresh()
    market = view.markets[0]
    assert len(historical_clients[0].calls) == 1
    assert market.vwap_historical_candles_loaded == 2
    assert market.vwap_historical_volume == 20
    assert market.vwap_historical_seed_complete is True
    assert market.vwap_bootstrap_time == current[0]
    assert market.vwap_live_tick_count == 1
    assert market.vwap_last_live_volume == 30
    assert market.vwap_last_delta_volume == 10
    assert market.vwap_current_accumulated_volume == 30
    ticker.callbacks["on_ticks"](
        None,
        (
            {
                "instrument_token": 201,
                "last_price": 25334.0,
                "exchange_timestamp": current[0] + timedelta(seconds=1),
                "volume_traded": 30,
            },
        ),
    )
    assert len(historical_clients[0].calls) == 1
    dashboard.shutdown()


@pytest.mark.parametrize("invalid_token", (None, 0, "bad-token"))
def test_futures_vwap_rejects_invalid_exchange_tokens_and_continues_with_valid_contracts(invalid_token):
    qt_app()
    ticker = FakeTickerClient()
    dashboard = create_dashboard_application(
        environ=live_env(
            LIVE_MARKET_DATA_AUTO_CONNECT="false",
            LIVE_FUTURES_VWAP_ENABLED="true",
            REFERENCE_DATA_BOOTSTRAP_ENABLED="false",
        ),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        instrument_client_factory=instrument_factory_factory([], futures_records(invalid_nifty_exchange_token=invalid_token)),
        historical_client_factory=historical_factory_factory([]),
        ticker_client=ticker,
        clock=lambda: NOW,
    )
    snapshot = dashboard.live_futures_vwap_runtime.snapshot()
    assert snapshot.futures_token_count == 3
    assert {item.contract.instrument_token for item in snapshot.instruments if item.contract is not None} == {201, 202, 203}
    assert ticker.subscriptions[-1] == (201, 202, 203)
    dashboard.shutdown()


def test_futures_vwap_subscription_failure_rolls_back_ownership_and_keeps_spot_runtime_available():
    qt_app()
    ticker = FailingSubscribeTickerClient()
    dashboard = create_dashboard_application(
        environ=live_env(
            LIVE_MARKET_DATA_AUTO_CONNECT="false",
            LIVE_FUTURES_VWAP_ENABLED="true",
            REFERENCE_DATA_BOOTSTRAP_ENABLED="false",
        ),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        instrument_client_factory=instrument_factory_factory([], futures_records()),
        historical_client_factory=historical_factory_factory([]),
        ticker_client=ticker,
        clock=lambda: NOW,
    )
    manager = dashboard.live_futures_vwap_runtime
    snapshot = manager.snapshot()
    assert snapshot.futures_token_count == 0
    assert all(item.subscription_active is False for item in snapshot.instruments)
    assert all("desktop_access_token" not in (item.last_error or "") for item in snapshot.instruments)
    assert dashboard.live_market_data_runtime is not None
    assert ticker.subscriptions == [(201, 202, 203)]
    dashboard.shutdown()


def test_futures_ticks_route_only_to_vwap_and_preserve_spot_candle_isolation():
    qt_app()
    ticker = FakeTickerClient()
    dashboard = create_dashboard_application(
        environ=live_env(
            LIVE_FUTURES_VWAP_ENABLED="true",
            REFERENCE_DATA_BOOTSTRAP_ENABLED="false",
        ),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        instrument_client_factory=instrument_factory_factory([], futures_records()),
        historical_client_factory=historical_factory_factory([]),
        ticker_client=ticker,
        clock=lambda: NOW,
    )
    ticker.callbacks["on_ticks"](
        None,
        (
            {
                "instrument_token": 201,
                "last_price": 25333.0,
                "exchange_timestamp": NOW,
                "volume_traded": 25,
            },
        ),
    )
    ticker.callbacks["on_ticks"](
        None,
        (
            {
                "instrument_token": 201,
                "last_price": 25334.0,
                "exchange_timestamp": NOW + timedelta(seconds=1),
                "volume_traded": 25,
            },
            {
                "instrument_token": 201,
                "last_price": 25335.0,
                "exchange_timestamp": NOW + timedelta(seconds=2),
                "volume_traded": 30,
            },
            {
                "instrument_token": 101,
                "last_price": 25000.0,
                "exchange_timestamp": NOW + timedelta(seconds=3),
                "volume": 0,
            },
        ),
    )
    ticker.callbacks["on_ticks"](
        None,
        (
            {
                "instrument_token": 201,
                "last_price": 25336.0,
                "exchange_timestamp": NOW + timedelta(seconds=4),
                "volume_traded": 20,
            },
            {
                "instrument_token": 201,
                "last_price": 25337.0,
                "exchange_timestamp": NOW + timedelta(seconds=5),
                "volume_traded": 35,
            },
        ),
    )
    view = dashboard.main_window.refresh()
    runtime_snapshot = dashboard.live_market_data_runtime.snapshot()
    assert runtime_snapshot.websocket.delivered_tick_count == 1
    assert view.markets[0].vwap_source == "NIFTY26JULFUT"
    assert view.markets[0].vwap_source_type == "Futures Proxy"
    assert view.markets[0].vwap_source_exchange == "NFO"
    assert view.markets[0].vwap_source_price == 25337.0
    assert view.markets[0].vwap_live_tick_count == 3
    assert view.markets[0].vwap_last_live_volume == 35
    assert view.markets[0].vwap_last_delta_volume == 5
    assert view.markets[0].vwap_current_accumulated_volume == 35
    assert view.markets[0].vwap_source_volume == 35
    assert view.markets[0].latest_candle_close == 25000.0
    assert view.price_actions[0].available is False
    dashboard.shutdown()


def test_reference_bootstrap_before_open_loads_previous_levels_without_current_history():
    qt_app()
    historical_clients = []
    before_open = datetime(2026, 7, 15, 8, 55, tzinfo=ZoneInfo("Asia/Kolkata"))
    dashboard = create_dashboard_application(
        environ=live_env(LIVE_MARKET_DATA_AUTO_CONNECT="false"),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: before_open),
        historical_client_factory=historical_factory_factory(historical_clients),
        ticker_client=FakeTickerClient(),
        clock=lambda: before_open,
    )
    view = dashboard.main_window.refresh()
    assert len(historical_clients[0].calls) == 3
    for market in view.markets:
        assert market.cpr_pivot is not None
        assert market.camarilla_h3 is not None
        assert market.latest_candle_close is None
        assert market.vwap is None
    dashboard.shutdown()


def test_reference_bootstrap_failure_isolated_from_live_runtime_startup():
    qt_app()

    def failing_historical_factory(*, api_key, access_token):
        raise RuntimeError("historical unavailable")

    dashboard = create_dashboard_application(
        environ=live_env(LIVE_MARKET_DATA_AUTO_CONNECT="false"),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        historical_client_factory=failing_historical_factory,
        ticker_client=FakeTickerClient(),
        clock=lambda: NOW,
    )
    assert dashboard.live_market_data_runtime is not None
    view = dashboard.main_window.refresh()
    assert [market.symbol for market in view.markets] == ["NIFTY", "BANKNIFTY", "SENSEX"]
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
    assert view.markets[0].market_bias != "-"
    assert view.ai[0].market_summary != "-"
    assert view.strategies[0].decision != "-"
    assert view.strategies[0].risk_decision == "-"
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
