"""
Desktop live option-chain integration tests.
"""

import os
from datetime import UTC, date, datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from application.desktop_live_data import (
    DesktopLiveDataConfigurationError,
    create_dashboard_application,
    load_desktop_live_configuration,
)
from application.live_market_data import LiveMarketDataRuntimeFactory
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 15, 9, 15, tzinfo=UTC)
EXPIRY = date(2026, 7, 30)


def qt_app():
    return QApplication.instance() or QApplication([])


def live_env(**overrides):
    env = {
        "LIVE_MARKET_DATA_ENABLED": "true",
        "LIVE_MARKET_DATA_AUTO_CONNECT": "true",
        "LIVE_OPTION_CHAIN_ENABLED": "true",
        "LIVE_OPTION_CHAIN_AUTO_START": "true",
        "OPTION_CHAIN_REFRESH_SECONDS": "15",
        "OPTION_CHAIN_STRIKES_EACH_SIDE": "0",
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
    def __init__(self, api_key):
        self.api_key = api_key
        self.access_token = None

    def set_access_token(self, access_token):
        self.access_token = access_token

    def profile(self):
        return {"user_id": "AB1234"}


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


class FakeInstrumentClient:
    def __init__(self, records):
        self.records = tuple(records)
        self.calls = []

    def instruments(self, exchange=None):
        self.calls.append(exchange)
        return tuple(record for record in self.records if exchange is None or record["exchange"] == exchange)


def auth_factory(api_key):
    return FakeAuthClient(api_key)


def instrument_factory(records):
    def create(*, api_key, access_token):
        assert api_key == "desktop_api_key"
        assert access_token == "desktop_access_token"
        return FakeInstrumentClient(records)

    return create


def option_record(token, underlying: Instrument, strike, right):
    venue = "BFO" if underlying is Instrument.SENSEX else "NFO"
    segment = f"{venue}-OPT"
    symbol = f"{underlying.value}{EXPIRY:%d%b%y}{int(strike)}{right}".upper()
    return {
        "instrument_token": token,
        "exchange_token": token,
        "exchange": venue,
        "segment": segment,
        "tradingsymbol": symbol,
        "name": underlying.value,
        "expiry": EXPIRY,
        "strike": float(strike),
        "instrument_type": right,
        "lot_size": 25,
        "tick_size": 0.05,
    }


def option_records():
    rows = []
    token = 1000
    for underlying, strikes in (
        (Instrument.NIFTY, (25000, 25100)),
        (Instrument.BANKNIFTY, (52000, 52100)),
        (Instrument.SENSEX, (81000, 81100)),
    ):
        for strike in strikes:
            rows.append(option_record(token, underlying, strike, "CE"))
            token += 1
            rows.append(option_record(token, underlying, strike, "PE"))
            token += 1
    return tuple(rows)


def spot_tick(token, price):
    return {
        "instrument_token": token,
        "last_price": float(price),
        "exchange_timestamp": NOW,
        "volume": 10,
        "depth": {"buy": [{"price": float(price) - 1}], "sell": [{"price": float(price) + 1}]},
    }


def option_tick(token, oi, price=10.0):
    return {
        "instrument_token": token,
        "last_price": price,
        "volume": token,
        "oi": oi,
        "exchange_timestamp": NOW,
        "depth": {"buy": [{"price": price - 0.5}], "sell": [{"price": price + 0.5}]},
    }


def create_dashboard(records=None, **env_overrides):
    qt_app()
    ticker = FakeTickerClient()
    dashboard = create_dashboard_application(
        environ=live_env(**env_overrides),
        auth_client_factory=auth_factory,
        instrument_client_factory=instrument_factory(option_records() if records is None else records),
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        ticker_client=ticker,
        clock=lambda: NOW,
    )
    return dashboard, ticker


def test_disabled_option_chain_mode_leaves_dashboard_unavailable():
    qt_app()
    dashboard = create_dashboard_application(
        environ=live_env(LIVE_OPTION_CHAIN_ENABLED="false"),
        auth_client_factory=auth_factory,
        runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: NOW),
        ticker_client=FakeTickerClient(),
        clock=lambda: NOW,
    )
    assert dashboard.live_option_chain_runtime is None
    view = dashboard.main_window.refresh()
    assert view.option_chains[0].available is False
    dashboard.shutdown()


