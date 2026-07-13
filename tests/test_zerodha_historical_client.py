"""
Tests for Zerodha historical client boundary.
"""

import builtins
import sys
import types

import pytest

from brokers.zerodha.historical.client import KiteHistoricalClient


class FakeKiteConnect:
    constructed = []

    def __init__(self, *, api_key):
        self.api_key = api_key
        self.access_token = None
        self.calls = []
        FakeKiteConnect.constructed.append(self)

    def set_access_token(self, access_token):
        self.access_token = access_token

    def historical_data(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["interval"] == "bad":
            raise RuntimeError(f"bad {self.api_key} {self.access_token}")
        return [{"date": "x"}]


def install(monkeypatch):
    monkeypatch.setitem(sys.modules, "kiteconnect", types.SimpleNamespace(KiteConnect=FakeKiteConnect))


def test_lazy_import_validation_no_fetch_and_access_token(monkeypatch):
    real_import = builtins.__import__
    monkeypatch.delitem(sys.modules, "kiteconnect", raising=False)

    def blocked(name, *args, **kwargs):
        if name == "kiteconnect":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RuntimeError):
        KiteHistoricalClient(api_key="a", access_token="b")
    install(monkeypatch)
    with pytest.raises(ValueError):
        KiteHistoricalClient(api_key="", access_token="b")
    with pytest.raises(ValueError):
        KiteHistoricalClient(api_key="a", access_token="")
    client = KiteHistoricalClient(api_key="real_api_key_secret", access_token="real_access_token_secret")
    raw = FakeKiteConnect.constructed[-1]
    assert raw.access_token == "real_access_token_secret"
    assert raw.calls == []


def test_delegate_repr_and_error_redaction(monkeypatch):
    install(monkeypatch)
    api_key = "real_api_key_secret"
    access_token = "real_access_token_secret"
    client = KiteHistoricalClient(api_key=api_key, access_token=access_token)
    result = client.historical_data(101, "from", "to", "minute", False, False)
    assert result == [{"date": "x"}]
    call = FakeKiteConnect.constructed[-1].calls[-1]
    assert call == dict(instrument_token=101, from_date="from", to_date="to", interval="minute", continuous=False, oi=False)
    assert not hasattr(client, "client")
    assert api_key not in repr(client)
    assert access_token not in repr(client)
    with pytest.raises(RuntimeError) as exc:
        client.historical_data(101, "from", "to", "bad")
    assert api_key not in str(exc.value)
    assert access_token not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)
