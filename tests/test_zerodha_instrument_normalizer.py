"""
Tests for Zerodha instrument normalizer.
"""

from copy import deepcopy
from datetime import date, datetime
from math import inf, nan

import pytest

from brokers.zerodha.instruments import ZerodhaInstrumentNormalizer, ZerodhaInstrumentType


def raw(**overrides):
    values = dict(
        instrument_token=101,
        exchange_token=1001,
        tradingsymbol="NIFTY 50",
        name="NIFTY 50",
        exchange="NSE",
        segment="INDICES",
        instrument_type="INDEX",
        expiry=None,
        strike=0,
        lot_size=1,
        tick_size=0.05,
    )
    values.update(overrides)
    return values


def test_type_mapping_for_index_equity_future_option_and_unknown():
    normalizer = ZerodhaInstrumentNormalizer()
    assert normalizer.normalize(raw(instrument_type="INDEX")).instrument_type is ZerodhaInstrumentType.INDEX
    assert normalizer.normalize(raw(instrument_type="INDICES")).instrument_type is ZerodhaInstrumentType.INDEX
    assert normalizer.normalize(raw(instrument_type="", segment="NSE-INDICES")).instrument_type is ZerodhaInstrumentType.INDEX
    assert normalizer.normalize(raw(instrument_type="EQ")).instrument_type is ZerodhaInstrumentType.EQUITY
    assert normalizer.normalize(raw(instrument_type="FUT", expiry="2026-07-30")).instrument_type is ZerodhaInstrumentType.FUTURE
    assert normalizer.normalize(raw(instrument_type="CE", expiry="2026-07-30")).instrument_type is ZerodhaInstrumentType.OPTION
    assert normalizer.normalize(raw(instrument_type="PE", expiry="2026-07-30")).instrument_type is ZerodhaInstrumentType.OPTION
    assert normalizer.normalize(raw(instrument_type="")).instrument_type is ZerodhaInstrumentType.UNKNOWN


def test_expiry_inputs_and_malformed_date_rejected():
    normalizer = ZerodhaInstrumentNormalizer()
    assert normalizer.normalize(raw(expiry=date(2026, 7, 30))).expiry == date(2026, 7, 30)
    assert normalizer.normalize(raw(expiry=datetime(2026, 7, 30, 9, 15))).expiry == date(2026, 7, 30)
    assert normalizer.normalize(raw(expiry="2026-07-30")).expiry == date(2026, 7, 30)
    assert normalizer.normalize(raw(expiry="")).expiry is None
    with pytest.raises(ValueError):
        normalizer.normalize(raw(expiry="30-07-2026"))


def test_numeric_conversion_validation_and_raw_mapping_not_mutated():
    normalizer = ZerodhaInstrumentNormalizer()
    source = raw(strike=1, tick_size=0.01)
    before = deepcopy(source)
    item = normalizer.normalize(source)
    assert item.strike == 1.0
    assert item.tick_size == 0.01
    assert source == before
    for field in ("instrument_token", "exchange_token", "strike", "lot_size", "tick_size"):
        with pytest.raises((TypeError, ValueError)):
            normalizer.normalize(raw(**{field: True}))
    for value in (nan, inf):
        with pytest.raises(ValueError):
            normalizer.normalize(raw(strike=value))


def test_batch_order_preserved_and_empty_batch_supported():
    normalizer = ZerodhaInstrumentNormalizer()
    first = raw(instrument_token=101, tradingsymbol="A", name="A")
    second = raw(instrument_token=102, tradingsymbol="B", name="B")
    assert [record.instrument_token for record in normalizer.normalize_many((first, second))] == [101, 102]
    assert normalizer.normalize_many(()) == ()
