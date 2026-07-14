from datetime import UTC, date, datetime, timedelta

import pytest

from application.live_option_chain import LiveOptionChainAssembler, LiveOptionChainConfiguration, ZerodhaLiveOptionQuote
from application.live_option_chain.assembler import IncompleteLiveOptionChainError, StaleLiveOptionQuoteError
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaExpiry, ZerodhaExpiryKind, ZerodhaOptionContract, ZerodhaOptionPair, ZerodhaOptionRight, ZerodhaOptionUniverse
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from engines.option_chain.models import OptionChainSnapshot


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def contract(token, strike, right):
    return ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", date(2026, 7, 30), strike, right, 75, 0.05)


def universe():
    exp = ZerodhaExpiry(Instrument.NIFTY, date(2026, 7, 30), ZerodhaExpiryKind.MONTHLY, 4, 2, 25000, 25100)
    pairs = (
        ZerodhaOptionPair(Instrument.NIFTY, exp, 25000, contract(1, 25000, ZerodhaOptionRight.CALL), contract(2, 25000, ZerodhaOptionRight.PUT)),
        ZerodhaOptionPair(Instrument.NIFTY, exp, 25100, contract(3, 25100, ZerodhaOptionRight.CALL), contract(4, 25100, ZerodhaOptionRight.PUT)),
    )
    subs = tuple(ZerodhaInstrumentSubscription(token, Instrument.NIFTY, Exchange.NSE) for token in (1, 2, 3, 4))
    return ZerodhaOptionUniverse(Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, exp, 25050, 25000, 100, pairs, subs, NOW)


def quote(token, strike, right, ts=NOW, change=0):
    return ZerodhaLiveOptionQuote(token, Instrument.NIFTY, date(2026, 7, 30), strike, right, 10 + token, token, 100 + token, change, 9.5, 10.5, ts, NOW)


def full_quotes(ts=NOW):
    return (
        quote(1, 25000, ZerodhaOptionRight.CALL, ts, 1),
        quote(2, 25000, ZerodhaOptionRight.PUT, ts, 2),
        quote(3, 25100, ZerodhaOptionRight.CALL, ts, 3),
        quote(4, 25100, ZerodhaOptionRight.PUT, ts, 4),
    )


def test_complete_assembly_reuses_existing_models_and_maps_fields():
    snapshot = LiveOptionChainAssembler(universe=universe(), configuration=LiveOptionChainConfiguration()).assemble(
        quotes=full_quotes(),
        underlying_price=25050,
        timestamp=NOW,
    )
    assert isinstance(snapshot, OptionChainSnapshot)
    assert tuple(strike.strike_price for strike in snapshot.strikes) == (25000, 25100)
    assert snapshot.strikes[0].call.open_interest == 101
    assert snapshot.strikes[0].call.change_in_open_interest == 1
    assert snapshot.strikes[0].put.volume == 2
    assert snapshot.strikes[0].call.bid_price == 9.5


def test_missing_stale_and_wrong_context_rejected():
    strict = LiveOptionChainAssembler(universe=universe(), configuration=LiveOptionChainConfiguration())
    with pytest.raises(IncompleteLiveOptionChainError):
        strict.assemble(quotes=full_quotes()[:3], underlying_price=25050, timestamp=NOW)
    partial = LiveOptionChainAssembler(universe=universe(), configuration=LiveOptionChainConfiguration(require_all_pairs=False))
    assert len(partial.assemble(quotes=full_quotes()[:2], underlying_price=25050, timestamp=NOW).strikes) == 1
    with pytest.raises(StaleLiveOptionQuoteError):
        strict.assemble(quotes=full_quotes(NOW - timedelta(seconds=20)), underlying_price=25050, timestamp=NOW)
    wrong = quote(1, 25000, ZerodhaOptionRight.CALL)
    wrong = ZerodhaLiveOptionQuote(wrong.instrument_token, Instrument.BANKNIFTY, wrong.expiry, wrong.strike, wrong.right, wrong.last_price, wrong.volume, wrong.open_interest, wrong.runtime_change_open_interest, wrong.bid_price, wrong.ask_price, wrong.exchange_timestamp, wrong.received_at)
    with pytest.raises(ValueError):
        strict.assemble(quotes=(wrong,) + full_quotes()[1:], underlying_price=25050, timestamp=NOW)
    assert not hasattr(strict, "pcr")
    assert not hasattr(strict, "max_pain")
