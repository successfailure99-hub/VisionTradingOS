"""
Tests for Zerodha historical candle normalization.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from math import inf, nan

import pytest

from brokers.zerodha.historical import ZerodhaHistoricalCandleNormalizer
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def raw(**overrides):
    values = dict(date=NOW, open=100.0, high=110.0, low=90.0, close=105.0, volume=10, oi=999)
    values.update(overrides)
    return values


def test_valid_timestamp_price_volume_mapping_and_oi_ignored():
    normalizer = ZerodhaHistoricalCandleNormalizer()
    item = normalizer.normalize(raw(), instrument=Instrument.NIFTY, timeframe=TimeFrame.FIVE_MINUTES)
    assert item.symbol == "NIFTY"
    assert item.timeframe == "5m"
    assert item.start_time == NOW
    assert item.end_time == NOW + timedelta(minutes=5)
    assert (item.open, item.high, item.low, item.close, item.volume) == (100.0, 110.0, 90.0, 105.0, 10)
    naive = normalizer.normalize(raw(date=datetime(2026, 7, 12, 9, 15)), instrument=Instrument.NIFTY, timeframe=TimeFrame.ONE_MINUTE)
    assert naive.start_time.tzinfo is not None
    iso = normalizer.normalize(raw(date=NOW.isoformat()), instrument=Instrument.NIFTY, timeframe=TimeFrame.ONE_MINUTE)
    assert iso.start_time == NOW


def test_invalid_timestamp_prices_volume_geometry_and_batch_behavior():
    normalizer = ZerodhaHistoricalCandleNormalizer()
    source = raw()
    before = deepcopy(source)
    assert normalizer.normalize(source, instrument=Instrument.NIFTY, timeframe=TimeFrame.FIVE_MINUTES)
    assert source == before
    for kwargs in (dict(date=None), dict(date="bad"), dict(open=True), dict(open=nan), dict(open=inf), dict(open=0), dict(volume=True), dict(volume=-1), dict(high=99), dict(low=106), dict(close=111)):
        with pytest.raises((TypeError, ValueError)):
            normalizer.normalize(raw(**kwargs), instrument=Instrument.NIFTY, timeframe=TimeFrame.FIVE_MINUTES)
    first = raw(date=NOW)
    second = raw(date=NOW + timedelta(minutes=5))
    assert [c.start_time for c in normalizer.normalize_many((first, second), instrument=Instrument.NIFTY, timeframe=TimeFrame.FIVE_MINUTES)] == [NOW, NOW + timedelta(minutes=5)]
    assert normalizer.normalize_many((), instrument=Instrument.NIFTY, timeframe=TimeFrame.FIVE_MINUTES) == ()
