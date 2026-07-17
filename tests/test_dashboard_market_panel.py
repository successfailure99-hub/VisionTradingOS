"""
Tests for the market dashboard panel.
"""

import os

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
        vwap=None, vwap_source="-", cpr_pivot=None, cpr_bc=None, cpr_tc=None,
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


def test_repeated_render_updates_existing_labels():
    panel = MarketPanel()
    label = panel._labels["Last"]
    panel.render(market_view(last_price=100.0))
    panel.render(market_view(last_price=101.0))
    assert panel._labels["Last"] is label
    assert label.text() == "101.00"
