"""
Tests for the option-chain analytics dashboard panel.
"""

import ast
import os
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QAbstractItemView, QApplication, QLabel, QPushButton, QScrollArea, QTabWidget, QTableWidget

from application import ApplicationBootstrap
from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from dashboard.models import (
    DashboardOptionChainEventView,
    DashboardOptionChainStrikeView,
    DashboardOptionChainView,
    unavailable_option_chain_view,
)
from dashboard.panels.option_chain_panel import OptionChainPanel, STRIKE_COLUMNS, select_display_strikes
from dashboard.widgets import MetricCard
from dashboard.main_window import VisionMainWindow


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
    assert isinstance(panel._tabs, QTabWidget)
    assert [panel._tabs.tabText(index) for index in range(panel._tabs.count())] == ["Overview", "Diagnostics", "Chain"]
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


def test_summary_uses_readable_grouped_metric_rows_without_missing_labels_or_values():
    app()
    panel = OptionChainPanel()
    panel.render(view())
    overview = {
        "Status", "Available", "Underlying", "Expiry", "ATM Strike", "Last Update",
        "Positioning Bias", "OI PCR", "Change OI PCR", "ATM Strike",
        "Support", "Resistance", "Max Pain",
        "Call Pressure", "Put Pressure", "Total Call OI", "Total Put OI",
        "Max Call OI", "Max Put OI", "Max Call Change OI", "Max Put Change OI",
        "Total Call Change OI", "Total Put Change OI",
    }
    diagnostics = {
        "Message", "Enabled", "Configured", "Started", "Runtime State", "Last Error",
        "Current Spot", "Nearest Expiry", "Resolved ATM", "Contracts Resolved",
        "Contracts Active", "Contracts Total", "Last Underlying", "Spot Ticks",
        "Option Ticks", "Last Spot Tick", "Last Option Tick", "Analytics Updated",
        "Market Feed", "Spot Feed", "Discovery", "Subscription", "Option Feed",
        "Analytics", "Dashboard", "Symbol", "Exchange", "Timestamp", "Strike Count",
    }
    expected = overview | diagnostics
    assert set(panel._cards) == expected
    assert set(panel._labels) == expected
    title_text = {
        label.text()
        for card in panel._cards.values()
        for label in card.findChildren(QLabel)
        if label.property("role") == "metric-title"
    }
    assert expected.issubset(title_text)
    assert all(panel._labels[field].isVisibleTo(panel) or not panel.isVisible() for field in expected)
    assert all(panel._labels[field].text() != "" for field in expected)
    assert panel._labels["Underlying"].text() == "101.00"
    assert panel._labels["Call Pressure"].property("status") == "negative"
    assert panel._labels["Put Pressure"].property("status") == "positive"
    panel._tabs.setCurrentIndex(0)
    app().processEvents()
    assert panel._table.isVisibleTo(panel) is False
    panel._tabs.setCurrentIndex(1)
    app().processEvents()
    assert panel._runtime_table.isVisibleTo(panel)
    assert panel._event_table.isVisibleTo(panel)
    panel._tabs.setCurrentIndex(2)
    app().processEvents()
    assert panel._table.isVisibleTo(panel)


def test_summary_missing_values_render_placeholders_in_grouped_layout():
    app()
    panel = OptionChainPanel()
    panel.render(unavailable_option_chain_view("NIFTY"))
    for field in ("OI PCR", "Change OI PCR", "ATM Strike", "Support", "Resistance", "Max Pain", "Underlying", "Timestamp"):
        assert panel._labels[field].text() == "-"


@pytest.mark.parametrize("size", ((1320, 580), (1554, 712), (1874, 892)))
def test_summary_layout_is_responsive_without_overlapping_widgets(size):
    app()
    panel = OptionChainPanel()
    panel.render(view())
    panel.resize(*size)
    panel.show()
    app().processEvents()
    assert len(panel.findChildren(MetricCard)) == len(panel._cards)
    for tab_index in range(panel._tabs.count()):
        panel._tabs.setCurrentIndex(tab_index)
        app().processEvents()
        cards = [card for card in panel.findChildren(MetricCard) if card.isVisibleTo(panel)]
        for card in cards:
            assert card.geometry().width() > 120
            assert card.geometry().height() >= card.minimumHeight()
        geometries = [(card, card.geometry().translated(card.parentWidget().mapTo(panel, card.geometry().topLeft()) - card.geometry().topLeft())) for card in cards]
        for index, (left_card, left_rect) in enumerate(geometries):
            for right_card, right_rect in geometries[index + 1:]:
                if left_rect.intersects(right_rect):
                    intersection = left_rect.intersected(right_rect)
                    assert intersection.width() == 0 or intersection.height() == 0, (
                        left_card.findChild(QLabel).text(),
                        right_card.findChild(QLabel).text(),
                        intersection,
                    )
    panel._tabs.setCurrentIndex(2)
    app().processEvents()
    assert panel._table.isVisibleTo(panel)
    assert panel._table.height() >= panel._table.minimumHeight()


