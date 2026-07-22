"""
Desktop live option-chain integration tests.
"""

import os
from datetime import UTC, date, datetime, timedelta

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
        "OPTION_CHAIN_STRIKES_EACH_SIDE": "1",
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
    def __init__(self, *, fail_option_subscribe=False):
        self.callbacks = {}
        self.connect_calls = 0
        self.close_calls = 0
        self.subscriptions = []
        self.unsubscriptions = []
        self.modes = []
        self.submitted_orders = []
        self.fail_option_subscribe = fail_option_subscribe

    def set_callbacks(self, **callbacks):
        self.callbacks = callbacks

    def connect(self, *, threaded=True):
        self.connect_calls += 1

    def close(self):
        self.close_calls += 1

    def subscribe(self, instrument_tokens):
        if self.fail_option_subscribe and any(token >= 1000 for token in instrument_tokens):
            raise RuntimeError("subscribe failed for secret desktop_access_token")
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
        (Instrument.NIFTY, (24900, 25000, 25100)),
        (Instrument.BANKNIFTY, (51900, 52000, 52100)),
        (Instrument.SENSEX, (80900, 81000, 81100)),
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


def spot_tick_with_timestamp(token, price, timestamp):
    row = spot_tick(token, price)
    row["exchange_timestamp"] = timestamp
    return row


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
    fail_option_subscribe = env_overrides.pop("fail_option_subscribe", False)
    clock = env_overrides.pop("clock", lambda: NOW)
    ticker = FakeTickerClient(fail_option_subscribe=fail_option_subscribe)
    dashboard = create_dashboard_application(
        environ=live_env(**env_overrides),
        auth_client_factory=auth_factory,
        instrument_client_factory=instrument_factory(option_records() if records is None else records),
        runtime_factory=LiveMarketDataRuntimeFactory(clock=clock),
        ticker_client=ticker,
        clock=clock,
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
    assert view.option_chains[0].runtime_status == "Disabled"
    assert view.option_chains[0].runtime_message == "Set LIVE_OPTION_CHAIN_ENABLED=true"
    dashboard.shutdown()


def test_option_chain_requires_live_market_data_and_valid_configuration():
    with pytest.raises(DesktopLiveDataConfigurationError, match="requires LIVE_MARKET_DATA_ENABLED"):
        load_desktop_live_configuration({"LIVE_MARKET_DATA_ENABLED": "false", "LIVE_OPTION_CHAIN_ENABLED": "true"})
    with pytest.raises(DesktopLiveDataConfigurationError, match="OPTION_CHAIN_STRIKES_EACH_SIDE must be between 1 and 20"):
        load_desktop_live_configuration(live_env(OPTION_CHAIN_STRIKES_EACH_SIDE="0"))
    with pytest.raises(DesktopLiveDataConfigurationError, match="OPTION_CHAIN_STRIKES_EACH_SIDE must be between 1 and 20"):
        load_desktop_live_configuration(live_env(OPTION_CHAIN_STRIKES_EACH_SIDE="21"))


def test_enabled_mode_resolves_expiry_atm_pairs_and_populates_dashboard_option_chain():
    dashboard, ticker = create_dashboard()
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (spot_tick(101, 25050),))
    assert dashboard.live_option_chain_runtime is not None
    assert dashboard.live_option_chain_runtime.started is True
    assert (1000, 1001, 1002, 1003, 1004, 1005) in ticker.subscriptions

    first_tokens = tuple(range(1000, 1006))
    ticker.callbacks["on_ticks"](None, tuple(option_tick(token, 100 + token) for token in first_tokens))
    ticker.callbacks["on_ticks"](None, tuple(option_tick(token, 120 + token, 11) for token in first_tokens))

    view = dashboard.main_window.refresh()
    option_view = view.option_chains[0]
    assert option_view.available is True
    assert option_view.symbol == "NIFTY"
    assert option_view.expiry_date == EXPIRY
    assert option_view.atm_strike == 25000.0
    assert option_view.strike_count == 3
    assert option_view.total_call_oi > 0
    assert option_view.total_put_oi > 0
    assert option_view.oi_pcr is not None
    assert option_view.change_oi_pcr is not None
    assert option_view.support_strike is not None
    assert option_view.resistance_strike is not None
    assert option_view.max_pain_strike == 25000.0
    assert len(option_view.strikes) == 3
    assert option_view.runtime_status == "Receiving"
    market_view = view.markets[0]
    assert market_view.option_chain_direction == "-"
    assert market_view.market_bias == "-"

    ticker.callbacks["on_ticks"](
        None,
        (spot_tick_with_timestamp(101, 25060, NOW + timedelta(minutes=1)),),
    )
    view = dashboard.main_window.refresh()
    market_view = view.markets[0]
    assert market_view.option_chain_direction != "-"
    assert market_view.market_bias != "-"
    assert view.ai[0].market_summary != "-"
    assert view.strategies[0].decision != "-"
    assert option_view.runtime_subscribed_contracts == 6
    assert option_view.option_ticks_received == 12
    assert option_view.health_option_feed is True
    assert option_view.health_analytics is True
    assert option_view.runtime_rows[0].instrument == "NIFTY"
    assert option_view.runtime_rows[0].state == "Receiving"
    assert any(row.instrument == "NIFTY" and row.message == "Analytics updated" for row in option_view.event_rows)
    panel = dashboard.main_window._instrument_panels["NIFTY"]["option_chain"]
    assert panel._tabs.tabText(0) == "Overview"
    assert panel._labels["Positioning Bias"].text() == "Mixed"
    assert panel._labels["OI PCR"].text() == "1.0009"
    assert panel._labels["Change OI PCR"].text() == "1.0000"
    assert panel._labels["ATM Strike"].text() == "25000.00"
    assert panel._labels["Support"].text() == "25100.00"
    assert panel._labels["Resistance"].text() == "25100.00"
    assert panel._labels["Max Pain"].text() == "25000.00"
    assert panel._labels["Call Pressure"].text() == "Call Writing"
    assert panel._labels["Put Pressure"].text() == "Put Writing"
    assert panel._labels["Total Call OI"].text() == "3366"
    assert panel._labels["Total Put OI"].text() == "3369"
    assert panel._labels["Total Call Change OI"].text() == "60"
    assert panel._labels["Total Put Change OI"].text() == "60"
    assert panel._labels["Strike Count"].text() == "3"
    assert panel._labels["Contracts Active"].text() == "6"
    assert panel._labels["Option Ticks"].text() == "12"
    assert panel._table.rowCount() == 3
    assert panel._table.item(0, 6).text() == "24900.00"
    assert panel._table.item(1, 6).text() == "25000.00"
    assert panel._table.item(2, 6).text() == "25100.00"
    assert ticker.submitted_orders == []
    assert view.runtime.broker_mode == "Dry Run"
    assert view.runtime.safety_mode == "Analysis Only"
    dashboard.shutdown()


