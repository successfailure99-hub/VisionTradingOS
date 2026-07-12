"""
Tests for Zerodha instrument discovery service.
"""

from datetime import UTC, datetime

import pytest

from brokers.zerodha.instruments import (
    ZerodhaInstrumentDiscoveryService,
    ZerodhaInstrumentDiscoveryStatus,
)
from core.enums.exchange import Exchange


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def raw(token, symbol, exchange="NSE"):
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


class FakeClient:
    def __init__(self, data=None, fail=False):
        self.data = data or {"NSE": [raw(101, "NIFTY 50"), raw(102, "NIFTY BANK")], "BSE": [raw(201, "SENSEX", "BSE")]}
        self.fail = fail
        self.calls = []

    def instruments(self, exchange=None):
        self.calls.append(exchange)
        if self.fail:
            raise RuntimeError("client failed api_secret")
        return self.data[exchange]


def test_constructor_no_load_initial_status_default_load_order_and_success():
    client = FakeClient()
    service = ZerodhaInstrumentDiscoveryService(client=client, clock=lambda: NOW)
    assert client.calls == []
    assert service.snapshot().status is ZerodhaInstrumentDiscoveryStatus.CREATED
    snapshot = service.load()
    assert client.calls == ["NSE", "BSE"]
    assert snapshot.status is ZerodhaInstrumentDiscoveryStatus.READY
    assert snapshot.record_count == 3
    assert snapshot.index_record_count == 3
    assert snapshot.supported_resolution_count == 3
    assert snapshot.loaded_exchanges == (Exchange.NSE, Exchange.BSE)
    assert snapshot.loaded_at is NOW


def test_catalogue_replaced_atomically_and_bad_exchanges_rejected():
    service = ZerodhaInstrumentDiscoveryService(client=FakeClient(), clock=lambda: NOW)
    service.load((Exchange.NSE,))
    previous = service.catalogue.all()
    with pytest.raises(ValueError):
        service.load(())
    with pytest.raises(ValueError):
        service.load((Exchange.NSE, Exchange.NSE))
    with pytest.raises(ValueError):
        service.load((Exchange.MCX,))
    assert service.catalogue.all() == previous


def test_exchange_mismatch_duplicate_token_and_failures_preserve_old_catalogue():
    service = ZerodhaInstrumentDiscoveryService(client=FakeClient(), clock=lambda: NOW)
    service.load((Exchange.NSE,))
    previous = service.catalogue.all()
    service._client = FakeClient({"NSE": [raw(101, "NIFTY 50", "BSE")]})
    with pytest.raises(ValueError):
        service.load((Exchange.NSE,))
    assert service.snapshot().status is ZerodhaInstrumentDiscoveryStatus.ERROR
    assert "{" not in service.snapshot().last_error
    assert service.catalogue.all() == previous
    service._client = FakeClient({"NSE": [raw(101, "A")], "BSE": [raw(101, "SENSEX", "BSE")]})
    with pytest.raises(ValueError):
        service.load()
    assert service.catalogue.all() == previous
    service._client = FakeClient(fail=True)
    with pytest.raises(RuntimeError):
        service.load((Exchange.NSE,))
    assert service.catalogue.all() == previous


def test_successful_reload_clears_error_clear_works_and_resolver_reuses_catalogue():
    service = ZerodhaInstrumentDiscoveryService(client=FakeClient(fail=True), clock=lambda: NOW)
    with pytest.raises(RuntimeError):
        service.load((Exchange.NSE,))
    assert service.snapshot().status is ZerodhaInstrumentDiscoveryStatus.ERROR
    service._client = FakeClient()
    snapshot = service.load()
    assert snapshot.last_error is None
    assert service.create_resolver().resolve_many(tuple()).__class__ is tuple
    cleared = service.clear()
    assert cleared.status is ZerodhaInstrumentDiscoveryStatus.CLEARED
    assert service.catalogue.all() == ()


def test_normalizer_failure_preserves_old_catalogue_and_no_auto_refresh_or_retry():
    class BadNormalizer:
        def normalize_many(self, records):
            raise ValueError("bad normalizer")

    service = ZerodhaInstrumentDiscoveryService(client=FakeClient(), clock=lambda: NOW)
    service.load((Exchange.NSE,))
    previous = service.catalogue.all()
    service._normalizer = BadNormalizer()
    with pytest.raises(ValueError):
        service.load((Exchange.NSE,))
    assert service.catalogue.all() == previous
    assert service._client.calls.count("NSE") == 2
    assert not hasattr(service, "refresh")
