from datetime import date

import pytest

from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaOptionContract, ZerodhaOptionContractCatalogue, ZerodhaOptionRight, ZerodhaOptionStrikeResolver
from core.enums.instrument import Instrument


EXP = date(2026, 7, 30)


def c(token, strike, right):
    return ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", EXP, strike, right, 75, 0.05)


def cat(strikes=(24900, 24950, 25000, 25050, 25100), extra=()):
    rows = []
    token = 1
    for strike in strikes:
        rows.extend((c(token, strike, ZerodhaOptionRight.CALL), c(token + 1, strike, ZerodhaOptionRight.PUT)))
        token += 2
    rows.extend(extra)
    return ZerodhaOptionContractCatalogue(tuple(rows))


def test_available_strikes_step_atm_and_windows():
    resolver = ZerodhaOptionStrikeResolver(cat(extra=(c(99, 25200, ZerodhaOptionRight.CALL),)))
    assert resolver.available_strikes(Instrument.NIFTY, expiry=EXP) == (24900, 24950, 25000, 25050, 25100)
    assert resolver.infer_strike_step(Instrument.NIFTY, expiry=EXP) == 50
    assert ZerodhaOptionStrikeResolver(cat((100, 125, 150))).infer_strike_step(Instrument.NIFTY, expiry=EXP) == 25
    assert ZerodhaOptionStrikeResolver(cat((100, 200, 300))).infer_strike_step(Instrument.NIFTY, expiry=EXP) == 100
    assert resolver.resolve_atm(Instrument.NIFTY, expiry=EXP, underlying_price=25000) == 25000
    assert resolver.resolve_atm(Instrument.NIFTY, expiry=EXP, underlying_price=25020) == 25000
    assert resolver.resolve_atm(Instrument.NIFTY, expiry=EXP, underlying_price=25040) == 25050
    assert resolver.resolve_atm(Instrument.NIFTY, expiry=EXP, underlying_price=25025) == 25000
    assert resolver.strike_window(Instrument.NIFTY, expiry=EXP, underlying_price=25000, strikes_each_side=0) == (25000,)
    assert resolver.strike_window(Instrument.NIFTY, expiry=EXP, underlying_price=25000, strikes_each_side=1) == (24950, 25000, 25050)


def test_rejects_irregular_grid_too_few_invalid_spot_and_bad_wings():
    with pytest.raises(ValueError):
        ZerodhaOptionStrikeResolver(cat((100, 130, 200))).infer_strike_step(Instrument.NIFTY, expiry=EXP)
    with pytest.raises(ValueError):
        ZerodhaOptionStrikeResolver(cat((100,))).infer_strike_step(Instrument.NIFTY, expiry=EXP)
    resolver = ZerodhaOptionStrikeResolver(cat())
    with pytest.raises(ValueError):
        resolver.resolve_atm(Instrument.NIFTY, expiry=EXP, underlying_price=0)
    with pytest.raises(ValueError):
        resolver.strike_window(Instrument.NIFTY, expiry=EXP, underlying_price=24900, strikes_each_side=1)
    with pytest.raises(ValueError):
        resolver.strike_window(Instrument.NIFTY, expiry=EXP, underlying_price=25100, strikes_each_side=1)
    with pytest.raises(ValueError):
        resolver.strike_window(Instrument.NIFTY, expiry=EXP, underlying_price=25000, strikes_each_side=-1)
    with pytest.raises(TypeError):
        resolver.strike_window(Instrument.NIFTY, expiry=EXP, underlying_price=25000, strikes_each_side=True)