def test_naive_zerodha_spot_timestamp_is_localized_and_option_chain_progresses():
    naive = datetime(2026, 7, 15, 9, 36, 15)
    dashboard, ticker = create_dashboard()
    ticker.callbacks["on_connect"](None, {})

    ticker.callbacks["on_ticks"](None, (spot_tick_with_timestamp(101, 25050, naive),))

    option_runtime = dashboard.live_option_chain_runtime.snapshot()
    nifty = option_runtime.instruments[0]
    assert nifty.naive_timestamps_localized == 1
    assert nifty.normalized_timestamp_count == 1
    assert nifty.last_normalized_spot_timestamp == naive.replace(tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    assert nifty.last_normalized_spot_timestamp.hour == 9
    assert nifty.state.value in {"Subscribing", "Receiving", "Waiting For Spot"}
    assert (1000, 1001, 1002, 1003, 1004, 1005) in ticker.subscriptions
    assert ticker.close_calls == 0
    dashboard.shutdown()


def test_malformed_sensex_timestamp_does_not_stop_nifty_or_disconnect_callback():
    dashboard, ticker = create_dashboard()
    ticker.callbacks["on_connect"](None, {})

    ticker.callbacks["on_ticks"](
        None,
        (
            spot_tick_with_timestamp(103, 81050, object()),
            spot_tick_with_timestamp(101, 25050, datetime(2026, 7, 15, 9, 36, 15)),
        ),
    )

    view = dashboard.main_window.refresh()
    option_runtime = dashboard.live_option_chain_runtime.snapshot()
    nifty = next(item for item in option_runtime.instruments if item.underlying is Instrument.NIFTY)
    sensex = next(item for item in option_runtime.instruments if item.underlying is Instrument.SENSEX)
    assert view.markets[0].last_price == 25050.0
    assert nifty.option_token_count == 6
    assert sensex.invalid_timestamp_rows == 1
    assert "Rejected live tick: invalid timestamp" in sensex.last_timestamp_error
    assert "desktop_access_token" not in sensex.last_timestamp_error
    assert ticker.close_calls == 0
    assert ticker.connect_calls == 1
    dashboard.shutdown()


def test_option_chain_callback_failure_is_isolated_from_spot_delivery(monkeypatch):
    dashboard, ticker = create_dashboard()
    ticker.callbacks["on_connect"](None, {})
    manager = dashboard.live_option_chain_runtime
    monkeypatch.setattr(manager, "deliver_spot_ticks", lambda rows: (_ for _ in ()).throw(RuntimeError("boom desktop_access_token")))

    ticker.callbacks["on_ticks"](None, (spot_tick(101, 25050),))

    view = dashboard.main_window.refresh()
    assert view.markets[0].last_price == 25050.0
    assert ticker.close_calls == 0
    assert ticker.connect_calls == 1
    assert "desktop_access_token" not in getattr(ticker, "_last_callback_error", "")
    dashboard.shutdown()


def test_waiting_for_option_ticks_analytics_waiting_and_stale_states_are_visible():
    current = [NOW]
    dashboard, ticker = create_dashboard(clock=lambda: current[0])
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (spot_tick(101, 25050),))
    waiting = dashboard.main_window.refresh().option_chains[0]
    assert waiting.runtime_status == "Waiting For Option Ticks"
    assert waiting.runtime_message == "Waiting for first option tick"

    ticker.callbacks["on_ticks"](None, (option_tick(1000, 1100),))
    partial = dashboard.main_window.refresh().option_chains[0]
    assert partial.runtime_status == "Analytics Waiting"
    assert partial.option_ticks_received == 1

    ticker.callbacks["on_ticks"](None, tuple(option_tick(token, 120 + token, 11) for token in range(1000, 1006)))
    receiving = dashboard.main_window.refresh().option_chains[0]
    assert receiving.runtime_status == "Receiving"
    current[0] = datetime(2026, 7, 15, 9, 16, 2, tzinfo=UTC)
    stale = dashboard.main_window.refresh().option_chains[0]
    assert stale.runtime_status == "Stale"
    assert stale.runtime_message == "Last option tick is stale"
    dashboard.shutdown()


