from datetime import date
from threading import RLock

import pytest

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.option_market_data import ZerodhaOptionSubscriptionEntry, ZerodhaOptionSubscriptionRegistry
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaOptionContract, ZerodhaOptionRight
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


EXP = date(2026, 7, 30)


def entry(token, strike=25000, right=ZerodhaOptionRight.CALL, underlying=Instrument.NIFTY, expiry=EXP):
    contract = ZerodhaOptionContract(token, token, underlying, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", underlying.value, expiry, strike, right, 75, 0.05)
    return ZerodhaOptionSubscriptionEntry(contract, ZerodhaInstrumentSubscription(token, underlying, Exchange.NSE))


def test_registry_order_lookup_filters_clear_and_lock():
    registry = ZerodhaOptionSubscriptionRegistry()
    assert isinstance(registry._lock, type(RLock()))
    assert registry.all() == ()
    rows = (entry(1), entry(2, right=ZerodhaOptionRight.PUT), entry(3, strike=25100))
    assert registry.replace(rows) == rows
    assert registry.all() == rows
    assert registry.tokens() == (1, 2, 3)
    assert registry.get_by_token(2) == rows[1]
    assert registry.contracts_for_strike(25000) == rows[:2]
    assert registry.entries_for_right(ZerodhaOptionRight.CALL) == (rows[0], rows[2])
    with pytest.raises(AttributeError):
        registry.all().append(rows[0])
    assert registry.clear() == rows
    assert registry.all() == ()


def test_registry_rejects_duplicates_mixed_groups_and_replace_is_atomic():
    registry = ZerodhaOptionSubscriptionRegistry((entry(1),))
    with pytest.raises(ValueError):
        registry.replace((entry(1), entry(1, right=ZerodhaOptionRight.PUT)))
    assert registry.tokens() == (1,)
    with pytest.raises(ValueError):
        registry.replace((entry(1), entry(2)))
    with pytest.raises(ValueError):
        registry.replace((entry(1), entry(2, expiry=date(2026, 8, 30))))
    with pytest.raises(ValueError):
        registry.replace((entry(1), entry(2, underlying=Instrument.BANKNIFTY)))
