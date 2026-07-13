"""
Tests for the Zerodha historical data client boundary.
"""

from __future__ import annotations

import builtins
from datetime import UTC, datetime
import sys
import types

import pytest

from brokers.zerodha.historical.client import KiteHistoricalClient


class FakeKiteConnect:
    constructed: list["FakeKiteConnect"] = []

    def __init__(self, *, api_key: str):
        self.api_key = api_key
        self.access_token: str | None = None
        self.historical_calls: list[dict[str, object]] = []
        FakeKiteConnect.constructed.append(self)

    def set_access_token(self, access_token: str) -> None:
        self.access_token = access_token

    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ):
        call = {
            "instrument_token": instrument_token,
            "from_date": from_date,
            "to_date": to_date,
            "interval": interval,
            "continuous": continuous,
            "oi": oi,
        }
        self.historical_calls.append(call)

        if instrument_token == 999:
            raise RuntimeError(
                f"historical failure {self.api_key} {self.access_token}"
            )

        return [
            {
                "date": from_date,
                "open": 100.0,
                "high": 110.0,
                "low": 95.0,
                "close": 105.0,
                "volume": 1000,
            }
        ]


@pytest.fixture(autouse=True)
def reset_fake_client_state():
    FakeKiteConnect.constructed.clear()
    yield
    FakeKiteConnect.constructed.clear()


def install_fake_kiteconnect(monkeypatch) -> None:
    fake_module = types.SimpleNamespace(KiteConnect=FakeKiteConnect)
    monkeypatch.setitem(sys.modules, "kiteconnect", fake_module)


def test_lazy_import_and_missing_dependency_fails_only_on_construction(monkeypatch):
    monkeypatch.delitem(sys.modules, "kiteconnect", raising=False)

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "kiteconnect":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    with pytest.raises(RuntimeError, match="kiteconnect"):
        KiteHistoricalClient(
            api_key="real_api_key_secret",
            access_token="real_access_token_secret",
        )


def test_validates_credentials_and_performs_no_historical_request_in_constructor(
    monkeypatch,
):
    install_fake_kiteconnect(monkeypatch)

    with pytest.raises(ValueError):
        KiteHistoricalClient(
            api_key="",
            access_token="valid_access_token",
        )

    with pytest.raises(ValueError):
        KiteHistoricalClient(
            api_key="valid_api_key",
            access_token="",
        )

    with pytest.raises(TypeError):
        KiteHistoricalClient(
            api_key=123,
            access_token="valid_access_token",
        )

    with pytest.raises(TypeError):
        KiteHistoricalClient(
            api_key="valid_api_key",
            access_token=123,
        )

    client = KiteHistoricalClient(
        api_key="valid_api_key",
        access_token="valid_access_token",
    )

    raw_client = FakeKiteConnect.constructed[-1]

    assert client is not None
    assert raw_client.api_key == "valid_api_key"
    assert raw_client.access_token == "valid_access_token"
    assert raw_client.historical_calls == []


def test_historical_data_delegates_all_arguments_exactly(monkeypatch):
    install_fake_kiteconnect(monkeypatch)

    client = KiteHistoricalClient(
        api_key="valid_api_key",
        access_token="valid_access_token",
    )

    start_at = datetime(2026, 7, 1, 9, 15, tzinfo=UTC)
    end_at = datetime(2026, 7, 1, 15, 30, tzinfo=UTC)

    result = client.historical_data(
        instrument_token=101,
        from_date=start_at,
        to_date=end_at,
        interval="5minute",
        continuous=True,
        oi=True,
    )

    raw_client = FakeKiteConnect.constructed[-1]

    assert result == [
        {
            "date": start_at,
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
            "volume": 1000,
        }
    ]

    assert raw_client.historical_calls == [
        {
            "instrument_token": 101,
            "from_date": start_at,
            "to_date": end_at,
            "interval": "5minute",
            "continuous": True,
            "oi": True,
        }
    ]


def test_raw_client_is_not_public_and_repr_redacts_actual_credentials(
    monkeypatch,
):
    install_fake_kiteconnect(monkeypatch)

    api_key = "real_api_key_secret_123"
    access_token = "real_access_token_secret_456"

    client = KiteHistoricalClient(
        api_key=api_key,
        access_token=access_token,
    )

    assert not hasattr(client, "client")

    rendered = repr(client)

    assert api_key not in rendered
    assert access_token not in rendered
    assert "[REDACTED]" in rendered


def test_project_created_errors_redact_actual_credentials(monkeypatch):
    install_fake_kiteconnect(monkeypatch)

    api_key = "real_api_key_secret_123"
    access_token = "real_access_token_secret_456"

    client = KiteHistoricalClient(
        api_key=api_key,
        access_token=access_token,
    )

    start_at = datetime(2026, 7, 1, 9, 15, tzinfo=UTC)
    end_at = datetime(2026, 7, 1, 15, 30, tzinfo=UTC)

    with pytest.raises(RuntimeError) as exc_info:
        client.historical_data(
            instrument_token=999,
            from_date=start_at,
            to_date=end_at,
            interval="5minute",
            continuous=False,
            oi=False,
        )

    message = str(exc_info.value)

    assert api_key not in message
    assert access_token not in message
    assert "[REDACTED]" in message