def test_waiting_status_visible_before_first_spot_tick():
    dashboard, _ = create_dashboard()
    snapshot = dashboard.live_option_chain_runtime.snapshot()
    assert snapshot.instruments[0].state.value == "Waiting For Spot"
    view = dashboard.main_window.refresh()
    assert view.option_chains[0].runtime_status == "Waiting For Spot"
    assert view.option_chains[0].runtime_message == "Waiting for first NIFTY spot tick"
    assert view.option_chains[0].health_discovery is True
    assert view.option_chains[0].health_spot_feed is False
    dashboard.shutdown()


def test_same_callback_spot_and_option_ticks_route_after_ownership_registration():
    dashboard, ticker = create_dashboard()
    ticker.callbacks["on_connect"](None, {})
    rows = (spot_tick(101, 25050),) + tuple(option_tick(token, 100 + token) for token in range(1000, 1006))
    ticker.callbacks["on_ticks"](None, rows)
    view = dashboard.main_window.refresh()
    assert view.option_chains[0].available is True
    assert view.option_chains[0].option_ticks_received == 6
    dashboard.shutdown()


def test_activation_failure_rolls_back_ownership_and_exposes_sanitized_error():
    dashboard, ticker = create_dashboard(fail_option_subscribe=True)
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (spot_tick(101, 25050),))
    manager = dashboard.live_option_chain_runtime
    assert manager.option_tokens() == set()
    view = dashboard.main_window.refresh()
    assert view.markets[0].last_price == 25050.0
    assert view.option_chains[0].runtime_status == "Error"
    assert "desktop_access_token" not in (view.option_chains[0].runtime_last_error or "")
    assert view.option_chains[0].runtime_last_error is not None
    dashboard.shutdown()


