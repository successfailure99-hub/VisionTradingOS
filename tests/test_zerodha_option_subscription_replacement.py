from datetime import UTC, date, datetime

import pytest

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode
from brokers.zerodha.option_market_data import ZerodhaOptionMarketDataSubscriptionManager, ZerodhaOptionSubscriptionStatus
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaExpiry, ZerodhaExpiryKind, ZerodhaOptionContract, ZerodhaOptionPair, ZerodhaOptionRight, ZerodhaOptionUniverse
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 10, tzinfo=UTC)


class Transport:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def subscribe(self, tokens):
        self.calls.append(("subscribe", list(tokens)))
        if self.fail_at == "subscribe":
            raise RuntimeError("subscribe failed")

    def unsubscribe(self, tokens):
        self.calls.append(("unsubscribe", list(tokens)))
        if self.fail_at == "unsubscribe":
            raise RuntimeError("unsubscribe failed")

    def set_mode(self, mode, tokens):
        self.calls.append(("mode", mode, list(tokens)))
        if self.fail_at == "mode":
            raise RuntimeError("mode failed")


def universe(expiry=date(2026, 7, 30), tokens=(1, 2, 3, 4), strikes=(25000, 25100), mode=ZerodhaSubscriptionMode.FULL):
    exp = ZerodhaExpiry(Instrument.NIFTY, expiry, ZerodhaExpiryKind.MONTHLY, 4, 2, strikes[0], strikes[1])
    pairs = (
        ZerodhaOptionPair(Instrument.NIFTY, exp, strikes[0], _c(tokens[0], expiry, strikes[0], ZerodhaOptionRight.CALL), _c(tokens[1], expiry, strikes[0], ZerodhaOptionRight.PUT)),
        ZerodhaOptionPair(Instrument.NIFTY, exp, strikes[1], _c(tokens[2], expiry, strikes[1], ZerodhaOptionRight.CALL), _c(tokens[3], expiry, strikes[1], ZerodhaOptionRight.PUT)),
    )
    subs = tuple(ZerodhaInstrumentSubscription(token, Instrument.NIFTY, Exchange.NSE, mode) for token in tokens)
    return ZerodhaOptionUniverse(Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, exp, strikes[0], strikes[0], 100, pairs, subs, NOW)


def _c(token, expiry, strike, right):
    return ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", expiry, strike, right, 75, 0.05)


def active_manager(transport):
    manager = ZerodhaOptionMarketDataSubscriptionManager(transport=transport, clock=lambda: NOW)
    manager.prepare(universe())
    manager.activate()
    transport.calls.clear()
    return manager


def test_replace_recenter_rollover_mode_only_and_idempotent():
    transport = Transport()
    manager = active_manager(transport)
    manager.replace(universe(tokens=(3, 4, 5, 6), strikes=(25100, 25200)))
    assert transport.calls[0] == ("subscribe", [5, 6])
    assert transport.calls[-1] == ("unsubscribe", [1, 2])
    assert manager.snapshot().replacement_count == 1
    transport.calls.clear()
    manager.replace(universe(tokens=(3, 4, 5, 6), strikes=(25100, 25200)))
    assert transport.calls == []
    manager.replace(universe(expiry=date(2026, 8, 30), tokens=(7, 8, 9, 10)))
    assert manager.snapshot().expiry == date(2026, 8, 30)


def test_failed_replace_preserves_old_registry_and_active_flag():
    transport = Transport()
    manager = active_manager(transport)

    before = manager.snapshot()
    before_entries = before.entries

    assert before.active is True
    assert tuple(
        entry.subscription.instrument_token
        for entry in before_entries
    ) == (1, 2, 3, 4)

    transport.calls.clear()
    transport.fail_at = "mode"

    with pytest.raises(RuntimeError, match="mode failed"):
        manager.replace(universe(tokens=(3, 4, 5, 6), strikes=(25100, 25200)))

    after = manager.snapshot()

    assert after.active is True
    assert after.entries == before_entries
    assert tuple(
        entry.subscription.instrument_token
        for entry in after.entries
    ) == (1, 2, 3, 4)

    assert after.status is ZerodhaOptionSubscriptionStatus.ERROR
    assert after.replacement_count == before.replacement_count
    assert (
        after.failed_operation_count
        == before.failed_operation_count + 1
    )
    assert "mode failed" in (after.last_error or "")

    assert ("subscribe", [5, 6]) in transport.calls
    assert ("unsubscribe", [5, 6]) in transport.calls
