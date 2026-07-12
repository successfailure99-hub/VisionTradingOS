"""
Tests for deterministic Zerodha index subscription resolver.
"""

import pytest

from brokers.zerodha.instruments import (
    ZerodhaIndexSubscriptionResolver,
    ZerodhaInstrumentCatalogue,
    ZerodhaInstrumentRecord,
    ZerodhaInstrumentType,
)
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


def rec(token, symbol, name=None, exchange=Exchange.NSE, kind=ZerodhaInstrumentType.INDEX, expiry=None):
    return ZerodhaInstrumentRecord(token, token + 1000, symbol, name or symbol, exchange, "INDICES", kind, expiry, 0.0, 1, 0.05)


def resolver(*records):
    return ZerodhaIndexSubscriptionResolver(ZerodhaInstrumentCatalogue(tuple(records)))


def test_resolves_canonical_and_fallback_index_aliases():
    assert resolver(rec(101, "NIFTY 50")).resolve(Instrument.NIFTY).subscription.instrument_token == 101
    assert resolver(rec(102, "NIFTY")).resolve(Instrument.NIFTY).subscription.instrument_token == 102
    assert resolver(rec(201, "NIFTY BANK")).resolve(Instrument.BANKNIFTY).subscription.instrument_token == 201
    assert resolver(rec(202, "BANKNIFTY")).resolve(Instrument.BANKNIFTY).subscription.instrument_token == 202
    assert resolver(rec(301, "SENSEX", exchange=Exchange.BSE)).resolve(Instrument.SENSEX).subscription.instrument_token == 301
    assert resolver(rec(302, "S&P BSE SENSEX", exchange=Exchange.BSE)).resolve(Instrument.SENSEX).subscription.instrument_token == 302


def test_correct_exchange_mode_token_and_existing_subscription_contract():
    result = resolver(rec(101, "NIFTY 50")).resolve(Instrument.NIFTY, mode=ZerodhaSubscriptionMode.LTP)
    assert result.record.exchange is Exchange.NSE
    assert result.subscription.instrument_token == 101
    assert result.subscription.mode is ZerodhaSubscriptionMode.LTP
    assert isinstance(result.subscription, ZerodhaInstrumentSubscription)


def test_empty_missing_ambiguous_wrong_exchange_and_unsupported_rejected():
    with pytest.raises(ValueError):
        resolver().resolve(Instrument.NIFTY)
    with pytest.raises(ValueError):
        resolver(rec(101, "OTHER")).resolve(Instrument.NIFTY)
    with pytest.raises(ValueError):
        resolver(rec(101, "NIFTY 50"), rec(102, "NIFTY 50")).resolve(Instrument.NIFTY)
    with pytest.raises(ValueError):
        resolver(rec(101, "SENSEX", exchange=Exchange.NSE)).resolve(Instrument.SENSEX)
    with pytest.raises(ValueError):
        resolver(rec(101, "SBIN", kind=ZerodhaInstrumentType.EQUITY)).resolve(Instrument.SBI)


def test_higher_priority_unique_match_wins_but_derivatives_equity_expiry_and_partial_text_rejected():
    result = resolver(rec(101, "NIFTY 50"), rec(102, "NIFTY")).resolve(Instrument.NIFTY)
    assert result.subscription.instrument_token == 101
    for bad in (
        rec(201, "NIFTY 50", kind=ZerodhaInstrumentType.FUTURE),
        rec(202, "NIFTY 50", kind=ZerodhaInstrumentType.OPTION),
        rec(203, "NIFTY 50", kind=ZerodhaInstrumentType.EQUITY),
        rec(204, "NIFTY 50", expiry=__import__("datetime").date(2026, 7, 30)),
        rec(205, "NIFTY 50 EXTRA"),
    ):
        with pytest.raises(ValueError):
            resolver(bad).resolve(Instrument.NIFTY)


def test_resolve_many_preserves_order_rejects_duplicates_and_does_not_hardcode_tokens():
    subject = resolver(
        rec(909, "SENSEX", exchange=Exchange.BSE),
        rec(808, "NIFTY BANK"),
        rec(707, "NIFTY 50"),
    )
    results = subject.resolve_many((Instrument.SENSEX, Instrument.NIFTY, Instrument.BANKNIFTY))
    assert [item.subscription.instrument_token for item in results] == [909, 707, 808]
    with pytest.raises(ValueError):
        subject.resolve_many((Instrument.NIFTY, Instrument.NIFTY))
