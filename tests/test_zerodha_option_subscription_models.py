from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.option_market_data import (
    ZerodhaOptionSubscriptionBatchResult,
    ZerodhaOptionSubscriptionEntry,
    ZerodhaOptionSubscriptionOperation,
    ZerodhaOptionSubscriptionPlan,
    ZerodhaOptionSubscriptionSnapshot,
    ZerodhaOptionSubscriptionStatus,
    entries_from_universe,
)
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaOptionContract, ZerodhaOptionRight
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


EXP = date(2026, 7, 30)
NOW = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


def contract(token=1, right=ZerodhaOptionRight.CALL, strike=25000):
    return ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", EXP, strike, right, 75, 0.05)


def entry(token=1, right=ZerodhaOptionRight.CALL, strike=25000, exchange=Exchange.NSE):
    return ZerodhaOptionSubscriptionEntry(contract(token, right, strike), ZerodhaInstrumentSubscription(token, Instrument.NIFTY, exchange))


def test_entry_validation_immutability_and_secret_absence():
    item = entry()
    assert item.subscription.instrument_token == item.contract.instrument_token
    with pytest.raises(FrozenInstanceError):
        item.contract = contract(2)
    with pytest.raises(ValueError):
        ZerodhaOptionSubscriptionEntry(contract(1), ZerodhaInstrumentSubscription(2, Instrument.NIFTY, Exchange.NSE))
    with pytest.raises(ValueError):
        ZerodhaOptionSubscriptionEntry(contract(1), ZerodhaInstrumentSubscription(1, Instrument.BANKNIFTY, Exchange.NSE))
    with pytest.raises(ValueError):
        ZerodhaOptionSubscriptionEntry(contract(1), ZerodhaInstrumentSubscription(1, Instrument.NIFTY, Exchange.BSE))
    assert "api_key" not in repr(item)
    assert not hasattr(item, "client")
    assert not hasattr(item, "last_price")


def test_plan_batch_snapshot_validation_and_immutability():
    current = (entry(1),)
    proposed = (entry(1), entry(2, ZerodhaOptionRight.PUT))
    plan = ZerodhaOptionSubscriptionPlan(Instrument.NIFTY, EXP, current, proposed, (proposed[1],), (), (), (proposed[0],))
    with pytest.raises(FrozenInstanceError):
        plan.underlying = Instrument.SENSEX
    result = ZerodhaOptionSubscriptionBatchResult(ZerodhaOptionSubscriptionOperation.ACTIVATE, (1,), (), (1,), (1,), NOW)
    assert result.active_tokens == (1,)
    with pytest.raises(ValueError):
        ZerodhaOptionSubscriptionBatchResult(ZerodhaOptionSubscriptionOperation.ACTIVATE, (1, 1), (), (), (), NOW)
    snapshot = ZerodhaOptionSubscriptionSnapshot(
        ZerodhaOptionSubscriptionStatus.ACTIVE,
        Instrument.NIFTY,
        EXP,
        proposed,
        True,
        True,
        1,
        1,
        0,
        1,
        0,
        0,
        2,
        ZerodhaOptionSubscriptionOperation.ACTIVATE,
        result,
        NOW,
        NOW,
        None,
    )
    assert snapshot.active
    with pytest.raises(FrozenInstanceError):
        snapshot.active = False
    with pytest.raises(ValueError):
        ZerodhaOptionSubscriptionSnapshot(ZerodhaOptionSubscriptionStatus.ACTIVE, None, None, (), True, False, 0, 0, 0, 0, 0, 0, 0, None, None, None, None, None)
