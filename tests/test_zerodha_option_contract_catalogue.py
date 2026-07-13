from datetime import date
from threading import RLock

import pytest

from brokers.zerodha.options import (
    ZerodhaDerivativeVenue,
    ZerodhaOptionContract,
    ZerodhaOptionContractCatalogue,
    ZerodhaOptionRight,
)
from core.enums.instrument import Instrument


def c(token, expiry=date(2026, 7, 30), strike=25000, right=ZerodhaOptionRight.CALL):
    return ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", expiry, strike, right, 75, 0.05)


def test_catalogue_order_duplicates_atomic_replace_lookup_filters_and_clear():
    item = ZerodhaOptionContractCatalogue()
    assert isinstance(item._lock, type(RLock()))
    assert item.all() == ()
    first = (c(1), c(2, strike=25100, right=ZerodhaOptionRight.PUT))
    assert item.replace(first) == first
    assert item.all() == first
    with pytest.raises(ValueError):
        item.replace((c(1), c(1, right=ZerodhaOptionRight.PUT)))
    assert item.all() == first
    with pytest.raises(ValueError):
        item.replace((c(3), c(4)))
    assert item.by_token(1) == c(1)
    assert item.contracts_for(Instrument.NIFTY, expiry=date(2026, 7, 30)) == first
    assert item.contracts_for(Instrument.NIFTY, strike=25000) == (c(1),)
    assert item.contracts_for(Instrument.NIFTY, right=ZerodhaOptionRight.PUT) == (first[1],)
    assert item.expiries(Instrument.NIFTY, as_of=date(2026, 7, 1)) == (date(2026, 7, 30),)
    assert item.expiries(Instrument.NIFTY, as_of=date(2026, 8, 1)) == ()
    with pytest.raises(AttributeError):
        item.all().append(c(9))
    assert item.clear() == first
    assert item.all() == ()
