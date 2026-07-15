"""
Tests for dashboard option-chain presentation models.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from dashboard.models import DashboardOptionChainStrikeView, DashboardOptionChainView, unavailable_option_chain_view


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def strike(price=100.0, **overrides):
    values = dict(
        strike_price=price,
        is_atm=False,
        call_last_price=10.0,
        call_open_interest=100,
        call_change_open_interest=-5,
        call_volume=20,
        call_bid_price=9.5,
        call_ask_price=10.5,
        put_last_price=8.0,
        put_open_interest=120,
        put_change_open_interest=7,
        put_volume=30,
        put_bid_price=7.5,
        put_ask_price=8.5,
    )
    values.update(overrides)
    return DashboardOptionChainStrikeView(**values)


def view(**overrides):
    rows = overrides.pop("strikes", (strike(100.0, is_atm=True), strike(90.0)))
    values = dict(
        symbol="NIFTY",
        available=True,
        exchange="NSE",
        expiry_date=date(2026, 7, 30),
        timestamp=NOW,
        underlying_price=100.0,
        atm_strike=100.0,
        strike_count=len(rows),
        total_call_oi=100,
        total_put_oi=120,
        total_call_change_oi=-5,
        total_put_change_oi=7,
        oi_pcr=1.2,
        change_oi_pcr=None,
        max_call_oi_strike=100.0,
        max_call_oi_value=100,
        max_put_oi_strike=90.0,
        max_put_oi_value=120,
        max_call_change_oi_strike=100.0,
        max_call_change_oi_value=5,
        max_put_change_oi_strike=90.0,
        max_put_change_oi_value=7,
        resistance_strike=100.0,
        support_strike=90.0,
        max_pain_strike=95.0,
        call_pressure="Call Writing",
        put_pressure="Put Writing",
        positioning_bias="Bullish",
        strikes=rows,
    )
    values.update(overrides)
    return DashboardOptionChainView(**values)


def test_option_chain_view_models_are_frozen_and_use_immutable_sorted_tuples():
    rows = [strike(110.0), strike(90.0), strike(100.0, is_atm=True)]
    result = view(strikes=rows, strike_count=3)
    assert isinstance(result.strikes, tuple)
    assert tuple(row.strike_price for row in result.strikes) == (90.0, 100.0, 110.0)
    with pytest.raises(FrozenInstanceError):
        result.symbol = "BANKNIFTY"
    with pytest.raises(FrozenInstanceError):
        result.strikes[0].strike_price = 95.0


def test_timestamp_counts_and_strike_rows_are_validated():
    with pytest.raises(ValueError):
        view(timestamp=datetime(2026, 7, 12, 9, 15))
    with pytest.raises(ValueError):
        view(strike_count=-1)
    with pytest.raises(ValueError):
        view(total_call_oi=-1)
    with pytest.raises(ValueError):
        view(strikes=(strike(),), strike_count=2)
    with pytest.raises(TypeError):
        view(strikes=(object(),), strike_count=1)


def test_strike_view_validates_non_negative_oi_counts_but_allows_signed_change_oi():
    row = strike(call_change_open_interest=-10, put_change_open_interest=-20)
    assert row.call_change_open_interest == -10
    with pytest.raises(ValueError):
        strike(call_open_interest=-1)
    with pytest.raises(ValueError):
        strike(put_volume=-1)


def test_unavailable_view_is_valid_deterministic_and_missing_legs_are_supported():
    unavailable = unavailable_option_chain_view("NIFTY")
    assert unavailable.available is False
    assert unavailable.symbol == "NIFTY"
    assert unavailable.strikes == ()
    assert unavailable.timestamp is None
    missing_call = strike(call_last_price=None, call_open_interest=None, call_change_open_interest=None, call_volume=None, call_bid_price=None, call_ask_price=None)
    missing_put = strike(put_last_price=None, put_open_interest=None, put_change_open_interest=None, put_volume=None, put_bid_price=None, put_ask_price=None)
    result = view(strikes=(missing_call, missing_put), strike_count=2)
    assert result.strikes[0].call_last_price is None
    assert result.strikes[1].put_last_price is None
