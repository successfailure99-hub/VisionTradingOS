"""
No-network integration tests for Zerodha instrument discovery.
"""

from datetime import UTC, datetime, timedelta

from application import ApplicationBootstrap
from application.live_market_data import LiveMarketDataRuntimeFactory, LiveMarketDataRuntimeStatus
from brokers.zerodha.auth import ZerodhaCredentials, ZerodhaSessionManager
from brokers.zerodha.instruments import ZerodhaInstrumentDiscoveryService, build_live_market_data_configuration
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def raw(token, symbol, exchange):
    return {
        "instrument_token": token,
        "exchange_token": token + 1000,
        "tradingsymbol": symbol,
        "name": symbol,
        "exchange": exchange,
        "segment": "INDICES",
        "instrument_type": "INDEX",
        "expiry": None,
        "strike": 0,
        "lot_size": 1,
        "tick_size": 0.05,
    }


class FakeInstrumentClient:
    def __init__(self):
        self.calls = []

    def instruments(self, exchange=None):
        self.calls.append(exchange)
        return {
            "NSE": [raw(111, "NIFTY 50", "NSE"), raw(222, "NIFTY BANK", "NSE")],
            "BSE": [raw(333, "SENSEX", "BSE")],
        }[exchange]


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
        self.submitted_orders = []

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


def test_discovery_to_live_configuration_and_runtime_factory_no_network_flow():
    instrument_client = FakeInstrumentClient()
    service = ZerodhaInstrumentDiscoveryService(client=instrument_client, clock=lambda: NOW)
    service.load()
    resolutions = service.create_resolver().resolve_many((Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX))
    configuration = build_live_market_data_configuration(api_key="api_key", resolutions=resolutions)

    assert instrument_client.calls == ["NSE", "BSE"]
    assert [subscription.instrument for subscription in configuration.subscriptions] == [Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX]
    assert [subscription.exchange.value for subscription in configuration.subscriptions] == ["NSE", "NSE", "BSE"]
    assert [subscription.instrument_token for subscription in configuration.subscriptions] == [111, 222, 333]
    assert [subscription.mode.value for subscription in configuration.subscriptions] == ["full", "full", "full"]
    assert configuration.auto_connect is False

    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    auth = ZerodhaSessionManager(ZerodhaCredentials("api_key", "api_secret"), client=FakeAuthClient(), clock=lambda: NOW)
    auth.restore_session(user_id="AB1234", access_token="access_token", authenticated_at=NOW, expires_at=NOW + timedelta(hours=1))
    ticker = FakeTickerClient()
    runtime = LiveMarketDataRuntimeFactory(clock=lambda: NOW).create(
        lifecycle=lifecycle,
        session_manager=auth,
        configuration=configuration,
        ticker_client=ticker,
    )

    assert ticker.connect_calls == 0
    assert runtime.status is LiveMarketDataRuntimeStatus.CREATED
    assert lifecycle.snapshot().orchestrator_snapshot.safety_mode.value == "analysis_only"
    assert lifecycle.snapshot().orchestrator_snapshot.broker_mode.value == "dry_run"
    assert ticker.submitted_orders == []
