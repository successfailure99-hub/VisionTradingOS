"""
Tests for the market dashboard panel.
"""

import os
from datetime import UTC, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dashboard.models import DashboardMarketView
from dashboard.panels.market_panel import MarketPanel


def app():
    return QApplication.instance() or QApplication([])


def market_view(**overrides):
    values = dict(
        symbol="NIFTY", timeframe="1m", runtime_status="Running",
        last_price=None, bid_price=None, ask_price=None, session_high=None, session_low=None,
        latest_candle_open=None, latest_candle_high=None, latest_candle_low=None, latest_candle_close=None,
        vwap=None, vwap_source="-", vwap_source_type="-", vwap_source_exchange="-",
        vwap_source_expiry=None, vwap_source_volume=0, vwap_source_price=None,
        vwap_source_state="-", vwap_source_message="-", vwap_subscription_active=False,
        vwap_historical_candles_loaded=0, vwap_historical_volume=0, vwap_live_tick_count=0,
        vwap_historical_seed_complete=False, vwap_bootstrap_time=None,
        vwap_last_live_volume=0, vwap_last_delta_volume=0,
        vwap_last_live_tick=None, vwap_current_accumulated_volume=0, vwap_last_error=None,
        cpr_pivot=None, cpr_bc=None, cpr_tc=None,
        camarilla_h3=None, camarilla_h4=None, camarilla_h5=None, camarilla_h6=None,
        camarilla_l3=None, camarilla_l4=None, camarilla_l5=None, camarilla_l6=None,
        market_bias="-", market_phase="-", context_strength="-", option_chain_direction="-", updated_at=None,
    )
    values.update(overrides)
    return DashboardMarketView(**values)


def test_panel_constructs_in_offscreen_mode():
    app()
    assert MarketPanel().title() == "Market"


def test_render_empty_values_safely():
    panel = MarketPanel()
    panel.render(market_view())
    assert panel._labels["Last"].text() == "-"


def test_render_populated_market_values_and_price_formatting():
    panel = MarketPanel()
    panel.render(market_view(last_price=100.123, bid_price=99.5, ask_price=100.5))
    assert panel._labels["Last"].text() == "100.12"
    assert panel._labels["Bid"].text() == "99.50"
    assert panel._labels["Ask"].text() == "100.50"


def test_camarilla_cpr_and_market_bias_render():
    panel = MarketPanel()
    panel.render(market_view(vwap=100.5, vwap_source="NIFTY Spot", cpr_pivot=100.0, cpr_bc=99.0, cpr_tc=101.0, camarilla_h3=102.0, camarilla_l6=94.0, market_bias="Bullish"))
    assert panel._labels["VWAP Source"].text() == "NIFTY Spot"
    assert panel._labels["CPR Pivot"].text() == "100.00"
    assert panel._labels["CPR BC"].text() == "99.00"
    assert panel._labels["Cam H3"].text() == "102.00"
    assert panel._labels["Cam L6"].text() == "94.00"
    assert panel._labels["Bias"].text() == "Bullish"


def test_futures_vwap_source_metadata_renders():
    panel = MarketPanel()
    panel.render(
        market_view(
            vwap=25250.0,
            vwap_source="NIFTY26JULFUT",
            vwap_source_type="Futures",
            vwap_source_exchange="NFO",
            vwap_source_volume=1500,
            vwap_source_price=25255.5,
            vwap_source_state="Ready",
            vwap_source_message="Futures proxy VWAP ready",
            vwap_subscription_active=True,
            vwap_historical_candles_loaded=3,
            vwap_historical_volume=1475,
            vwap_historical_seed_complete=True,
            vwap_bootstrap_time=datetime(2026, 7, 15, 9, 20, tzinfo=UTC),
            vwap_live_tick_count=1,
            vwap_last_live_volume=1500,
            vwap_last_delta_volume=25,
            vwap_current_accumulated_volume=1500,
        )
    )
    assert panel._labels["VWAP"].text() == "25250.00"
    assert panel._labels["VWAP Source"].text() == "NIFTY26JULFUT"
    assert panel._labels["VWAP Type"].text() == "Futures"
    assert panel._labels["VWAP Venue"].text() == "NFO"
    assert panel._labels["VWAP Volume"].text() == "1500"
    assert panel._labels["VWAP Source Price"].text() == "25255.50"
    assert panel._labels["VWAP Status"].text() == "Ready"
    assert panel._labels["VWAP Message"].text() == "Futures proxy VWAP ready"
    assert panel._labels["VWAP Subscription"].text() == "Active"
    assert panel._labels["VWAP History Volume"].text() == "1475"
    assert panel._labels["Historical Seed Complete"].text() == "Yes"
    assert panel._labels["Bootstrap Time"].text() == "15-Jul-2026 14:50:00 IST"
    assert panel._labels["Live Tick Count"].text() == "1"
    assert panel._labels["Last Live Volume"].text() == "1500"
    assert panel._labels["Last Delta Volume"].text() == "25"
    assert panel._labels["Current Accumulated Volume"].text() == "1500"


def test_repeated_render_updates_existing_labels():
    panel = MarketPanel()
    label = panel._labels["Last"]
    panel.render(market_view(last_price=100.0))
    panel.render(market_view(last_price=101.0))
    assert panel._labels["Last"] is label
    assert label.text() == "101.00"
