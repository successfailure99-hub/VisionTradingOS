from dataclasses import FrozenInstanceError
from datetime import datetime
from math import inf, nan
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from adapters.zerodha import (
    ZerodhaConnectionState,
    ZerodhaCredentials,
    ZerodhaInstrumentToken,
    ZerodhaReadOnlyAdapter,
    ZerodhaSubscription,
)
from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core import events
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.tick import Tick
from engines.market_data.market_data_engine import MarketDataEngine


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 20, 9, 30, tzinfo=IST)


def record(token, symbol, name, exchange):
    return {
        "instrument_token": token,
        "exchange_token": token + 1000,
        "tradingsymbol": symbol,
        "name": name,
        "exchange": exchange,
        "segment": f"{exchange}-INDICES",
        "instrument_type": "INDEX",
        "expiry": None,
        "strike": None,
        "lot_size": None,
        "tick_size": 0.05,
    }


class AuthClient:
    def __init__(self, *, valid=True):
        self.valid = valid
        self.access_tokens = []

    def set_access_token(self, access_token):
        self.access_tokens.append(access_token)

    def profile(self):
        if not self.valid:
            raise RuntimeError("invalid api_secret access_secret")
        return {"user_id": "USER1"}


class InstrumentClient:
    def __init__(self, *, conflict=False, invalid_token=False):
        nifty_token = 0 if invalid_token else 101
        sensex_token = 101 if conflict else 301
        self.responses = {
            "NSE": (
                record(nifty_token, "NIFTY 50", "NIFTY 50", "NSE"),
                record(201, "NIFTY BANK", "NIFTY BANK", "NSE"),
            ),
            "BSE": (
                record(sensex_token, "SENSEX", "SENSEX", "BSE"),
            ),
        }
        self.calls = []

    def instruments(self, exchange):
        self.calls.append(exchange)
        return self.responses[exchange]


class TickerClient:
    def __init__(self):
        self.callbacks = {}
        self.connect_calls = 0
        self.close_calls = 0
        self.subscribed = []
        self.modes = []

    def set_callbacks(self, **callbacks):
        self.callbacks = callbacks

    def connect(self, *, threaded=True):
        self.connect_calls += 1
        self.threaded = threaded

    def close(self):
        self.close_calls += 1

    def subscribe(self, instrument_tokens):
        self.subscribed.append(list(instrument_tokens))

    def set_mode(self, mode, instrument_tokens):
        self.modes.append((mode, list(instrument_tokens)))


def adapter(*, auth_client=None, instrument_client=None, ticker_client=None, tick_consumer=None):
    return ZerodhaReadOnlyAdapter(
        EventBus(),
        auth_client=auth_client or AuthClient(),
        instrument_client=instrument_client or InstrumentClient(),
        ticker_client=ticker_client or TickerClient(),
        tick_consumer=tick_consumer,
        clock=lambda: NOW,
    )


def ready_connected(subject=None, ticker=None):
    ticker = ticker or TickerClient()
    subject = subject or adapter(ticker_client=ticker)
    subject.start()
    subject.configure_credentials(ZerodhaCredentials("api-key-1234", "access-token-secret"))
    subject.load_instrument_tokens()
    subject.connect()
    subject.on_connect(None, None)
    return subject, ticker


def raw_tick(token=101, price=22000.5, timestamp=NOW, volume=100, oi=10):
    return {
        "instrument_token": token,
        "last_price": price,
        "exchange_timestamp": timestamp,
        "volume_traded": volume,
        "oi": oi,
        "depth": {
            "buy": [{"price": price - 0.5}],
            "sell": [{"price": price + 0.5}],
        },
    }


def test_models_and_secrecy_contracts_are_immutable_and_redacted():
    with pytest.raises(ValueError):
        ZerodhaCredentials("api", "")
    credentials = ZerodhaCredentials("api-key-1234", "access-token-secret")
    assert "access-token-secret" not in repr(credentials)
    token = ZerodhaInstrumentToken(Instrument.NIFTY, Exchange.NSE, "NIFTY 50", 101)
    with pytest.raises(FrozenInstanceError):
        token.trading_symbol = "x"
    with pytest.raises(ValueError):
        ZerodhaInstrumentToken(Instrument.NIFTY, Exchange.NSE, "NIFTY 50", 0)
    subscription = ZerodhaSubscription(Instrument.NIFTY, 101)
    assert subscription.mode == "full"
    snapshot = adapter().snapshot()
    assert "access" not in repr(snapshot).casefold()
    assert snapshot.broker_order_calls == 0
    assert snapshot.mutation_calls == 0
    assert snapshot.live_order_submission_enabled is False