@pytest.mark.parametrize(
    ("pressure", "expected"),
    (
        ("Put Writing", "positive"),
        ("Call Unwinding", "positive"),
        ("Call Writing", "negative"),
        ("Put Unwinding", "negative"),
        ("Balanced", "neutral"),
        ("Unknown", "neutral"),
        ("-", "neutral"),
    ),
)
def test_pressure_badges_use_required_semantic_mapping(pressure, expected):
    app()
    panel = OptionChainPanel()
    panel.render(view(call_pressure=pressure, put_pressure=pressure))
    assert panel._labels["Call Pressure"].property("status") == expected
    assert panel._labels["Put Pressure"].property("status") == expected


@pytest.mark.parametrize(
    ("pressure", "expected"),
    (
        ("PUT_WRITING", "positive"),
        ("put-writing", "positive"),
        ("put writing", "positive"),
        ("call_unwinding", "positive"),
        ("CALL-UNWINDING", "positive"),
    ),
)
def test_pressure_badges_normalize_case_spaces_hyphens_and_underscores(pressure, expected):
    app()
    panel = OptionChainPanel()
    panel.render(view(call_pressure=pressure, put_pressure=pressure))
    assert panel._labels["Call Pressure"].property("status") == expected
    assert panel._labels["Put Pressure"].property("status") == expected


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


def test_repeated_render_does_not_duplicate_summary_widgets_and_table_remains_usable():
    app()
    panel = OptionChainPanel()
    card_count = len(panel.findChildren(MetricCard))
    first = view(rows=(strike(90), strike(100, is_atm=True), strike(110)))
    second = view(rows=(strike(100, is_atm=True), strike(110)), strike_count=2)
    panel.render(first)
    panel.render(second)
    assert len(panel.findChildren(MetricCard)) == card_count
    assert len(panel._cards) == card_count
    assert panel._table.rowCount() == 2
    assert panel._table.columnCount() == len(STRIKE_COLUMNS)
    assert panel._table.editTriggers() == QAbstractItemView.NoEditTriggers
    assert panel._table.selectionBehavior() == QAbstractItemView.SelectRows
    assert panel._runtime_table.rowCount() == 0
    assert panel._event_table.rowCount() == 0


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


def test_selected_option_chain_tab_survives_refresh_after_layout_repair():
    app()
    lifecycle = ApplicationBootstrap(
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.SENSEX, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.NIFTY)
        )
    ).create_application()
    window = VisionMainWindow(lifecycle)
    window.refresh()
    panels = window._instrument_panels["BANKNIFTY"]
    window._tabs.setCurrentWidget(panels["tab"])
    panels["sections"].setCurrentIndex(2)
    panels["option_chain"]._tabs.setCurrentIndex(1)
    window.refresh()
    assert window._tabs.tabText(window._tabs.currentIndex()) == "BANKNIFTY"
    assert panels["sections"].tabText(panels["sections"].currentIndex()) == "Option Chain"
    assert window._instrument_panels["BANKNIFTY"]["option_chain"] is panels["option_chain"]
    assert panels["option_chain"]._tabs.tabText(panels["option_chain"]._tabs.currentIndex()) == "Diagnostics"


def test_internal_tabs_are_scrollable_and_chain_empty_state_explains_stage():
    app()
    panel = OptionChainPanel()
    waiting = replace(
        unavailable_option_chain_view("NIFTY"),
        runtime_status="Waiting For Spot",
        runtime_message="Waiting for first NIFTY spot tick",
    )
    panel.render(waiting)
    assert isinstance(panel._tabs.widget(0), QScrollArea)
    assert isinstance(panel._tabs.widget(1), QScrollArea)
    assert panel._empty_chain.text() == "Waiting for first spot tick"


def test_long_diagnostic_error_and_events_remain_readable_without_extra_timers():
    app()
    panel = OptionChainPanel()
    long_error = "RuntimeError: " + "contract discovery delayed " * 18
    long_event = "09:15:04 " + "Analytics waiting for mapped option ticks " * 12
    panel.render(
        view(
            runtime_last_error=long_error,
            event_rows=(DashboardOptionChainEventView("09:15:04", "NIFTY", "Analytics Waiting", long_event),),
        )
    )
    panel._tabs.setCurrentIndex(1)
    panel.resize(1366, 768)
    panel.show()
    app().processEvents()
    assert panel._labels["Last Error"].text() == long_error
    assert panel._labels["Last Error"].height() >= panel._labels["Last Error"].minimumHeight()
    assert panel._event_table.item(0, 3).text() == long_event
    assert panel.findChildren(QTimer) == []
