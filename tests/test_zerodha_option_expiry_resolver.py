from datetime import date, datetime

import pytest

from brokers.zerodha.options import (
    ZerodhaDerivativeVenue,
    ZerodhaExpiryKind,
    ZerodhaExpirySelection,
    ZerodhaOptionContract,
    ZerodhaOptionContractCatalogue,
    ZerodhaOptionExpiryResolver,
    ZerodhaOptionRight,
)
from core.enums.instrument import Instrument


def c(token, exp, strike=25000, right=ZerodhaOptionRight.CALL):
    return ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", exp, strike, right, 75, 0.05)


def catalogue():
    rows = []
    token = 1
    for exp in (date(2026, 7, 27), date(2026, 7, 29), date(2026, 8, 3)):
        for strike in (25000, 25100):
            rows.extend((c(token, exp, strike), c(token + 1, exp, strike, ZerodhaOptionRight.PUT)))
            token += 2
    return ZerodhaOptionContractCatalogue(tuple(rows))


def test_lists_and_classifies_without_weekday_assumptions_and_resolves_selection():
    resolver = ZerodhaOptionExpiryResolver(catalogue())
    expiries = resolver.list_expiries(Instrument.NIFTY, as_of=date(2026, 7, 1))
    assert [item.expiry for item in expiries] == [date(2026, 7, 27), date(2026, 7, 29), date(2026, 8, 3)]
    assert [item.kind for item in expiries] == [ZerodhaExpiryKind.WEEKLY, ZerodhaExpiryKind.MONTHLY, ZerodhaExpiryKind.MONTHLY]
    assert expiries[0].contract_count == 4
    assert expiries[0].strike_count == 2
    assert resolver.resolve(Instrument.NIFTY, as_of=date(2026, 7, 1)).expiry == date(2026, 7, 27)
    assert resolver.resolve(Instrument.NIFTY, as_of=date(2026, 7, 1), selection=ZerodhaExpirySelection.NEXT).expiry == date(2026, 7, 29)
    assert resolver.resolve(Instrument.NIFTY, as_of=date(2026, 7, 1), selection=ZerodhaExpirySelection.CURRENT_WEEKLY).expiry == date(2026, 7, 27)
    assert resolver.resolve(Instrument.NIFTY, as_of=date(2026, 7, 1), selection=ZerodhaExpirySelection.CURRENT_MONTHLY).expiry == date(2026, 7, 29)
    assert resolver.resolve(Instrument.NIFTY, as_of=date(2026, 7, 1), selection=ZerodhaExpirySelection.NEXT_MONTHLY).expiry == date(2026, 8, 3)
    assert resolver.resolve(Instrument.NIFTY, as_of=date(2026, 7, 1), selection=ZerodhaExpirySelection.EXPLICIT, explicit_expiry=date(2026, 7, 29)).kind is ZerodhaExpiryKind.MONTHLY


def test_rejects_invalid_expiry_resolution_inputs_and_missing_fallbacks():
    resolver = ZerodhaOptionExpiryResolver(catalogue())
    with pytest.raises(TypeError):
        resolver.resolve(Instrument.NIFTY, as_of=datetime(2026, 7, 1))
    with pytest.raises(ValueError):
        resolver.resolve(Instrument.NIFTY, as_of=date(2026, 7, 1), selection=ZerodhaExpirySelection.EXPLICIT)
    with pytest.raises(ValueError):
        resolver.resolve(Instrument.NIFTY, as_of=date(2026, 8, 1), selection=ZerodhaExpirySelection.EXPLICIT, explicit_expiry=date(2026, 7, 29))
    with pytest.raises(ValueError):
        resolver.resolve(Instrument.NIFTY, as_of=date(2026, 7, 1), explicit_expiry=date(2026, 7, 29))
    with pytest.raises(ValueError):
        resolver.resolve(Instrument.NIFTY, as_of=date(2026, 7, 1), selection=ZerodhaExpirySelection.NEXT_WEEKLY)
    with pytest.raises(ValueError):
        ZerodhaOptionExpiryResolver(ZerodhaOptionContractCatalogue()).resolve(Instrument.NIFTY, as_of=date(2026, 7, 1))
    with pytest.raises(ValueError):
        resolver.list_expiries(Instrument.FINNIFTY, as_of=date(2026, 7, 1))
