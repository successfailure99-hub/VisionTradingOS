"""Phase 2 regression tests for dynamic option subscription recovery."""

from datetime import UTC, date, datetime

import pytest

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode
from brokers.zerodha.option_market_data import (
    ZerodhaOptionMarketDataSubscriptionManager,
    ZerodhaOptionSubscriptionOperation,
    ZerodhaOptionSubscriptionStatus,
)
from brokers.zerodha.options import (
    ZerodhaDerivativeVenue,
    ZerodhaExpiry,
    ZerodhaExpiryKind,
    ZerodhaOptionContract,
    ZerodhaOptionPair,
    ZerodhaOptionRight,
    ZerodhaOptionUniverse,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


class FakeTransport:
    def __init__(self):
        self.subscribe_calls = []
        self.unsubscribe_calls = []
        self.mode_calls = []
        self.fail_subscribe = None

    def subscribe(self, instrument_tokens):
        if self.fail_subscribe is not None:
            raise self.fail_subscribe
        self.subscribe_calls.append(list(instrument_tokens))

    def unsubscribe(self, instrument_tokens):
        self.unsubscribe_calls.append(list(instrument_tokens))

    def set_mode(self, mode, instrument_tokens):
        self.mode_calls.append((mode, list(instrument_tokens)))


def _universe() -> ZerodhaOptionUniverse:
    expiry_date = date(2026, 8, 27)
    expiry = ZerodhaExpiry(
        underlying=Instrument.NIFTY,
        expiry=expiry_date,
        kind=ZerodhaExpiryKind.WEEKLY,
        contract_count=2,
        strike_count=1,
        first_strike=25000.0,
        last_strike=25000.0,
    )
    call = ZerodhaOptionContract(
        instrument_token=1001,
        exchange_token=501,
        underlying=Instrument.NIFTY,
        venue=ZerodhaDerivativeVenue.NFO,
        segment="NFO-OPT",
        tradingsymbol="NIFTY26AUG25000CE",
        name="NIFTY",
        expiry=expiry_date,
        strike=25000.0,
        right=ZerodhaOptionRight.CALL,
        lot_size=65,
        tick_size=0.05,
    )
    put = ZerodhaOptionContract(
        instrument_token=1002,
        exchange_token=502,
        underlying=Instrument.NIFTY,
        venue=ZerodhaDerivativeVenue.NFO,
        segment="NFO-OPT",
        tradingsymbol="NIFTY26AUG25000PE",
        name="NIFTY",
        expiry=expiry_date,
        strike=25000.0,
        right=ZerodhaOptionRight.PUT,
        lot_size=65,
        tick_size=0.05,
    )
    pair = ZerodhaOptionPair(
        underlying=Instrument.NIFTY,
        expiry=expiry,
        strike=25000.0,
        call=call,
        put=put,
    )
    subscriptions = (
        ZerodhaInstrumentSubscription(1001, Instrument.NIFTY, Exchange.NSE, ZerodhaSubscriptionMode.FULL),
        ZerodhaInstrumentSubscription(1002, Instrument.NIFTY, Exchange.NSE, ZerodhaSubscriptionMode.FULL),
    )
    return ZerodhaOptionUniverse(
        underlying=Instrument.NIFTY,
        venue=ZerodhaDerivativeVenue.NFO,
        expiry=expiry,
        underlying_price=25012.5,
        atm_strike=25000.0,
        strike_step=50.0,
        pairs=(pair,),
        subscriptions=subscriptions,
        resolved_at=datetime(2026, 8, 21, 6, 0, tzinfo=UTC),
    )


def test_recover_reapplies_authoritative_active_tokens_and_modes():
    transport = FakeTransport()
    manager = ZerodhaOptionMarketDataSubscriptionManager(
        transport=transport,
        clock=lambda: datetime(2026, 8, 21, 6, 0, tzinfo=UTC),
    )
    manager.prepare(_universe())
    manager.activate()
    transport.subscribe_calls.clear()
    transport.mode_calls.clear()

    snapshot = manager.recover()

    assert transport.subscribe_calls == [[1001, 1002]]
    assert transport.mode_calls == [("full", [1001, 1002])]
    assert snapshot.status is ZerodhaOptionSubscriptionStatus.ACTIVE
    assert snapshot.active is True
    assert snapshot.last_operation is ZerodhaOptionSubscriptionOperation.RECOVER
    assert snapshot.last_result.operation is ZerodhaOptionSubscriptionOperation.RECOVER
    assert snapshot.last_result.active_tokens == (1001, 1002)
    assert snapshot.activation_count == 1


def test_recover_requires_active_registry():
    manager = ZerodhaOptionMarketDataSubscriptionManager(
        transport=FakeTransport(),
        clock=lambda: datetime(2026, 8, 21, 6, 0, tzinfo=UTC),
    )
    manager.prepare(_universe())

    with pytest.raises(RuntimeError, match="recover requires active subscriptions"):
        manager.recover()


def test_failed_recovery_preserves_logical_active_registry_for_next_attempt():
    transport = FakeTransport()
    manager = ZerodhaOptionMarketDataSubscriptionManager(
        transport=transport,
        clock=lambda: datetime(2026, 8, 21, 6, 0, tzinfo=UTC),
    )
    manager.prepare(_universe())
    manager.activate()
    transport.fail_subscribe = RuntimeError("socket unavailable")

    with pytest.raises(RuntimeError, match="socket unavailable"):
        manager.recover()

    snapshot = manager.snapshot()
    assert snapshot.status is ZerodhaOptionSubscriptionStatus.ERROR
    assert snapshot.active is True
    assert snapshot.prepared is True
    assert snapshot.last_operation is ZerodhaOptionSubscriptionOperation.RECOVER
    assert snapshot.failed_operation_count == 1
