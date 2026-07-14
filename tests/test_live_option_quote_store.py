from datetime import UTC, date, datetime, timedelta

import pytest

from application.live_option_chain import LiveOptionQuoteStore, LiveOptionQuoteUpdateResult, ZerodhaLiveOptionQuote
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.option_market_data import ZerodhaOptionSubscriptionEntry
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaOptionContract, ZerodhaOptionRight
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def entries():
    result = []
    for token, right in ((1, ZerodhaOptionRight.CALL), (2, ZerodhaOptionRight.PUT)):
        contract = ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", date(2026, 7, 30), 25000, right, 75, 0.05)
        result.append(ZerodhaOptionSubscriptionEntry(contract, ZerodhaInstrumentSubscription(token, Instrument.NIFTY, Exchange.NSE)))
    return tuple(result)


def quote(token=1, ts=NOW, oi=100):
    return ZerodhaLiveOptionQuote(token, Instrument.NIFTY, date(2026, 7, 30), 25000, ZerodhaOptionRight.CALL if token == 1 else ZerodhaOptionRight.PUT, 10, 1, oi, 0, None, None, ts, NOW)


def test_store_order_baselines_duplicates_stale_and_reset():
    store = LiveOptionQuoteStore(entries())
    assert store.baseline_for(1, current_open_interest=100) == 100
    store.seed_open_interest_baselines({1: 90})
    assert store.baseline_for(1, current_open_interest=100) == 90
    assert store.update(quote(1)) is LiveOptionQuoteUpdateResult.ACCEPTED
    assert store.update(quote(1)) is LiveOptionQuoteUpdateResult.DUPLICATE
    assert store.update(quote(1, NOW - timedelta(seconds=1))) is LiveOptionQuoteUpdateResult.STALE
    assert store.update(quote(1, NOW, 101)) is LiveOptionQuoteUpdateResult.ACCEPTED
    store.update(quote(2))
    assert tuple(item.instrument_token for item in store.all_latest()) == (1, 2)
    with pytest.raises(ValueError):
        store.update(quote(99))
    store.reset(entries())
    assert store.all_latest() == ()
    assert store.baselines() == ()


def test_underlying_price_and_immutability():
    store = LiveOptionQuoteStore(entries())
    store.set_underlying_price(25000, timestamp=NOW)
    assert store.underlying_price == 25000
    with pytest.raises(ValueError):
        store.set_underlying_price(25001, timestamp=NOW - timedelta(seconds=1))
    store.update(quote(1))
    latest = store.all_latest()
    assert isinstance(latest, tuple)
    with pytest.raises(TypeError):
        latest[0] = quote(2)