@pytest.mark.parametrize(
    "spot_token, price, expected_symbol, expected_tokens",
    (
        (101, 25050, "NIFTY", (1000, 1001, 1002, 1003, 1004, 1005)),
        (102, 52050, "BANKNIFTY", (1006, 1007, 1008, 1009, 1010, 1011)),
        (103, 81050, "SENSEX", (1012, 1013, 1014, 1015, 1016, 1017)),
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
    assert populated[0].strike_count == 3
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
    assert dashboard.live_option_chain_runtime is not None
    assert dashboard.live_option_chain_runtime.snapshot().last_error is not None
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (spot_tick(101, 25050),))
    view = dashboard.main_window.refresh()
    assert view.markets[0].last_price == 25050.0
    assert view.option_chains[0].available is False
    assert view.option_chains[0].runtime_status == "Error"
    assert view.option_chains[0].runtime_last_error is not None
    assert "desktop_api_key" not in view.live_market_data.runtime_status
    assert "desktop_access_token" not in view.live_market_data.runtime_status
    dashboard.shutdown()


def test_invalid_option_exchange_tokens_surface_safe_discovery_error_on_dashboard():
    records = []
    for record in option_records():
        broken = dict(record)
        broken["exchange_token"] = None
        records.append(broken)
    dashboard, ticker = create_dashboard(records=tuple(records))
    assert dashboard.live_option_chain_runtime is not None
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (spot_tick(101, 25050),))
    view = dashboard.main_window.refresh()
    assert view.markets[0].last_price == 25050.0
    assert view.option_chains[0].runtime_status == "Error"
    assert view.option_chains[0].runtime_last_error is not None
    assert view.option_chains[0].runtime_last_error == "No valid NIFTY contracts were discovered."
    assert "TypeError" not in view.option_chains[0].runtime_last_error
    assert "desktop_access_token" not in view.option_chains[0].runtime_last_error
    dashboard.shutdown()


def test_nifty_receiving_and_banknifty_waiting_are_isolated_from_sensex_discovery_error():
    records = []
    for record in option_records():
        row = dict(record)
        if row["name"] == "SENSEX":
            row["exchange_token"] = "856478.0"
        records.append(row)
    dashboard, ticker = create_dashboard(records=tuple(records))
    ticker.callbacks["on_connect"](None, {})
    ticker.callbacks["on_ticks"](None, (spot_tick(101, 25050),))
    ticker.callbacks["on_ticks"](None, tuple(option_tick(token, 120 + token, 11) for token in range(1000, 1006)))

    view = dashboard.main_window.refresh()
    by_symbol = {chain.symbol: chain for chain in view.option_chains}
    assert by_symbol["NIFTY"].runtime_status == "Receiving"
    assert by_symbol["NIFTY"].runtime_last_error is None
    assert by_symbol["NIFTY"].available is True
    assert by_symbol["NIFTY"].strike_count == 3
    assert all(24900 <= strike.strike_price <= 25100 for strike in by_symbol["NIFTY"].strikes)
    assert by_symbol["BANKNIFTY"].runtime_status == "Waiting For Spot"
    assert by_symbol["BANKNIFTY"].runtime_last_error is None
    assert by_symbol["SENSEX"].runtime_status == "Error"
    assert by_symbol["SENSEX"].runtime_last_error == "No valid SENSEX contracts were discovered."
    assert "SENSEX" not in (by_symbol["NIFTY"].runtime_last_error or "")
    assert "SENSEX" not in (by_symbol["BANKNIFTY"].runtime_last_error or "")

    nifty_panel = dashboard.main_window._instrument_panels["NIFTY"]["option_chain"]
    bank_panel = dashboard.main_window._instrument_panels["BANKNIFTY"]["option_chain"]
    sensex_panel = dashboard.main_window._instrument_panels["SENSEX"]["option_chain"]
    assert nifty_panel._labels["Status"].text() == "Receiving"
    assert nifty_panel._labels["Last Error"].text() == "-"
    assert nifty_panel._table.rowCount() == 3
    assert bank_panel._labels["Status"].text() == "Waiting For Spot"
    assert bank_panel._labels["Last Error"].text() == "-"
    assert sensex_panel._labels["Status"].text() == "Error"
    assert sensex_panel._labels["Last Error"].text() == "No valid SENSEX contracts were discovered."
    assert ticker.submitted_orders == []
    assert view.runtime.broker_mode == "Dry Run"
    assert view.runtime.safety_mode == "Analysis Only"
    dashboard.shutdown()
