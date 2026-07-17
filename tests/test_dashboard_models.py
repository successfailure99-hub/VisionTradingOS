"""
Tests for dashboard presentation models.
"""

from dataclasses import FrozenInstanceError, fields

import pytest

from dashboard.models import (
    DashboardAIView,
    DashboardJournalView,
    DashboardMarketView,
    DashboardPositionView,
    DashboardPriceActionView,
    DashboardRuntimeView,
    DashboardStrategyView,
    DashboardView,
)


def test_presentation_models_are_frozen():
    view = DashboardRuntimeView("Created", "Dry Run", "Analysis Only", ("NIFTY",), False, False, 0, 0, 0, None, None, None)
    with pytest.raises(FrozenInstanceError):
        view.application_status = "Running"
    price_action = DashboardPriceActionView("NIFTY", False, "-", "-", None, None, None, None, None, None, "-", "-", "-", "-", "-", None)
    with pytest.raises(FrozenInstanceError):
        price_action.trend = "Bullish"


def test_models_accept_optional_values_and_tuples_are_immutable():
    runtime = DashboardRuntimeView("Created", "Dry Run", "Analysis Only", ("NIFTY",), False, False, 0, 0, 0, None, None, None)
    market = DashboardMarketView(
        symbol="NIFTY",
        timeframe="1m",
        runtime_status="Created",
        last_price=None,
        bid_price=None,
        ask_price=None,
        session_high=None,
        session_low=None,
        latest_candle_open=None,
        latest_candle_high=None,
        latest_candle_low=None,
        latest_candle_close=None,
        vwap=None,
        vwap_source="-",
        vwap_source_type="-",
        vwap_source_exchange="-",
        vwap_source_expiry=None,
        vwap_source_volume=0,
        vwap_source_price=None,
        vwap_source_state="-",
        vwap_source_message="-",
        vwap_subscription_active=False,
        vwap_historical_candles_loaded=0,
        vwap_historical_volume=0,
        vwap_live_tick_count=0,
        vwap_last_live_tick=None,
        vwap_last_error=None,
        cpr_pivot=None,
        cpr_bc=None,
        cpr_tc=None,
        camarilla_h3=None,
        camarilla_h4=None,
        camarilla_h5=None,
        camarilla_h6=None,
        camarilla_l3=None,
        camarilla_l4=None,
        camarilla_l5=None,
        camarilla_l6=None,
        market_bias="-",
        market_phase="-",
        context_strength="-",
        option_chain_direction="-",
        updated_at=None,
    )
    price_action = DashboardPriceActionView("NIFTY", False, "-", "-", None, None, None, None, None, None, "-", "-", "-", "-", "-", None)
    ai = DashboardAIView("NIFTY", "-", "-", "-", "-", "-", "-", ())
    strategy = DashboardStrategyView("NIFTY", "-", "-", "-", "-", "-", "-", "-", "-", None, None, None, "-")
    position = DashboardPositionView("NIFTY", "No Active Position", False, "-", None, None, None, None, None, None, None)
    journal = DashboardJournalView("NIFTY", "Ready", 0, "No completed DRY_RUN trades", None, "-", None, None, None)
    dashboard = DashboardView(runtime, (market,), (ai,), (strategy,), (position,), (journal,), (price_action,))
    assert dashboard.markets == (market,)
    assert dashboard.price_actions == (price_action,)
    assert isinstance(dashboard.markets, tuple)


def test_models_do_not_contain_engine_objects():
    runtime = DashboardRuntimeView("Created", "Dry Run", "Analysis Only", ("NIFTY",), False, False, 0, 0, 0, None, None, None)
    values = tuple(getattr(runtime, field.name) for field in fields(runtime))
    assert all("Engine" not in type(value).__name__ for value in values)
