"""
Tests for the live market-data Qt panel.
"""

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QAbstractItemView, QApplication, QPushButton

from dashboard.models import DashboardLiveMarketDataView, DashboardLiveSubscriptionView, unavailable_live_market_data_view
from dashboard.panels.live_market_data_panel import LiveMarketDataPanel


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


def app():
    return QApplication.instance() or QApplication([])


def view(rows=None, **overrides):
    rows = tuple(rows or (DashboardLiveSubscriptionView("NIFTY", "NSE", 101, "Full"),))
    values = dict(
        available=True,
        runtime_status="Running",
        ready=True,
        running=True,
        websocket_status="Connected",
        connected=True,
        configured_instruments=("NIFTY",),
        configured_tokens=(101,),
        subscription_count=len(rows),
        subscription_rows=rows,
        connection_count=1,
        disconnection_count=2,
        reconnect_count=3,
        raw_tick_count=4,
        normalized_tick_count=5,
        delivered_tick_count=6,
        rejected_tick_count=7,
        start_count=8,
        stop_count=9,
        last_connected_at=NOW,
        last_disconnected_at=NOW,
        last_tick_at=NOW,
        last_started_at=NOW,
        last_stopped_at=NOW,
        last_error=None,
    )
    values.update(overrides)
    return DashboardLiveMarketDataView(**values)


def test_panel_constructs_and_unavailable_view_renders_offline_message():
    app()
    panel = LiveMarketDataPanel()
    panel.render(unavailable_live_market_data_view())
    assert panel._offline_label.text() == "Live market data not configured"
    assert panel._offline_label.isHidden() is False


def test_running_view_renders_status_counters_and_timestamps():
    app()
    panel = LiveMarketDataPanel()
    panel.render(view())
    assert panel._offline_label.isHidden() is True
    assert panel._labels["Runtime Status"].text() == "Running"
    assert panel._labels["Connected"].text() == "Yes"
    assert panel._labels["Raw Ticks"].text() == "4"
    assert panel._labels["Delivered Ticks"].text() == "6"
    assert panel._labels["Rejected Ticks"].property("status") == "negative"
    assert panel._labels["Last Tick"].text().startswith("2026-07-12 09:15:00")


def test_subscriptions_render_in_order_and_table_is_read_only():
    app()
    panel = LiveMarketDataPanel()
    rows = (
        DashboardLiveSubscriptionView("NIFTY", "NSE", 101, "Full"),
        DashboardLiveSubscriptionView("SENSEX", "BSE", 202, "Quote"),
    )
    panel.render(view(rows=rows))
    assert panel._table.rowCount() == 2
    assert panel._table.item(0, 0).text() == "NIFTY"
    assert panel._table.item(1, 0).text() == "SENSEX"
    assert panel._table.editTriggers() == QAbstractItemView.NoEditTriggers


def test_repeated_render_updates_rows_and_missing_values_safely():
    app()
    panel = LiveMarketDataPanel()
    panel.render(view())
    panel.render(unavailable_live_market_data_view())
    assert panel._table.rowCount() == 0
    assert panel._labels["Last Tick"].text() == "-"


def test_no_buttons_or_backend_objects_are_accepted():
    app()
    panel = LiveMarketDataPanel()
    assert panel.findChildren(QPushButton) == []
    with pytest.raises(TypeError):
        panel.render(object())
