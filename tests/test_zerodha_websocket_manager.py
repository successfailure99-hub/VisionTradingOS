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
        self.invoke_close_callback_on_close = False

    def set_callbacks(self, **callbacks):
        if self.callbacks is not None:
            raise AssertionError("callbacks registered twice")
        self.callbacks = callbacks

    def connect(self, *, threaded=True):
        self.connect_calls.append(threaded)

    def close(self):
        self.close_calls += 1
        if self.invoke_close_callback_on_close:
            self.callbacks["on_close"](None, 1000, "closed")

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


def manager(client=None, subscriptions=(), consumer=None, clock=None, **kwargs):
    return ZerodhaWebSocketManager(
        api_key="api_secret",
        session=session(),
        tick_consumer=consumer or (lambda tick: tick),
        subscriptions=subscriptions,
        client=client or FakeTickerClient(),
        clock=clock or (lambda: NOW),
        **kwargs,
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


def test_disconnect_stops_and_ignores_late_reconnect_callbacks():
    client = FakeTickerClient()
    subject = manager(client)
    subject.connect()
    client.callbacks["on_connect"](None, {})

    assert subject.disconnect().status is ZerodhaWebSocketStatus.STOPPED
    assert subject.disconnect().status is ZerodhaWebSocketStatus.STOPPED
    client.callbacks["on_reconnect"](None, 1)
    assert subject.status is ZerodhaWebSocketStatus.STOPPED
    assert subject.snapshot().reconnect_count == 0
    client.callbacks["on_noreconnect"](None)
    assert subject.status is ZerodhaWebSocketStatus.STOPPED


def test_synchronous_on_close_during_client_close_counts_one_disconnect():
    client = FakeTickerClient()
    client.invoke_close_callback_on_close = True
    subject = manager(client)
    subject.connect()
    client.callbacks["on_connect"](None, {})

    snapshot = subject.disconnect()

    assert snapshot.status is ZerodhaWebSocketStatus.STOPPED
    assert snapshot.disconnection_count == 1
    assert snapshot.last_disconnected_at == NOW


def test_asynchronous_on_close_after_disconnect_returns_does_not_count_twice():
    client = FakeTickerClient()
    subject = manager(client)
    subject.connect()
    client.callbacks["on_connect"](None, {})

    snapshot = subject.disconnect()
    first_disconnected_at = snapshot.last_disconnected_at
    client.callbacks["on_close"](None, 1000, "closed")

    assert subject.snapshot().disconnection_count == 1
    assert subject.snapshot().last_disconnected_at == first_disconnected_at


def test_manual_disconnect_with_no_callback_counts_once_and_double_disconnect_is_idempotent():
    client = FakeTickerClient()
    subject = manager(client)
    subject.connect()
    client.callbacks["on_connect"](None, {})

    first = subject.disconnect()
    second = subject.disconnect()

    assert first.disconnection_count == 1
    assert second.disconnection_count == 1
    assert second.status is ZerodhaWebSocketStatus.STOPPED


def test_remote_on_close_counts_once_and_duplicate_callback_is_idempotent():
    client = FakeTickerClient()
    subject = manager(client)
    subject.connect()
    client.callbacks["on_connect"](None, {})

    client.callbacks["on_close"](None, 1000, "closed")
    first_disconnected_at = subject.snapshot().last_disconnected_at
    client.callbacks["on_close"](None, 1000, "duplicate")

    assert subject.snapshot().disconnection_count == 1
    assert subject.snapshot().last_disconnected_at == first_disconnected_at
    assert subject.snapshot().status is ZerodhaWebSocketStatus.RECONNECT_WAIT


def test_reconnect_followed_by_another_close_permits_new_disconnection_count():
    client = FakeTickerClient()
    subject = manager(client)
    subject.connect()
    client.callbacks["on_connect"](None, {})
    client.callbacks["on_close"](None, 1000, "closed")

    client.callbacks["on_connect"](None, {})
    client.callbacks["on_close"](None, 1000, "closed again")

    assert subject.snapshot().connection_count == 2
    assert subject.snapshot().disconnection_count == 2


def test_reconnect_wait_uses_bounded_backoff_and_prevents_overlapping_connects():
    client = FakeTickerClient()
    current = [NOW]
    subject = manager(
        client,
        clock=lambda: current[0],
        reconnect_initial_delay_seconds=2,
        reconnect_max_delay_seconds=5,
    )
    subject.connect()
    client.callbacks["on_connect"](None, {})

    client.callbacks["on_close"](None, 1006, "connection was closed uncleanly")
    first = subject.snapshot()
    assert first.status is ZerodhaWebSocketStatus.RECONNECT_WAIT
    assert first.retry_count == 1
    assert first.reconnect_delay_seconds == 2
    assert first.reconnect_due_at == NOW + timedelta(seconds=2)
    assert client.connect_calls == [True]

    subject.connect()
    assert client.connect_calls == [True]

    current[0] = NOW + timedelta(seconds=2)
    subject.retry_connect_if_due()
    assert subject.snapshot().status is ZerodhaWebSocketStatus.CONNECTING
    assert client.connect_calls == [True, True]

    client.callbacks["on_error"](None, 1006, "connection was closed uncleanly")
    assert subject.snapshot().status is ZerodhaWebSocketStatus.CONNECTING
    client.callbacks["on_close"](None, 1006, "connection was closed uncleanly")
    second = subject.snapshot()
    assert second.status is ZerodhaWebSocketStatus.RECONNECT_WAIT
    assert second.retry_count == 2
    assert second.reconnect_delay_seconds == 4

    current[0] = NOW + timedelta(seconds=6)
    subject.retry_connect_if_due()
    client.callbacks["on_error"](None, 1006, "connection was closed uncleanly")
    assert subject.snapshot().reconnect_delay_seconds == 4
    client.callbacks["on_close"](None, 1006, "connection was closed uncleanly")
    assert subject.snapshot().reconnect_delay_seconds == 5


def test_duplicate_1006_errors_are_suppressed_without_reconnect_storm():
    client = FakeTickerClient()
    subject = manager(client)
    subject.connect()
    client.callbacks["on_connect"](None, {})

    client.callbacks["on_error"](None, 1006, "peer dropped the TCP connection without previous WebSocket closing handshake")
    first = subject.snapshot()
    client.callbacks["on_error"](None, 1006, "peer dropped the TCP connection without previous WebSocket closing handshake")
    second = subject.snapshot()

    assert first.status is ZerodhaWebSocketStatus.CONNECTED
    assert second.reconnect_count == first.reconnect_count
    assert second.retry_count == first.retry_count
    assert second.suppressed_error_count == 1
    assert second.error_callbacks == 2
    assert second.disconnect_callbacks == 0
    assert second.retry_scheduled == 0
    assert client.connect_calls == [True]

    client.callbacks["on_close"](None, 1006, "peer dropped the TCP connection without previous WebSocket closing handshake")
    closed = subject.snapshot()
    assert closed.status is ZerodhaWebSocketStatus.RECONNECT_WAIT
    assert closed.retry_scheduled == 1
    assert closed.reconnect_owner == "on_close"


def test_duplicate_connect_callbacks_do_not_resubscribe_same_connection():
    client = FakeTickerClient()
    subject = manager(client, (sub(101), sub(102, Instrument.BANKNIFTY)))
    subject.connect()

    client.callbacks["on_connect"](None, {})
    client.callbacks["on_connect"](None, {})

    assert subject.snapshot().connection_count == 1
    assert client.subscribed == [[101, 102]]


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
    assert subject.snapshot().broker_received_at == NOW
    assert subject.snapshot().tick_exchange_timestamp == NOW
    assert subject.snapshot().tick_normalized_at == NOW
    assert subject.snapshot().event_published_at == NOW
    assert subject.snapshot().runtime_processed_at == NOW
    assert subject.snapshot().latest_tick_latency_ms is not None
    assert subject.snapshot().max_tick_latency_ms is not None
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