def test_lifecycle_transitions_duplicate_connect_stop_reset_and_late_callbacks():
    ticker = TickerClient()
    subject = adapter(ticker_client=ticker)
    assert subject.snapshot().state is ZerodhaConnectionState.CREATED
    assert subject.start().state is ZerodhaConnectionState.READY
    subject.configure_credentials(ZerodhaCredentials("api", "token"))
    first = subject.connect()
    assert first.state is ZerodhaConnectionState.CONNECTING
    assert ticker.connect_calls == 1
    assert subject.connect().state is ZerodhaConnectionState.CONNECTING
    assert ticker.connect_calls == 1
    subject.on_connect(None, None)
    assert subject.snapshot().state is ZerodhaConnectionState.CONNECTED
    subject.on_connect(None, None)
    assert subject.snapshot().state is ZerodhaConnectionState.CONNECTED
    subject.on_close(None, 1000, "closed")
    assert subject.snapshot().state is ZerodhaConnectionState.DISCONNECTED
    assert subject.stop().state is ZerodhaConnectionState.STOPPED
    with pytest.raises(RuntimeError):
        subject.connect()
    stopped = subject.snapshot()
    subject.on_connect(None, None)
    assert subject.snapshot() == stopped
    assert subject.reset().state is ZerodhaConnectionState.READY
    subject._state = ZerodhaConnectionState.FAILED
    with pytest.raises(RuntimeError):
        subject.connect()
    assert subject.reset().state is ZerodhaConnectionState.READY


def test_authentication_validation_failure_is_sanitized_and_does_not_connect():
    ticker = TickerClient()
    subject = adapter(auth_client=AuthClient(valid=False), ticker_client=ticker)
    failed = []
    subject._event_bus.subscribe(events.ZERODHA_AUTHENTICATION_FAILED, failed.append)
    subject.start()
    snapshot = subject.configure_credentials(ZerodhaCredentials("api_secret", "access_secret"))
    assert snapshot.state is ZerodhaConnectionState.FAILED
    assert snapshot.authenticated is False
    assert ticker.connect_calls == 0
    assert "api_secret" not in snapshot.last_error_code
    assert "access_secret" not in snapshot.last_error_code
    assert failed == [snapshot]


def test_token_loading_resolves_supported_indexes_and_rejects_bad_inputs():
    subject = adapter()
    subject.start()
    snapshot = subject.load_instrument_tokens()
    resolved = {token.instrument: token for token in snapshot.resolved_tokens}
    assert resolved[Instrument.NIFTY].instrument_token == 101
    assert resolved[Instrument.BANKNIFTY].instrument_token == 201
    assert resolved[Instrument.SENSEX].instrument_token == 301
    assert subject.load_instrument_tokens().resolved_tokens == snapshot.resolved_tokens
    subject.configure_credentials(ZerodhaCredentials("api", "token"))
    subject.connect()
    subject.on_connect(None, None)
    with pytest.raises(ValueError):
        subject.subscribe(("FINNIFTY",))
    bad = adapter(instrument_client=InstrumentClient(invalid_token=True))
    bad.start()
    assert bad.load_instrument_tokens().state is ZerodhaConnectionState.FAILED
    conflict = adapter(instrument_client=InstrumentClient(conflict=True))
    conflict.start()
    assert conflict.load_instrument_tokens().state is ZerodhaConnectionState.FAILED


def test_subscribe_requires_connection_is_idempotent_and_uses_one_ticker():
    ticker = TickerClient()
    subject = adapter(ticker_client=ticker)
    subject.start()
    with pytest.raises(RuntimeError):
        subject.subscribe(("NIFTY",))
    subject, ticker = ready_connected(subject, ticker)
    snapshot = subject.subscribe(("NIFTY", "BANKNIFTY", "SENSEX"))
    assert snapshot.subscribed_instruments == (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)
    assert ticker.connect_calls == 1
    assert ticker.subscribed == [[101, 201, 301]]
    assert ticker.modes == [("full", [101, 201, 301])]
    duplicate = subject.subscribe(("NIFTY", "BANKNIFTY"))
    assert duplicate.subscribed_instruments == snapshot.subscribed_instruments
    assert ticker.subscribed == [[101, 201, 301]]
    assert ticker.modes == [("full", [101, 201, 301])]


def test_valid_ticks_normalize_to_existing_tick_model_and_enter_market_boundary():
    bus = EventBus()
    market_engine = MarketDataEngine(bus)
    published = []
    bus.subscribe(events.NEW_TICK, published.append)
    subject = ZerodhaReadOnlyAdapter(
        bus,
        auth_client=AuthClient(),
        instrument_client=InstrumentClient(),
        ticker_client=TickerClient(),
        tick_consumer=market_engine.on_tick,
        clock=lambda: NOW,
    )
    ready_connected(subject)
    subject.subscribe(("NIFTY", "BANKNIFTY", "SENSEX"))
    subject.on_ticks(None, (raw_tick(101, 22000.5), raw_tick(201, 51000.0), raw_tick(301, 80000.0)))
    assert [tick.symbol for tick in published] == [Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX]
    assert all(isinstance(tick, Tick) for tick in published)
    assert market_engine.get_latest(Instrument.NIFTY).last_price == 22000.5
    assert subject.snapshot().published_tick_count == 3


