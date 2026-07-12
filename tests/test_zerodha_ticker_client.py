"""
Tests for KiteTicker client boundary.
"""

import builtins
import sys
import types

import pytest

from brokers.zerodha.market_data.client import KiteTickerClient


class FakeKiteTicker:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.connected = []
        self.closed = 0
        self.subscribed = []
        self.unsubscribed = []
        self.modes = []

    def connect(self, threaded=True):
        self.connected.append(threaded)

    def close(self):
        self.closed += 1

    def subscribe(self, instrument_tokens):
        self.subscribed.append(list(instrument_tokens))

    def unsubscribe(self, instrument_tokens):
        self.unsubscribed.append(list(instrument_tokens))

    def set_mode(self, mode, instrument_tokens):
        self.modes.append((mode, list(instrument_tokens)))


@pytest.fixture
def fake_kiteconnect(monkeypatch):
    module = types.ModuleType("kiteconnect")
    module.KiteTicker = FakeKiteTicker
    monkeypatch.setitem(sys.modules, "kiteconnect", module)
    return module


def test_lazy_import_allows_module_import_without_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "kiteconnect", None)

    assert KiteTickerClient.MODE_FULL == "full"


def test_missing_dependency_fails_only_at_construction(monkeypatch):
    monkeypatch.delitem(sys.modules, "kiteconnect", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "kiteconnect":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="kiteconnect is required"):
        KiteTickerClient(api_key="api", access_token="token")


def test_constructor_validates_credentials():
    with pytest.raises(ValueError):
        KiteTickerClient(api_key=" ", access_token="token")
    with pytest.raises(ValueError):
        KiteTickerClient(api_key="api", access_token=" ")


def test_constructor_performs_no_network_and_delegates_reconnect_config(fake_kiteconnect):
    client = KiteTickerClient(
        api_key="api",
        access_token="token",
        reconnect=False,
        reconnect_max_tries=3,
        reconnect_max_delay=9,
    )

    assert client._ticker.connected == []
    assert client._ticker.kwargs["reconnect"] is False
    assert client._ticker.kwargs["reconnect_max_tries"] == 3
    assert client._ticker.kwargs["reconnect_max_delay"] == 9


def test_callback_assignment(fake_kiteconnect):
    client = KiteTickerClient(api_key="api", access_token="token")
    callbacks = {name: object() for name in ("on_connect", "on_ticks", "on_close", "on_error", "on_reconnect", "on_noreconnect")}

    client.set_callbacks(**callbacks)

    for name, value in callbacks.items():
        assert getattr(client._ticker, name) is value


def test_delegates_connection_and_subscription_methods(fake_kiteconnect):
    client = KiteTickerClient(api_key="api", access_token="token")

    client.connect()
    client.close()
    client.subscribe([101])
    client.unsubscribe([101])
    client.set_mode("full", [101])

    assert client._ticker.connected == [True]
    assert client._ticker.closed == 1
    assert client._ticker.subscribed == [[101]]
    assert client._ticker.unsubscribed == [[101]]
    assert client._ticker.modes == [("full", [101])]


def test_raw_client_not_publicly_exposed_and_repr_redacts(fake_kiteconnect):
    client = KiteTickerClient(api_key="api_secret_key", access_token="access_secret_token")

    assert "ticker" not in vars(client)
    assert "api_secret_key" not in repr(client)
    assert "access_secret_token" not in repr(client)
