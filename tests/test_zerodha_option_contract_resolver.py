from datetime import UTC, date, datetime

import pytest

from brokers.zerodha.market_data import ZerodhaSubscriptionMode
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaOptionContract, ZerodhaOptionContractCatalogue, ZerodhaOptionContractResolver, ZerodhaOptionRight
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


EXP = date(2026, 7, 30)


def c(token, underlying, venue, strike, right, expiry=EXP):
    return ZerodhaOptionContract(token, token, underlying, venue, f"{venue.value}-OPT", f"{underlying.value}{token}", underlying.value, expiry, strike, right, 75, 0.05)


def catalogue(underlying=Instrument.NIFTY, venue=ZerodhaDerivativeVenue.NFO):
    rows = []
    token = 1
    for exp in (date(2026, 7, 29), EXP):
        for strike in (24900, 24950, 25000, 25050, 25100):
            rows.extend((c(token, underlying, venue, strike, ZerodhaOptionRight.CALL, exp), c(token + 1, underlying, venue, strike, ZerodhaOptionRight.PUT, exp)))
            token += 2
    return ZerodhaOptionContractCatalogue(tuple(rows))


def test_resolves_pair_and_rejects_missing_sides():
    resolver = ZerodhaOptionContractResolver(catalogue(), clock=lambda: datetime(2026, 7, 10, tzinfo=UTC))
    expiry = resolver._expiry_resolver.resolve(Instrument.NIFTY, as_of=date(2026, 7, 1))
    assert resolver.resolve_pair(Instrument.NIFTY, expiry=expiry, strike=25000).call.right is ZerodhaOptionRight.CALL
    missing_ce = ZerodhaOptionContractCatalogue((c(1, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, 25000, ZerodhaOptionRight.PUT),))
    with pytest.raises(ValueError):
        ZerodhaOptionContractResolver(missing_ce).resolve_pair(Instrument.NIFTY, expiry=expiry, strike=25000)
    missing_pe = ZerodhaOptionContractCatalogue((c(2, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, 25000, ZerodhaOptionRight.CALL),))
    with pytest.raises(ValueError):
        ZerodhaOptionContractResolver(missing_pe).resolve_pair(Instrument.NIFTY, expiry=expiry, strike=25000)


def test_resolves_universe_for_nifty_banknifty_sensex_subscriptions_and_clock():
    for underlying, venue, exchange in (
        (Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, Exchange.NSE),
        (Instrument.BANKNIFTY, ZerodhaDerivativeVenue.NFO, Exchange.NSE),
        (Instrument.SENSEX, ZerodhaDerivativeVenue.BFO, Exchange.BSE),
    ):
        resolver = ZerodhaOptionContractResolver(catalogue(underlying, venue), clock=lambda: datetime(2026, 7, 10, 9, 15, tzinfo=UTC))
        universe = resolver.resolve_universe(underlying, as_of=date(2026, 7, 1), underlying_price=25000, strikes_each_side=1)
        assert [pair.strike for pair in universe.pairs] == [24950, 25000, 25050]
        assert universe.atm_strike == 25000
        assert len(universe.subscriptions) == len(universe.pairs) * 2
        assert all(subscription.exchange is exchange for subscription in universe.subscriptions)
        assert all(subscription.mode is ZerodhaSubscriptionMode.FULL for subscription in universe.subscriptions)
        explicit = resolver.resolve_universe(underlying, as_of=date(2026, 7, 1), explicit_expiry=EXP, expiry_selection=__import__("brokers.zerodha.options", fromlist=["ZerodhaExpirySelection"]).ZerodhaExpirySelection.EXPLICIT, underlying_price=25000, strikes_each_side=0, mode=ZerodhaSubscriptionMode.QUOTE)
        assert explicit.subscriptions[0].mode is ZerodhaSubscriptionMode.QUOTE
    with pytest.raises(ValueError):
        ZerodhaOptionContractResolver(catalogue(), clock=lambda: datetime(2026, 7, 10)).resolve_universe(Instrument.NIFTY, as_of=date(2026, 7, 1), underlying_price=25000, strikes_each_side=0)
