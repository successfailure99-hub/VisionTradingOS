"""
Tests for Zerodha WebSocket manager.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from threading import RLock

import pytest

from brokers.zerodha.auth import ZerodhaSession
from brokers.zerodha.market_data import (
    ZerodhaInstrumentSubscription,
    ZerodhaSubscriptionMode,
    ZerodhaWebSocketManager,
    ZerodhaWebSocketStatus,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


class FakeTickerClient:
    def __init__(self):
        self.callbacks = None
        self.connect_calls = []
        self.close_calls = 0
        self.subscribed = []
        self.unsubscribed = []
        self.modes = []
        self.fail_subscribe = None
        self.fail_unsubscribe = None

    def set_callbacks(self, **callbacks):
        if self.callbacks is not None:
            raise AssertionError("callbacks registered twice")
        self.callbacks = callbacks

    def connect(self, *, threaded=True):
        self.connect_calls.append(threaded)

    def close(self):
        self.close_calls += 1

    def subscribe(self, instrument_tokens):
        if self.fail_subscribe:
            raise self.fail_subscribe
        self.subscribed.append(list(instrument_tokens))

    def unsubscribe(self, instrument_tokens):
        if self.fail_unsubscribe:
            raise self.fail_unsubscribe
        self.unsubscribed.append(list(instrument_tokens))

    def set_mode(self, mode, instrument_tokens):
        self.modes.append((mode, list(instrument_tokens)))


def session(expires_at=NOW + timedelta(hours=1)):
    return ZerodhaSession("AB1234", "access_secret", NOW, expires_at)


def sub(token=101, instrument=Instrument.NIFTY, mode=ZerodhaSubscriptionMode.FULL):
    return ZerodhaInstrumentSubscription(token, instrument, Exchange.NSE, mode)


def manager(client=None, subscriptions=(), consumer=None):
    return ZerodhaWebSocketManager(
        api_key="api_secret",
        session=session(),
        tick_consumer=consumer or (lambda tick: tick),
        subscriptions=subscriptions,
        client=client or FakeTickerClient(),
        clock=lambda: NOW,
    )


def raw(token=101, price=25000.0):
    return {
        "instrument_token": token,
        "last_price": price,
        "exchange_timestamp": NOW,
        "volume": 1,
        "depth": {"buy": [{"price": price - 1}], "sell": [{"price": price + 1}]},
    }


def test_initial_state_constructor_and_expired_session():
    client = FakeTickerClient()
    subject = manager(client)

    assert subject.status is ZerodhaWebSocketStatus.CREATED
    assert client.connect_calls == []
    with pytest.raises(ValueError):
        ZerodhaWebSocketManager(api_key="api", session=session(NOW - timedelta(seconds=1)), tick_consumer=lambda tick: tick, client=client)


def test_connect_sets_connecting_double_connect_idempotent_and_on_connect_applies_subscriptions():
    client = FakeTickerClient()
    subject = manager(client, (sub(101), sub(102, Instrument.BANKNIFTY, ZerodhaSubscriptionMode.QUOTE)))

    first = subject.connect()
    second = subject.connect()
    client.callbacks["on_connect"](None, {})

    assert first.status is ZerodhaWebSocketStatus.CONNECTING
    assert second.status is ZerodhaWebSocketStatus.CONNECTING
    assert client.connect_calls == [True]
    assert subject.status is ZerodhaWebSocketStatus.CONNECTED
    assert subject.snapshot().connection_count == 1
    assert client.subscribed == [[101, 102]]
    assert ("full", [101]) in client.modes
    assert ("quote", [102]) in client.modes


def test_disconnect_callbacks_reconnect_and_noreconnect():
    client = FakeTickerClient()
    subject = manager(client)
    subject.connect()
    client.callbacks["on_connect"](None, {})

    assert subject.disconnect().status is ZerodhaWebSocketStatus.DISCONNECTED
    assert subject.disconnect().status is ZerodhaWebSocketStatus.DISCONNECTED
    client.callbacks["on_reconnect"](None, 1)
    assert subject.status is ZerodhaWebSocketStatus.RECONNECTING
    assert subject.snapshot().reconnect_count == 1
    client.callbacks["on_noreconnect"](None)
    assert subject.status is ZerodhaWebSocketStatus.ERROR


def test_subscribe_unsubscribe_disconnected_and_connected_failure_paths():
    client = FakeTickerClient()
    subject = manager(client)
    subject.subscribe(sub(101))
    assert client.subscribed == []

    subject.connect()
    client.callbacks["on_connect"](None, {})
    subject.subscribe(sub(102, Instrument.BANKNIFTY))
    assert client.subscribed[-1] == [102]
    client.fail_subscribe = RuntimeError("bad api_secret access_secret")
    with pytest.raises(RuntimeError):
        subject.subscribe(sub(103, Instrument.SENSEX))
    assert subject.registry.get_by_token(103) is None
    assert "api_secret" not in subject.snapshot().last_error
    assert "access_secret" not in subject.snapshot().last_error

    client.fail_subscribe = None
    client.callbacks["on_connect"](None, {})
    client.fail_unsubscribe = RuntimeError("bad")
    with pytest.raises(RuntimeError):
        subject.unsubscribe(102)
    assert subject.registry.get_by_token(102) is not None
    client.fail_unsubscribe = None
    subject.unsubscribe(102)
    assert subject.registry.get_by_token(102) is None


def test_replace_subscriptions_disconnected_connected_and_failure_preserves_registry():
    client = FakeTickerClient()
    subject = manager(client, (sub(101),))
    subject.replace_subscriptions((sub(102, Instrument.BANKNIFTY),))
    assert subject.registry.tokens() == (102,)

    subject.connect()
    client.callbacks["on_connect"](None, {})
    subject.replace_subscriptions((sub(103, Instrument.SENSEX),))
    assert client.unsubscribed[-1] == [102]
    assert client.subscribed[-1] == [103]
    assert subject.registry.tokens() == (103,)

    client.fail_unsubscribe = RuntimeError("replace failed")
    with pytest.raises(RuntimeError):
        subject.replace_subscriptions((sub(104, Instrument.FINNIFTY),))
    assert subject.registry.tokens() == (103,)


def test_process_raw_ticks_serialized_delivery_counts_and_errors():
    delivered = []

    def consumer(tick):
        delivered.append(tick)
        if tick.last_price == 25001.0:
            raise RuntimeError("consumer failed")

    subject = manager(subscriptions=(sub(101),), consumer=consumer)
    result = subject.process_raw_ticks((raw(101, 25000.0), {"instrument_token": 999, "last_price": 1}, raw(101, 25001.0)))

    assert result.received_count == 3
    assert len(result.normalized_ticks) == 2
    assert len(result.delivered_ticks) == 1
    assert result.rejected_count == 2
    assert subject.snapshot().rejected_tick_count == 2
    assert subject.snapshot().last_tick_at == NOW
    assert subject.status is ZerodhaWebSocketStatus.CREATED


def test_snapshot_immutable_no_secret_fields_same_client_callbacks_once_and_rlock():
    client = FakeTickerClient()
    subject = manager(client, (sub(101),))
    snapshot = subject.snapshot()

    assert subject._client is client
    assert isinstance(subject._lock, type(RLock()))
    assert "api_secret" not in repr(snapshot)
    assert "access_secret" not in repr(snapshot)
    with pytest.raises(FrozenInstanceError):
        snapshot.connected = True
    assert client.callbacks is not None
