"""
Tests for the option-chain analytics dashboard panel.
"""

import ast
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication, QPushButton

from dashboard.models import DashboardOptionChainStrikeView, DashboardOptionChainView, unavailable_option_chain_view
from dashboard.panels.option_chain_panel import OptionChainPanel, STRIKE_COLUMNS, select_display_strikes


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def app():
    return QApplication.instance() or QApplication([])


def strike(price, *, is_atm=False, call_change=1, put_change=-1, call_oi=100, put_oi=120):
    return DashboardOptionChainStrikeView(
        strike_price=float(price),
        is_atm=is_atm,
        call_last_price=10.0,
        call_open_interest=call_oi,
        call_change_open_interest=call_change,
        call_volume=0,
        call_bid_price=9.5,
        call_ask_price=10.5,
        put_last_price=8.0,
        put_open_interest=put_oi,
        put_change_open_interest=put_change,
        put_volume=0,
        put_bid_price=7.5,
        put_ask_price=8.5,
    )


def view(rows=None, **overrides):
    rows = tuple(rows or (strike(90), strike(100, is_atm=True), strike(110)))
    values = dict(
        symbol="NIFTY",
        available=True,
        exchange="NSE",
        expiry_date=date(2026, 7, 30),
        timestamp=NOW,
        underlying_price=101.0,
        atm_strike=100.0,
        strike_count=len(rows),
        total_call_oi=1000,
        total_put_oi=1200,
        total_call_change_oi=10,
        total_put_change_oi=-5,
        oi_pcr=1.2,
        change_oi_pcr=0.5,
        max_call_oi_strike=110.0,
        max_call_oi_value=500,
        max_put_oi_strike=90.0,
        max_put_oi_value=600,
        max_call_change_oi_strike=110.0,
        max_call_change_oi_value=50,
        max_put_change_oi_strike=90.0,
        max_put_change_oi_value=60,
        resistance_strike=110.0,
        support_strike=90.0,
        max_pain_strike=100.0,
        call_pressure="Call Writing",
        put_pressure="Put Writing",
        positioning_bias="Bullish",
        strikes=rows,
    )
    values.update(overrides)
    return DashboardOptionChainView(**values)


def test_strike_window_selects_atm_wings_and_handles_fewer_irregular_rows():
    prices = (41, 49, 58, 70, 83, 91, 100, 112, 127, 145)
    result = select_display_strikes(view(rows=tuple(strike(price, is_atm=price == 100) for price in prices)))
    assert tuple(row.strike_price for row in result) == tuple(float(price) for price in prices)


def test_strike_window_includes_special_rows_outside_normal_window_once_and_sorted():
    prices = tuple(float(index) for index in range(1, 31))
    rows = tuple(strike(price, is_atm=price == 15.0) for price in prices)
    result = select_display_strikes(
        view(
            rows=rows,
            atm_strike=15.0,
            support_strike=1.0,
            resistance_strike=30.0,
            max_pain_strike=2.0,
            max_call_oi_strike=29.0,
            max_put_oi_strike=3.0,
            max_call_change_oi_strike=28.0,
            max_put_change_oi_strike=4.0,
        )
    )
    selected = tuple(row.strike_price for row in result)
    assert selected == tuple(sorted(set(selected)))
    for special in (1.0, 2.0, 3.0, 4.0, 28.0, 29.0, 30.0):
        assert special in selected
    assert all(price in selected for price in range(5, 26))


def test_panel_constructs_rejects_bad_view_and_unavailable_state_renders_cleanly():
    app()
    panel = OptionChainPanel()
    assert panel.title() == "Option Chain Analytics"
    with pytest.raises(TypeError):
        panel.render(object())
    panel.render(unavailable_option_chain_view("NIFTY"))
    assert panel._labels["Available"].text() == "No"
    assert panel._labels["Symbol"].text() == "NIFTY"
    assert panel._labels["Underlying"].text() == "-"
    assert panel._table.rowCount() == 0


def test_complete_view_renders_headline_analytics_and_deterministic_columns():
    app()
    panel = OptionChainPanel()
    panel.render(view())
    assert panel._labels["Available"].text() == "Yes"
    assert panel._labels["Exchange"].text() == "NSE"
    assert panel._labels["Expiry"].text() == "2026-07-30"
    assert panel._labels["Timestamp"].text().startswith("2026-07-12 09:15:00")
    assert panel._labels["Underlying"].text() == "101.00"
    assert panel._labels["Support"].text() == "90.00"
    assert panel._labels["Resistance"].text() == "110.00"
    assert panel._labels["Max Pain"].text() == "100.00"
    assert panel._labels["Max Call OI"].text() == "110.00 / 500"
    assert panel._labels["Total Put Change OI"].text() == "-5"
    assert panel._labels["Positioning Bias"].text() == "Bullish"
    assert panel._labels["Positioning Bias"].property("status") == "positive"
    assert [panel._table.horizontalHeaderItem(index).text() for index in range(panel._table.columnCount())] == list(STRIKE_COLUMNS)


def test_table_cells_are_read_only_repeated_render_replaces_rows_and_values_are_safe():
    app()
    panel = OptionChainPanel()
    first = view(rows=(strike(90), strike(100, is_atm=True), strike(110)))
    second_rows = (
        strike(100, is_atm=True, call_change=0, put_change=0, call_oi=0, put_oi=0),
        DashboardOptionChainStrikeView(110.0, False, None, None, None, None, None, None, 8.0, 120, -1, 0, 7.5, 8.5),
    )
    panel.render(first)
    panel.render(view(rows=second_rows, strike_count=2, support_strike=None, resistance_strike=None, max_pain_strike=None))
    assert panel._table.rowCount() == 2
    assert panel._table.editTriggers() == QAbstractItemView.NoEditTriggers
    assert panel._table.contextMenuPolicy() == Qt.NoContextMenu
    assert panel._table.item(0, 0).flags() & Qt.ItemIsEditable == Qt.NoItemFlags
    assert panel._table.item(0, 3).text() == "0"
    assert panel._table.item(0, 4).text() == "0"
    assert panel._table.item(1, 0).text() == "-"


def test_row_and_change_oi_styling_markers_are_applied():
    app()
    rows = (
        strike(90, put_change=-10),
        strike(100, is_atm=True, call_change=10, put_change=-10),
        strike(110, call_change=10),
    )
    panel = OptionChainPanel()
    panel.render(view(rows=rows, support_strike=90.0, resistance_strike=110.0, max_pain_strike=100.0))
    tags = [panel._table.item(row, 6).data(Qt.UserRole) for row in range(panel._table.rowCount())]
    assert "support" in tags[0]
    assert "atm" in tags[1]
    assert "max-pain" in tags[1]
    assert "resistance" in tags[2]
    assert panel._table.item(1, 4).data(Qt.UserRole + 1) == "positive"
    assert panel._table.item(1, 8).data(Qt.UserRole + 1) == "negative"


def test_panel_has_no_buttons_fetching_or_analytics_calculation_calls():
    app()
    panel = OptionChainPanel()
    assert panel.findChildren(QPushButton) == []
    tree = ast.parse(Path("dashboard/panels/option_chain_panel.py").read_text(encoding="utf-8"))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and (isinstance(node.func, ast.Attribute) or isinstance(node.func, ast.Name))
    }
    assert called.isdisjoint({"process", "process_snapshot", "calculate", "classify", "fetch", "request", "login", "place_order"})
