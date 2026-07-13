from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.options import (
    ZerodhaDerivativeVenue,
    ZerodhaExpiry,
    ZerodhaExpiryKind,
    ZerodhaOptionContract,
    ZerodhaOptionDiscoverySnapshot,
    ZerodhaOptionDiscoveryStatus,
    ZerodhaOptionPair,
    ZerodhaOptionRight,
    ZerodhaOptionUniverse,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


EXP = date(2026, 7, 30)
TS = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


def contract(token=1, *, underlying=Instrument.NIFTY, venue=ZerodhaDerivativeVenue.NFO, strike=25000, right=ZerodhaOptionRight.CALL):
    return ZerodhaOptionContract(token, token + 1000, underlying, venue, f"{venue.value}-OPT", f"{underlying.value}{token}", underlying.value, EXP, strike, right, 75, 0.05)


def expiry(underlying=Instrument.NIFTY):
    return ZerodhaExpiry(underlying, EXP, ZerodhaExpiryKind.MONTHLY, 2, 1, 25000, 25000)


def pair():
    return ZerodhaOptionPair(Instrument.NIFTY, expiry(), 25000, contract(1), contract(2, right=ZerodhaOptionRight.PUT))


def test_valid_contracts_for_supported_underlyings_and_validation():
    assert contract().underlying is Instrument.NIFTY
    assert contract(3, underlying=Instrument.BANKNIFTY).underlying is Instrument.BANKNIFTY
    assert contract(5, underlying=Instrument.SENSEX, venue=ZerodhaDerivativeVenue.BFO).venue is ZerodhaDerivativeVenue.BFO
    with pytest.raises((TypeError, ValueError)):
        contract(0)
    with pytest.raises(TypeError):
        contract(True)
    with pytest.raises(ValueError):
        contract(7, underlying=Instrument.SENSEX, venue=ZerodhaDerivativeVenue.NFO)
    with pytest.raises(ValueError):
        ZerodhaOptionContract(8, 9, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-FUT", "N", "NIFTY", EXP, 1, ZerodhaOptionRight.CALL, 1, 0.05)
    with pytest.raises(TypeError):
        ZerodhaOptionContract(8, 9, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", "N", "NIFTY", datetime(2026, 7, 30), 1, ZerodhaOptionRight.CALL, 1, 0.05)
    with pytest.raises(ValueError):
        contract(9, strike=0)
    with pytest.raises(ValueError):
        ZerodhaOptionContract(10, 11, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", "N", "NIFTY", EXP, 1, ZerodhaOptionRight.CALL, 0, 0.05)
    with pytest.raises(ValueError):
        ZerodhaOptionContract(10, 11, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", "N", "NIFTY", EXP, 1, ZerodhaOptionRight.CALL, 1, 0)


def test_pair_universe_snapshot_immutability_and_no_quote_fields():
    item = pair()
    with pytest.raises(FrozenInstanceError):
        item.strike = 1
    with pytest.raises(ValueError):
        ZerodhaOptionPair(Instrument.NIFTY, expiry(), 25000, contract(1), contract(2))
    with pytest.raises(ValueError):
        ZerodhaOptionPair(Instrument.NIFTY, expiry(), 25000, contract(1), contract(1, right=ZerodhaOptionRight.PUT))
    subscriptions = (
        ZerodhaInstrumentSubscription(1, Instrument.NIFTY, Exchange.NSE),
        ZerodhaInstrumentSubscription(2, Instrument.NIFTY, Exchange.NSE),
    )
    universe = ZerodhaOptionUniverse(Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, expiry(), 25001, 25000, 50, (item,), subscriptions, TS)
    assert universe.subscriptions == subscriptions
    assert universe.atm_strike == 25000
    with pytest.raises(FrozenInstanceError):
        universe.atm_strike = 1
    snapshot = ZerodhaOptionDiscoverySnapshot(ZerodhaOptionDiscoveryStatus.READY, 2, 2, (Instrument.NIFTY,), 1, (ZerodhaDerivativeVenue.NFO,), TS, None)
    assert snapshot.supported_contract_count == 2
    assert "api_key" not in repr(universe)
    assert not hasattr(contract(), "oi")
    assert not hasattr(contract(), "last_price")
