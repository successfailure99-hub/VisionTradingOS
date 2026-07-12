"""
Tests for Zerodha instrument catalogue.
"""

from datetime import date
from threading import RLock

import pytest

from brokers.zerodha.instruments import ZerodhaInstrumentCatalogue, ZerodhaInstrumentRecord, ZerodhaInstrumentType
from core.enums.exchange import Exchange


def record(token=101, symbol="NIFTY 50", exchange=Exchange.NSE, instrument_type=ZerodhaInstrumentType.INDEX, expiry=None):
    return ZerodhaInstrumentRecord(token, token + 1000, symbol, symbol, exchange, "INDICES", instrument_type, expiry, 0.0, 1, 0.05)


def test_empty_source_order_duplicate_token_and_atomic_replace():
    catalogue = ZerodhaInstrumentCatalogue()
    assert catalogue.all() == ()
    first = record(101, "A")
    second = record(102, "B")
    assert catalogue.replace((first, second)) == (first, second)
    with pytest.raises(ValueError):
        catalogue.replace((first, record(101, "C")))
    assert catalogue.all() == (first, second)


def test_lookup_filtering_case_insensitive_search_and_expiry_filter():
    expiry = date(2026, 7, 30)
    first = record(101, "NIFTY 50")
    second = record(202, "SENSEX", Exchange.BSE)
    future = record(303, "NIFTY26JULFUT", Exchange.NSE, ZerodhaInstrumentType.FUTURE, expiry)
    catalogue = ZerodhaInstrumentCatalogue((first, second, future))
    assert catalogue.by_token(101) is first
    assert catalogue.by_exchange(Exchange.BSE) == (second,)
    assert catalogue.find(tradingsymbol=" nifty 50 ") == (first,)
    assert catalogue.find(exchange=Exchange.NSE, instrument_type=ZerodhaInstrumentType.FUTURE, expiry=expiry) == (future,)


def test_clear_immutable_tuples_lock_no_network_or_persistence():
    catalogue = ZerodhaInstrumentCatalogue((record(),))
    assert isinstance(catalogue._lock, type(RLock()))
    all_records = catalogue.all()
    assert isinstance(all_records, tuple)
    assert catalogue.clear() == ()
    assert catalogue.all() == ()
    assert not hasattr(catalogue, "instruments")
    assert not hasattr(catalogue, "path")
