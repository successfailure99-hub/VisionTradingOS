from datetime import date

import pytest

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode
from brokers.zerodha.option_market_data import ZerodhaOptionSubscriptionEntry, ZerodhaOptionSubscriptionPlanner
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaOptionContract, ZerodhaOptionRight
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


EXP = date(2026, 7, 30)


def entry(token, strike=25000, right=ZerodhaOptionRight.CALL, mode=ZerodhaSubscriptionMode.FULL, expiry=EXP):
    contract = ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", expiry, strike, right, 75, 0.05)
    return ZerodhaOptionSubscriptionEntry(contract, ZerodhaInstrumentSubscription(token, Instrument.NIFTY, Exchange.NSE, mode))


def test_plans_empty_identical_added_removed_modes_and_rollover():
    planner = ZerodhaOptionSubscriptionPlanner()
    proposed = (entry(1), entry(2, right=ZerodhaOptionRight.PUT))
    plan = planner.plan((), proposed)
    assert plan.subscribe_entries == proposed
    same = planner.plan(proposed, proposed)
    assert same.unchanged_entries == proposed
    added = planner.plan((entry(1),), proposed)
    assert added.subscribe_entries == (proposed[1],)
    removed = planner.plan(proposed, (entry(1),))
    assert removed.unsubscribe_entries == (proposed[1],)
    changed = planner.plan((entry(1),), (entry(1, mode=ZerodhaSubscriptionMode.QUOTE),))
    assert changed.mode_change_entries[0].subscription.mode is ZerodhaSubscriptionMode.QUOTE
    rollover = planner.plan(proposed, (entry(3, expiry=date(2026, 8, 30)), entry(4, right=ZerodhaOptionRight.PUT, expiry=date(2026, 8, 30))))
    assert rollover.subscribe_entries and rollover.unsubscribe_entries


def test_planner_rejects_bad_groups_and_token_identity_collision():
    planner = ZerodhaOptionSubscriptionPlanner()
    with pytest.raises(ValueError):
        planner.plan((), ())
    with pytest.raises(ValueError):
        planner.plan((), (entry(1), entry(1, right=ZerodhaOptionRight.PUT)))
    with pytest.raises(ValueError):
        planner.plan((entry(1),), (entry(1, strike=25100),))
    with pytest.raises(ValueError):
        planner.plan((), (entry(1), entry(2, expiry=date(2026, 8, 30))))