def test_option_chain_requires_live_market_data_and_valid_configuration():
    with pytest.raises(DesktopLiveDataConfigurationError, match="requires LIVE_MARKET_DATA_ENABLED"):
        load_desktop_live_configuration({"LIVE_MARKET_DATA_ENABLED": "false", "LIVE_OPTION_CHAIN_ENABLED": "true"})
    with pytest.raises(DesktopLiveDataConfigurationError, match="OPTION_CHAIN_REFRESH_SECONDS must be a positive integer"):
        load_desktop_live_configuration(live_env(OPTION_CHAIN_REFRESH_SECONDS="0"))
    with pytest.raises(DesktopLiveDataConfigurationError, match="OPTION_CHAIN_STRIKES_EACH_SIDE must be a non-negative integer"):
        load_desktop_live_configuration(live_env(OPTION_CHAIN_STRIKES_EACH_SIDE="-1"))


def test_enabled_mode_resolves_expiry_atm_pairs_and_populates_dashboard_option_chain():
    dashboard, ticker = create_dashboard()
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (spot_tick(101, 25050),))
    assert dashboard.live_option_chain_runtime is not None
    assert dashboard.live_option_chain_runtime.started is True
    assert (1000, 1001) in ticker.subscriptions

    ticker.callbacks["on_ticks"](None, (option_tick(1000, 100), option_tick(1001, 200)))
    ticker.callbacks["on_ticks"](None, (option_tick(1000, 120, 11), option_tick(1001, 240, 12)))

    view = dashboard.main_window.refresh()
    option_view = view.option_chains[0]
    assert option_view.available is True
    assert option_view.symbol == "NIFTY"
    assert option_view.expiry_date == EXPIRY
    assert option_view.atm_strike == 25000.0
    assert option_view.strike_count == 1
    assert option_view.total_call_oi == 120
    assert option_view.total_put_oi == 240
    assert option_view.oi_pcr == 2.0
    assert option_view.change_oi_pcr == 2.0
    assert option_view.support_strike == 25000.0
    assert option_view.resistance_strike == 25000.0
    assert option_view.max_pain_strike == 25000.0
    assert len(option_view.strikes) == 1
    assert ticker.submitted_orders == []
    assert view.runtime.broker_mode == "Dry Run"
    assert view.runtime.safety_mode == "Analysis Only"
    dashboard.shutdown()


@pytest.mark.parametrize(
    "spot_token, price, expected_symbol, expected_tokens",
    (
        (101, 25050, "NIFTY", (1000, 1001)),
        (102, 52050, "BANKNIFTY", (1004, 1005)),
        (103, 81050, "SENSEX", (1008, 1009)),
    ),
)
def test_supported_underlying_mapping_for_nifty_banknifty_and_sensex(
    spot_token,
    price,
    expected_symbol,
    expected_tokens,
):
    dashboard, ticker = create_dashboard()
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (spot_tick(spot_token, price),))
    assert expected_tokens in ticker.subscriptions
    ticker.callbacks["on_ticks"](None, tuple(option_tick(token, 100 + token) for token in expected_tokens))
    view = dashboard.main_window.refresh()
    populated = [chain for chain in view.option_chains if chain.available]
    assert len(populated) == 1
    assert populated[0].symbol == expected_symbol
    assert populated[0].strike_count == 1
    dashboard.shutdown()


def test_runtime_starts_stops_once_and_shutdown_is_idempotent():
    dashboard, ticker = create_dashboard()
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (spot_tick(101, 25050),))
    stack = dashboard.live_option_chain_runtime._stacks[Instrument.NIFTY]
    assert stack.live_integration.snapshot().start_count == 1
    dashboard.shutdown()
    dashboard.shutdown()
    assert stack.live_integration.snapshot().stop_count == 1
    assert ticker.close_calls == 1


def test_provider_failure_is_safe_and_spot_runtime_remains_operational():
    dashboard, ticker = create_dashboard(records=())
    assert dashboard.live_option_chain_runtime is None
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (spot_tick(101, 25050),))
    view = dashboard.main_window.refresh()
    assert view.markets[0].last_price == 25050.0
    assert view.option_chains[0].available is False
    assert "desktop_api_key" not in view.live_market_data.runtime_status
    assert "desktop_access_token" not in view.live_market_data.runtime_status
    dashboard.shutdown()