def test_malformed_ticks_are_isolated_non_finite_rejected_and_naive_time_localized():
    delivered = []
    subject, _ = ready_connected(adapter(tick_consumer=lambda tick: delivered.append(tick)))
    subject.subscribe(("NIFTY", "BANKNIFTY"))
    naive = datetime(2026, 7, 20, 9, 31)
    subject.on_ticks(None, (raw_tick(999), {"bad": "payload"}, raw_tick(101, nan), raw_tick(101, inf), raw_tick(101, 22001.0, naive), raw_tick(201, 51001.0)))
    snapshot = subject.snapshot()
    assert [tick.symbol for tick in delivered] == [Instrument.NIFTY, Instrument.BANKNIFTY]
    assert delivered[0].timestamp.tzinfo is not None
    assert snapshot.received_tick_count == 6
    assert snapshot.rejected_tick_count == 4
    assert snapshot.published_tick_count == 2
    assert snapshot.state is ZerodhaConnectionState.CONNECTED


def test_duplicate_ticks_are_not_republished_but_authoritative_changes_are():
    delivered = []
    subject, _ = ready_connected(adapter(tick_consumer=lambda tick: delivered.append(tick)))
    subject.subscribe(("NIFTY",))
    tick = raw_tick(101, 22000.5)
    subject.on_ticks(None, (tick, tick, raw_tick(101, 22000.75), raw_tick(101, 22000.75, NOW.replace(minute=31))))
    snapshot = subject.snapshot()
    assert [item.last_price for item in delivered] == [22000.5, 22000.75, 22000.75]
    assert snapshot.duplicate_tick_count == 1
    assert snapshot.published_tick_count == 3


def test_orchestrator_facade_routes_cross_instrument_ticks_to_configured_runtimes():
    app = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX)),
    )
    app.zerodha_adapter = ZerodhaReadOnlyAdapter(
        app._event_bus,
        auth_client=AuthClient(),
        instrument_client=InstrumentClient(),
        ticker_client=TickerClient(),
        tick_consumer=app.process_tick,
        clock=lambda: NOW,
    )
    app.start()
    app.configure_zerodha_credentials(ZerodhaCredentials("api", "token"))
    app.load_zerodha_instrument_tokens()
    app.connect_zerodha_market_data()
    app.zerodha_adapter.on_connect(None, None)
    app.subscribe_zerodha_instruments(("NIFTY", "BANKNIFTY", "SENSEX"))
    app.zerodha_adapter.on_ticks(None, (raw_tick(101, 22000.5), raw_tick(201, 51000.0), raw_tick(301, 80000.0)))
    assert app.get_runtime(RuntimeInstrument.NIFTY).snapshot().latest_tick.last_price == 22000.5
    assert app.get_runtime(RuntimeInstrument.BANKNIFTY).snapshot().latest_tick.last_price == 51000.0
    assert app.get_runtime(RuntimeInstrument.SENSEX).snapshot().latest_tick.last_price == 80000.0
    assert app.snapshot().zerodha_connection.published_tick_count == 3


def test_transport_failure_and_tick_rejection_events_are_sanitized():
    rejected = []
    failed = []
    subject, _ = ready_connected(adapter())
    subject._event_bus.subscribe(events.ZERODHA_TICK_REJECTED, rejected.append)
    subject._event_bus.subscribe(events.ZERODHA_CONNECTION_FAILED, failed.append)
    subject.on_ticks(None, (raw_tick(999),))
    subject.on_error(None, "access_secret", "bad")
    snapshot = subject.snapshot()
    assert rejected
    assert failed
    assert snapshot.state is ZerodhaConnectionState.FAILED
    assert "access_secret" not in snapshot.last_error_code


def test_safety_no_forbidden_protocol_or_adapter_capabilities():
    from adapters.zerodha.protocols import (
        ZerodhaReadOnlyAuthClientProtocol,
        ZerodhaReadOnlyInstrumentClientProtocol,
        ZerodhaReadOnlyTickerClientProtocol,
    )

    forbidden = (
        "place_order",
        "modify_order",
        "cancel_order",
        "exit_order",
        "convert_position",
        "place_gtt",
        "modify_gtt",
        "delete_gtt",
    )
    for protocol in (
        ZerodhaReadOnlyAuthClientProtocol,
        ZerodhaReadOnlyInstrumentClientProtocol,
        ZerodhaReadOnlyTickerClientProtocol,
        ZerodhaReadOnlyAdapter,
    ):
        for name in forbidden:
            assert not hasattr(protocol, name)
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("adapters/zerodha").glob("*.py"))
    for forbidden_text in forbidden + ("webbrowser", "selenium", "playwright", "time.sleep"):
        assert forbidden_text not in text
    snapshot = adapter().snapshot()
    assert snapshot.broker_order_calls == 0
    assert snapshot.mutation_calls == 0
    assert snapshot.live_order_submission_enabled is False
