"""
Tests for the price-action dashboard panel.
"""

import ast
import os
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from dashboard.models import DashboardPriceActionView, unavailable_price_action_view
from dashboard.panels.price_action_panel import PriceActionPanel


NOW = datetime(2026, 7, 12, 9, 15)


def app():
    return QApplication.instance() or QApplication([])


def view(**overrides):
    values = dict(
        symbol="NIFTY",
        available=True,
        trend="Bullish",
        market_structure="Bullish",
        latest_hh=111.0,
        latest_hl=101.0,
        latest_lh=109.0,
        latest_ll=99.0,
        swing_high=111.0,
        swing_low=101.0,
        bos_direction="Bullish",
        choch_direction="Bearish",
        pullback_state="Bullish Pullback",
        range_state="Not Range",
        liquidity_sweep="Buy Side",
        updated_at=NOW,
    )
    values.update(overrides)
    return DashboardPriceActionView(**values)


def test_panel_constructs_rejects_bad_view_and_unavailable_state_renders_cleanly():
    app()
    panel = PriceActionPanel()
    assert panel.title() == "Price Action"
    with pytest.raises(TypeError):
        panel.render(object())
    panel.render(unavailable_price_action_view("NIFTY"))
    assert panel._labels["Available"].text() == "No"
    assert panel._labels["Symbol"].text() == "NIFTY"
    assert panel._labels["Trend"].text() == "-"
    assert panel._labels["Higher High"].text() == "-"
    assert panel._labels["Updated Time"].text() == "-"


def test_complete_state_renders_all_price_action_evidence():
    app()
    panel = PriceActionPanel()
    panel.render(view())
    assert panel._labels["Available"].text() == "Yes"
    assert panel._labels["Trend"].text() == "Bullish"
    assert panel._labels["Structure"].text() == "Bullish"
    assert panel._labels["Higher High"].text() == "111.00"
    assert panel._labels["Higher Low"].text() == "101.00"
    assert panel._labels["Lower High"].text() == "109.00"
    assert panel._labels["Lower Low"].text() == "99.00"
    assert panel._labels["Swing High"].text() == "111.00"
    assert panel._labels["Swing Low"].text() == "101.00"
    assert panel._labels["BOS"].text() == "Bullish"
    assert panel._labels["CHoCH"].text() == "Bearish"
    assert panel._labels["Pullback"].text() == "Bullish Pullback"
    assert panel._labels["Range"].text() == "Not Range"
    assert panel._labels["Liquidity Sweep"].text() == "Buy Side"
    assert panel._labels["Updated Time"].text() == "2026-07-12 09:15:00"


def test_status_properties_use_existing_semantic_colors():
    app()
    panel = PriceActionPanel()
    panel.render(view(trend="Bearish", bos_direction="Bearish", range_state="Range", liquidity_sweep="None"))
    assert panel._labels["Trend"].property("status") == "negative"
    assert panel._labels["BOS"].property("status") == "negative"
    assert panel._labels["Range"].property("status") == "neutral"
    assert panel._labels["Liquidity Sweep"].property("status") == "neutral"


def test_repeated_render_updates_existing_labels_without_recreating_children():
    app()
    panel = PriceActionPanel()
    labels = dict(panel._labels)
    panel.render(view())
    panel.render(view(trend="Range", latest_hh=None, bos_direction="None", liquidity_sweep="Sell Side"))
    assert panel._labels == labels
    assert panel._labels["Trend"].text() == "Range"
    assert panel._labels["Higher High"].text() == "-"
    assert panel._labels["BOS"].text() == "None"
    assert panel._labels["Liquidity Sweep"].text() == "Sell Side"


def test_panel_is_read_only_and_has_no_backend_or_engine_calls():
    app()
    panel = PriceActionPanel()
    assert panel.findChildren(QPushButton) == []
    tree = ast.parse(Path("dashboard/panels/price_action_panel.py").read_text(encoding="utf-8"))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and (isinstance(node.func, ast.Attribute) or isinstance(node.func, ast.Name))
    }
    assert called.isdisjoint({"process", "calculate", "classify", "fetch", "request", "login", "place_order"})
