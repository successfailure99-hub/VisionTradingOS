"""
Tests for Zerodha raw tick normalization.
"""

from copy import deepcopy
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionRegistry, ZerodhaTickNormalizer
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


TOKEN = 256265
NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def normalizer(clock=lambda: NOW):
    registry = ZerodhaSubscriptionRegistry((ZerodhaInstrumentSubscription(TOKEN, Instrument.NIFTY, Exchange.NSE),))
    return ZerodhaTickNormalizer(registry, clock=clock)


def raw_tick(**overrides):
    payload = {
        "instrument_token": TOKEN,
        "last_price": 25000.5,
        "exchange_timestamp": datetime(2026, 7, 12, 9, 15),
        "volume_traded": 123,
        "oi": 456,
        "depth": {"buy": [{"price": 25000.0}], "sell": [{"price": 25001.0}]},
    }
    payload.update(overrides)
    return payload


def test_known_token_resolves_instrument_exchange_and_prices():
    tick = normalizer().normalize(raw_tick())

    assert tick.symbol is Instrument.NIFTY
    assert tick.exchange is Exchange.NSE
    assert tick.last_price == 25000.5
    assert tick.volume == 123
    assert tick.open_interest == 456
    assert tick.bid_price == 25000.0
    assert tick.ask_price == 25001.0


def test_volume_fallbacks_and_missing_oi_depth():
    tick = normalizer().normalize(raw_tick(volume_traded=None, volume=7, oi=0, depth=None))

    assert tick.volume == 7
    assert tick.open_interest == 0
    assert tick.bid_price == 0.0
    assert tick.ask_price == 0.0


def test_missing_volume_and_oi_become_zero_for_index_like_ticks():
    payload = raw_tick()
    payload.pop("volume_traded")
    payload.pop("oi")
    payload.pop("depth")

    tick = normalizer().normalize(payload)

    assert tick.volume == 0
    assert tick.open_interest == 0
    assert tick.bid_price == 0.0
    assert tick.ask_price == 0.0


def test_one_sided_depth_handled():
    tick = normalizer().normalize(raw_tick(depth={"buy": [{"price": 25000.0}], "sell": []}))

    assert tick.bid_price == 25000.0
    assert tick.ask_price == 0.0


def test_bid_greater_than_ask_rejected():
    with pytest.raises(ValueError):
        normalizer().normalize(raw_tick(depth={"buy": [{"price": 25002.0}], "sell": [{"price": 25001.0}]}))


def test_token_validation():
    with pytest.raises(ValueError):
        normalizer().normalize(raw_tick(instrument_token=999))
    with pytest.raises(TypeError):
        normalizer().normalize(raw_tick(instrument_token=True))
    payload = raw_tick()
    payload.pop("instrument_token")
    with pytest.raises(TypeError):
        normalizer().normalize(payload)


def test_invalid_prices_rejected():
    for price in (0, -1, float("nan"), float("inf"), True):
        with pytest.raises((TypeError, ValueError)):
            normalizer().normalize(raw_tick(last_price=price))


def test_timestamp_priority_and_timezone_handling():
    naive = datetime(2026, 7, 12, 9, 15)
    aware = datetime(2026, 7, 12, 3, 45, tzinfo=UTC)

    localized = normalizer().normalize(raw_tick(exchange_timestamp=naive)).timestamp
    assert localized == datetime(2026, 7, 12, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert localized.hour == 9
    assert localized.minute == 15
    assert normalizer().normalize(raw_tick(exchange_timestamp=aware)).timestamp is aware
    assert normalizer().normalize(raw_tick(exchange_timestamp=None, last_trade_time=aware)).timestamp is aware
    last_trade = normalizer().normalize(raw_tick(exchange_timestamp=None, last_trade_time=naive)).timestamp
    assert last_trade == datetime(2026, 7, 12, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert normalizer().normalize(raw_tick(exchange_timestamp=None, last_trade_time=None)).timestamp == NOW


def test_naive_clock_result_rejected():
    with pytest.raises(ValueError):
        normalizer(clock=lambda: datetime(2026, 7, 12)).normalize(raw_tick(exchange_timestamp=None, last_trade_time=None))


@pytest.mark.parametrize("bad_value", (object(), date(2026, 7, 12), True, "not-a-datetime", 123456))
def test_invalid_timestamp_values_are_rejected_without_epoch_fallback(bad_value):
    with pytest.raises((TypeError, ValueError)):
        normalizer().normalize(raw_tick(exchange_timestamp=bad_value))


def test_raw_payload_is_not_mutated_and_batch_order_preserved():
    first = raw_tick(last_price=25000.0)
    second = raw_tick(last_price=25001.0)
    original = deepcopy(first)

    ticks = normalizer().normalize_batch((first, second))

    assert first == original
    assert [tick.last_price for tick in ticks] == [25000.0, 25001.0]
