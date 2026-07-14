from datetime import UTC, date, datetime

import pytest

from application.live_option_chain import ZerodhaLiveOptionQuoteNormalizer
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.option_market_data import ZerodhaOptionSubscriptionEntry
from brokers.zerodha.options import (
    ZerodhaDerivativeVenue,
    ZerodhaOptionContract,
    ZerodhaOptionRight,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def entry(token=1, underlying=Instrument.NIFTY, right=ZerodhaOptionRight.CALL):
    venue = ZerodhaDerivativeVenue.BFO if underlying is Instrument.SENSEX else ZerodhaDerivativeVenue.NFO
    exchange = Exchange.BSE if venue is ZerodhaDerivativeVenue.BFO else Exchange.NSE
    contract = ZerodhaOptionContract(
        token,
        token,
        underlying,
        venue,
        f"{venue.value}-OPT",
        f"{underlying.value}{token}",
        underlying.value,
        date(2026, 7, 30),
        25000,
        right,
        75,
        0.05,
    )
    return ZerodhaOptionSubscriptionEntry(
        contract,
        ZerodhaInstrumentSubscription(token, underlying, exchange),
    )


def test_normalizes_identity_from_entry_and_runtime_oi_change():
    normalizer = ZerodhaLiveOptionQuoteNormalizer(entries=(entry(),), clock=lambda: NOW)
    raw = {
        "instrument_token": 1,
        "last_price": 10,
        "volume": 5,
        "oi": 120,
        "exchange_timestamp": NOW,
        "depth": {"buy": [{"price": 9.5}], "sell": [{"price": 10.5}]},
        "tradingsymbol": "DO-NOT-TRUST",
    }
    before = dict(raw)
    quote = normalizer.normalize(raw, baseline_open_interest=100)
    assert quote.underlying is Instrument.NIFTY
    assert quote.right is ZerodhaOptionRight.CALL
    assert quote.runtime_change_open_interest == 20
    assert quote.bid_price == 9.5
    assert raw == before


def test_timestamps_underlyings_and_rejections():
    entries = (
        entry(1, Instrument.NIFTY, ZerodhaOptionRight.CALL),
        entry(2, Instrument.BANKNIFTY, ZerodhaOptionRight.PUT),
        entry(3, Instrument.SENSEX, ZerodhaOptionRight.CALL),
    )
    normalizer = ZerodhaLiveOptionQuoteNormalizer(entries=entries, clock=lambda: NOW)
    assert normalizer.normalize({"instrument_token": 2, "last_price": 1, "volume": 0, "oi": 1, "timestamp": "2026-07-14T09:15:00+05:30"}, baseline_open_interest=1).underlying is Instrument.BANKNIFTY
    assert normalizer.normalize({"instrument_token": 3, "last_price": 1, "volume": 0, "oi": 1, "timestamp": datetime(2026, 7, 14, 9, 15)}, baseline_open_interest=1).exchange_timestamp.tzinfo is not None
    assert normalizer.normalize({"instrument_token": 1, "last_price": 1, "volume": 0, "oi": 1}, baseline_open_interest=1).exchange_timestamp == NOW
    with pytest.raises(ValueError):
        normalizer.normalize({"instrument_token": 99, "last_price": 1, "volume": 0, "oi": 1}, baseline_open_interest=1)
    with pytest.raises(ValueError):
        normalizer.normalize({"instrument_token": 1, "last_price": -1, "volume": 0, "oi": 1}, baseline_open_interest=1)
    with pytest.raises(ValueError):
        normalizer.normalize({"instrument_token": 1, "last_price": 1, "volume": -1, "oi": 1}, baseline_open_interest=1)
    with pytest.raises(ValueError):
        normalizer.normalize({"instrument_token": 1, "last_price": 1, "volume": 0, "oi": -1}, baseline_open_interest=1)
    with pytest.raises(ValueError):
        normalizer.normalize({"instrument_token": 1, "last_price": 1, "volume": 0, "oi": 1, "depth": {"buy": [{"price": 2}], "sell": [{"price": 1}]}}, baseline_open_interest=1)
