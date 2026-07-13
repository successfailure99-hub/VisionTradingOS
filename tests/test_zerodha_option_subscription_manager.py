from datetime import UTC, date, datetime

import pytest

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode
from brokers.zerodha.option_market_data import (
    ZerodhaOptionMarketDataSubscriptionManager,
    ZerodhaOptionSubscriptionStatus,
)
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaExpiry, ZerodhaExpiryKind, ZerodhaOptionContract, ZerodhaOptionPair, ZerodhaOptionRight, ZerodhaOptionUniverse
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


EXP = date(2026, 7, 30)
NOW = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


class Transport:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def subscribe(self, tokens):
        self.calls.append(("subscribe", list(tokens)))
        if self.fail_at == "subscribe":
            raise RuntimeError("subscribe failed {'secret': 'x'}")

    def unsubscribe(self, tokens):
        self.calls.append(("unsubscribe", list(tokens)))
        if self.fail_at == "unsubscribe":
            raise RuntimeError("unsubscribe failed")

    def set_mode(self, mode, tokens):
        self.calls.append(("mode", mode, list(tokens)))
        if self.fail_at == "mode":
            raise RuntimeError("mode failed")


def contract(token, strike, right):
    return ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", EXP, strike, right, 75, 0.05)


def universe(tokens=(1, 2, 3, 4), mode=ZerodhaSubscriptionMode.FULL):
    pairs = (
        ZerodhaOptionPair(Instrument.NIFTY, ZerodhaExpiry(Instrument.NIFTY, EXP, ZerodhaExpiryKind.MONTHLY, 4, 2, 25000, 25100), 25000, contract(tokens[0], 25000, ZerodhaOptionRight.CALL), contract(tokens[1], 25000, ZerodhaOptionRight.PUT)),
        ZerodhaOptionPair(Instrument.NIFTY, ZerodhaExpiry(Instrument.NIFTY, EXP, ZerodhaExpiryKind.MONTHLY, 4, 2, 25000, 25100), 25100, contract(tokens[2], 25100, ZerodhaOptionRight.CALL), contract(tokens[3], 25100, ZerodhaOptionRight.PUT)),
    )
    subs = tuple(ZerodhaInstrumentSubscription(token, Instrument.NIFTY, Exchange.NSE, mode) for token in tokens)
    return ZerodhaOptionUniverse(Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, pairs[0].expiry, 25050, 25000, 100, pairs, subs, NOW)


def test_prepare_activate_deactivate_clear_and_idempotency():
    transport = Transport()
    manager = ZerodhaOptionMarketDataSubscriptionManager(transport=transport, clock=lambda: NOW)
    assert manager.snapshot().status is ZerodhaOptionSubscriptionStatus.CREATED
    prepared = manager.prepare(universe())
    assert prepared.status is ZerodhaOptionSubscriptionStatus.PREPARED
    assert transport.calls == []
    active = manager.activate()
    assert active.status is ZerodhaOptionSubscriptionStatus.ACTIVE
    assert transport.calls == [("subscribe", [1, 2, 3, 4]), ("mode", "full", [1, 2, 3, 4])]
    assert manager.activate().activation_count == 1
    manager.deactivate()
    assert transport.calls[-1] == ("unsubscribe", [1, 2, 3, 4])
    manager.activate()
    manager.deactivate()
    assert manager.clear().status is ZerodhaOptionSubscriptionStatus.CLEARED


def test_activation_and_deactivation_failures_preserve_state_and_errors():
    manager = ZerodhaOptionMarketDataSubscriptionManager(transport=Transport(fail_at="mode"), clock=lambda: NOW)
    manager.prepare(universe())
    with pytest.raises(RuntimeError):
        manager.activate()
    snapshot = manager.snapshot()
    assert snapshot.status is ZerodhaOptionSubscriptionStatus.ERROR
    assert not snapshot.active
    assert "secret" not in snapshot.last_error
    manager = ZerodhaOptionMarketDataSubscriptionManager(transport=Transport(fail_at="unsubscribe"), clock=lambda: NOW)
    manager.prepare(universe())
    manager.activate()
    with pytest.raises(RuntimeError):
        manager.deactivate()
    assert manager.snapshot().active
    with pytest.raises(RuntimeError):
        manager.clear()
