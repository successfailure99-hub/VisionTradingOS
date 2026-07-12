"""
Tests for Zerodha instrument discovery models.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, date, datetime

import pytest

from brokers.zerodha.instruments import (
    ZerodhaInstrumentDiscoverySnapshot,
    ZerodhaInstrumentDiscoveryStatus,
    ZerodhaInstrumentRecord,
    ZerodhaInstrumentResolution,
    ZerodhaInstrumentType,
)
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def record(**overrides):
    values = dict(
        instrument_token=101,
        exchange_token=1001,
        tradingsymbol=" NIFTY 50 ",
        name=" NIFTY 50 ",
        exchange=Exchange.NSE,
        segment=" INDICES ",
        instrument_type=ZerodhaInstrumentType.INDEX,
        expiry=None,
        strike=0.0,
        lot_size=1,
        tick_size=0.05,
    )
    values.update(overrides)
    return ZerodhaInstrumentRecord(**values)


def test_valid_record_and_text_normalization():
    item = record()
    assert item.instrument_token == 101
    assert item.tradingsymbol == "NIFTY 50"
    assert item.name == "NIFTY 50"
    assert item.segment == "INDICES"


def test_invalid_tokens_and_optional_exchange_token_validation():
    with pytest.raises(ValueError):
        record(instrument_token=0)
    with pytest.raises(ValueError):
        record(instrument_token=True)
    with pytest.raises(ValueError):
        record(exchange_token=0)
    assert record(exchange_token=None).exchange_token is None


def test_invalid_exchange_type_expiry_strike_lot_and_tick_size():
    with pytest.raises(TypeError):
        record(exchange="NSE")
    with pytest.raises(TypeError):
        record(instrument_type="INDEX")
    with pytest.raises(TypeError):
        record(expiry=NOW)
    assert record(expiry=date(2026, 7, 30)).expiry == date(2026, 7, 30)
    with pytest.raises(ValueError):
        record(strike=-1.0)
    with pytest.raises(ValueError):
        record(lot_size=0)
    with pytest.raises(ValueError):
        record(tick_size=0.0)


def test_record_resolution_and_snapshot_are_immutable_and_consistent():
    item = record()
    with pytest.raises(FrozenInstanceError):
        item.name = "x"
    subscription = ZerodhaInstrumentSubscription(101, Instrument.NIFTY, Exchange.NSE)
    resolution = ZerodhaInstrumentResolution(Instrument.NIFTY, item, subscription)
    assert resolution.record is item
    with pytest.raises(ValueError):
        ZerodhaInstrumentResolution(Instrument.BANKNIFTY, item, subscription)
    snapshot = ZerodhaInstrumentDiscoverySnapshot(
        ZerodhaInstrumentDiscoveryStatus.READY,
        1,
        1,
        1,
        (Exchange.NSE,),
        NOW,
        None,
    )
    with pytest.raises(FrozenInstanceError):
        snapshot.record_count = 2


def test_snapshot_validates_counts_timestamps_and_has_no_secret_fields():
    with pytest.raises(ValueError):
        ZerodhaInstrumentDiscoverySnapshot(ZerodhaInstrumentDiscoveryStatus.READY, -1, 0, 0, (), None, None)
    with pytest.raises(ValueError):
        ZerodhaInstrumentDiscoverySnapshot(ZerodhaInstrumentDiscoveryStatus.READY, 0, 0, 0, (), datetime(2026, 7, 12), None)
    names = {field.name for field in fields(ZerodhaInstrumentDiscoverySnapshot)}
    assert names.isdisjoint({"api_key", "api_secret", "access_token", "request_token", "raw_records"})
