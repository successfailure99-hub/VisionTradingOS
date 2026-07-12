"""
Tests for the Zerodha instrument client boundary.
"""

import sys
import types
import builtins

import pytest

from brokers.zerodha.instruments.client import KiteInstrumentClient


class FakeKiteConnect:
    constructed = []

    def __init__(self, *, api_key):
        self.api_key = api_key
        self.access_token = None
        self.calls = []
        FakeKiteConnect.constructed.append(self)

    def set_access_token(self, access_token):
        self.access_token = access_token

    def instruments(self, exchange=None):
        self.calls.append(exchange)
        if exchange == "BAD":
            raise RuntimeError(f"bad {self.api_key} {self.access_token}")
        return [{"exchange": exchange}]


def install_fake_module(monkeypatch):
    module = types.SimpleNamespace(KiteConnect=FakeKiteConnect)
    monkeypatch.setitem(sys.modules, "kiteconnect", module)


def test_lazy_import_and_missing_module_fails_only_on_construction(monkeypatch):
    monkeypatch.delitem(sys.modules, "kiteconnect", raising=False)
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "kiteconnect":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(RuntimeError):
        KiteInstrumentClient(api_key="api_key", access_token="access_token")


def test_validates_credentials_and_does_not_fetch_in_constructor(monkeypatch):
    install_fake_module(monkeypatch)
    with pytest.raises(ValueError):
        KiteInstrumentClient(api_key="", access_token="access_token")
    with pytest.raises(ValueError):
        KiteInstrumentClient(api_key="api_key", access_token="")
    client = KiteInstrumentClient(api_key="api_key", access_token="access_token")
    raw = FakeKiteConnect.constructed[-1]
    assert raw.access_token == "access_token"
    assert raw.calls == []


def test_instruments_delegates_and_raw_client_is_not_public(monkeypatch):
    install_fake_module(monkeypatch)
    api_key = "real_api_key_secret_123"
    access_token = "real_access_token_secret_456"
    client = KiteInstrumentClient(api_key=api_key, access_token=access_token)
    assert client.instruments() == [{"exchange": None}]
    assert client.instruments("NSE") == [{"exchange": "NSE"}]
    assert not hasattr(client, "client")
    rendered = repr(client)
    assert api_key not in rendered
    assert access_token not in rendered
    assert "[REDACTED]" in rendered


def test_project_errors_redact_credentials(monkeypatch):
    install_fake_module(monkeypatch)
    api_key = "real_api_key_secret_123"
    access_token = "real_access_token_secret_456"
    client = KiteInstrumentClient(api_key=api_key, access_token=access_token)
    with pytest.raises(RuntimeError) as exc:
        client.instruments("BAD")
    message = str(exc.value)
    assert api_key not in message
    assert access_token not in message
    assert "[REDACTED]" in message
