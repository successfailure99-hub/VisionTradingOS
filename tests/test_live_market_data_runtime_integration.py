"""
Integration smoke tests for live market-data runtime.
"""

from datetime import UTC, datetime, timedelta

from application.bootstrap import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from application.live_market_data import LiveMarketDataConfiguration, LiveMarketDataRuntimeFactory
from brokers.zerodha.auth import ZerodhaCredentials, ZerodhaSessionManager
from brokers.zerodha.enums import BrokerExecutionMode
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from dashboard.presenters import build_dashboard_view


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


def raw(price=25000.0, timestamp=NOW):
    return {
        "instrument_token": 101,
        "last_price": price,
        "exchange_timestamp": timestamp,
        "volume": 10,
        "depth": {"buy": [{"price": price - 1}], "sell": [{"price": price + 1}]},
    }


def test_live_market_data_runtime_delivers_ticks_through_orchestrator_and_preserves_safety():
    lifecycle = ApplicationBootstrap().create_application()
    ticker = FakeTickerClient()
    lifecycle.start()
    auth = ZerodhaSessionManager(ZerodhaCredentials("api_key", "api_secret"), client=FakeAuthClient(), clock=lambda: NOW)
    auth.restore_session(user_id="AB1234", access_token="access_token", authenticated_at=NOW, expires_at=NOW + timedelta(hours=1))
    configuration = LiveMarketDataConfiguration("api_key", (ZerodhaInstrumentSubscription(101, Instrument.NIFTY, Exchange.NSE),))

    runtime = LiveMarketDataRuntimeFactory(clock=lambda: NOW).create(
        lifecycle=lifecycle,
        session_manager=auth,
        configuration=configuration,
        ticker_client=ticker,
    )

    runtime.validate()
    runtime.start()
    ticker.callbacks["on_connect"](None, {})
    result = runtime.websocket_manager.process_raw_ticks((raw(), raw(), raw(24999.0, NOW - timedelta(seconds=1)), {"instrument_token": 999, "last_price": 1}, raw(25001.0, NOW + timedelta(seconds=1))))
    dashboard = build_dashboard_view(lifecycle.snapshot())

    assert ticker.connect_calls == 1
    assert lifecycle.orchestrator.market_data_engine.get_latest(Instrument.NIFTY).last_price == 25001.0
    assert lifecycle.snapshot().orchestrator_snapshot.runtime_snapshots[0].latest_tick.last_price == 25001.0
    assert lifecycle.snapshot().orchestrator_snapshot.runtime_snapshots[0].latest_candle is not None
    assert result.rejected_count == 2
    assert dashboard.markets[0].last_price == 25001.0
    assert lifecycle.orchestrator.configuration.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert lifecycle.orchestrator.broker_adapter.mode is BrokerExecutionMode.DRY_RUN

    runtime.stop()
    assert lifecycle.is_running() is True
    lifecycle.stop()
