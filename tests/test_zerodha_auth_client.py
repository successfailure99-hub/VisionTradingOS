"""
Tests for the lazy Zerodha auth client boundary.
"""

import builtins
import sys
import types

import pytest

from brokers.zerodha.auth.client import KiteConnectAuthClient
from brokers.zerodha.auth.credentials import ZerodhaCredentials


class FakeKiteConnect:
    def __init__(self, api_key):
        self.api_key = api_key
        self.generated = None
        self.access_token = None

    def login_url(self):
        return f"https://kite.zerodha.com/connect/login?api_key={self.api_key}"

    def generate_session(self, request_token, api_secret):
        self.generated = (request_token, api_secret)
        return {"access_token": "access_123", "user_id": "AB1234"}

    def set_access_token(self, access_token):
        self.access_token = access_token

    def profile(self):
        return {"user_id": "AB1234"}


@pytest.fixture
def fake_kiteconnect_module(monkeypatch):
    module = types.ModuleType("kiteconnect")
    module.KiteConnect = FakeKiteConnect
    monkeypatch.setitem(sys.modules, "kiteconnect", module)
    return module


def test_production_client_validates_api_key():
    with pytest.raises(ValueError):
        KiteConnectAuthClient(" ")


def test_lazy_import_permits_unrelated_import_without_kiteconnect(monkeypatch):
    monkeypatch.setitem(sys.modules, "kiteconnect", None)

    credentials = ZerodhaCredentials("api_key", "api_secret")

    assert credentials.api_key == "api_key"


def test_missing_kiteconnect_raises_clear_runtime_error(monkeypatch):
    monkeypatch.delitem(sys.modules, "kiteconnect", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "kiteconnect":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="kiteconnect is required"):
        KiteConnectAuthClient("api_key")


def test_login_url_delegates_correctly(fake_kiteconnect_module):
    client = KiteConnectAuthClient("api_key")

    assert client.login_url() == "https://kite.zerodha.com/connect/login?api_key=api_key"


def test_session_generation_delegates_correctly(fake_kiteconnect_module):
    client = KiteConnectAuthClient("api_key")

    response = client.generate_session("request_123", "secret_123")

    assert response == {"access_token": "access_123", "user_id": "AB1234"}
    assert client._client.generated == ("request_123", "secret_123")


def test_access_token_application_delegates_correctly(fake_kiteconnect_module):
    client = KiteConnectAuthClient("api_key")

    client.set_access_token("access_123")

    assert client._client.access_token == "access_123"


def test_profile_delegates_correctly(fake_kiteconnect_module):
    client = KiteConnectAuthClient("api_key")

    assert client.profile() == {"user_id": "AB1234"}


def test_raw_client_is_not_publicly_exposed(fake_kiteconnect_module):
    client = KiteConnectAuthClient("api_key")

    assert "client" not in vars(client)
    assert hasattr(client, "_client")
