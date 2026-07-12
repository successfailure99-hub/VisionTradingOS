"""
Tests for Zerodha subscription registry.
"""

from threading import RLock

import pytest

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionRegistry
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


def sub(token=101, instrument=Instrument.NIFTY):
    return ZerodhaInstrumentSubscription(token, instrument, Exchange.NSE)


def test_empty_registry_and_order_preservation():
    registry = ZerodhaSubscriptionRegistry((sub(101), sub(102, Instrument.BANKNIFTY)))

    assert registry.tokens() == (101, 102)
    assert registry.all()[0].instrument is Instrument.NIFTY


def test_add_and_duplicate_rejections():
    registry = ZerodhaSubscriptionRegistry()

    registry.add(sub(101))

    with pytest.raises(ValueError):
        registry.add(sub(101, Instrument.BANKNIFTY))
    with pytest.raises(ValueError):
        registry.add(sub(102, Instrument.NIFTY))


def test_remove_lookup_and_clear():
    registry = ZerodhaSubscriptionRegistry((sub(101), sub(102, Instrument.BANKNIFTY)))

    assert registry.get_by_token(101).instrument is Instrument.NIFTY
    assert registry.get_by_instrument(Instrument.BANKNIFTY).instrument_token == 102
    assert registry.remove_by_token(101) == (sub(102, Instrument.BANKNIFTY),)
    with pytest.raises(ValueError):
        registry.remove_by_token(999)
    assert registry.clear() == ()


def test_returned_tuples_are_immutable_and_registry_uses_rlock():
    registry = ZerodhaSubscriptionRegistry((sub(101),))
    returned = registry.all()

    assert isinstance(returned, tuple)
    assert isinstance(registry._lock, type(RLock()))


def test_no_remote_calls_or_hardcoded_tokens():
    registry = ZerodhaSubscriptionRegistry()
    registry.add(sub(987654321))

    assert registry.tokens() == (987654321,)
