"""
Responsive dashboard layout and readability regression tests.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QScrollArea

from application import ApplicationBootstrap
from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from dashboard.main_window import VisionMainWindow
from dashboard.widgets import FieldGrid, MetricCard, StatusBadge


def app():
    return QApplication.instance() or QApplication([])


def three_instrument_window():
    lifecycle = ApplicationBootstrap(
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.SENSEX, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.NIFTY)
        )
    ).create_application()
    window = VisionMainWindow(lifecycle)
    window.refresh()
    return window


def analysis_tab_names(sections):
    return [sections.tabText(index) for index in range(sections.count())]


def process_layout(window, size):
    window.resize(*size)
    window.show()
    app().processEvents()


def test_main_window_contains_trading_and_system_areas():
    app()
    window = three_instrument_window()
    assert [window._main_tabs.tabText(index) for index in range(window._main_tabs.count())] == ["Trading", "System"]
    assert [window._system_tabs.tabText(index) for index in range(window._system_tabs.count())] == ["Runtime", "Live Feed"]
    assert window._tabs.count() == 3
    assert [window._tabs.tabText(index) for index in range(window._tabs.count())] == ["NIFTY", "BANKNIFTY", "SENSEX"]


def test_each_instrument_has_stable_analysis_tabs_and_scroll_wrappers():
    app()
    window = three_instrument_window()
    expected = ["Market", "Price Action", "Option Chain", "AI", "Strategy", "Position", "Journal"]
    for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
        sections = window._instrument_panels[symbol]["sections"]
        assert analysis_tab_names(sections) == expected
        for index, name in enumerate(expected):
            widget = sections.widget(index)
            if name == "Option Chain":
                assert not isinstance(widget, QScrollArea)
            else:
                assert isinstance(widget, QScrollArea)
                assert widget.widgetResizable() is True


def test_selected_instrument_and_analysis_tabs_survive_refresh_without_recreated_panels():
    app()
    window = three_instrument_window()
    selected = "BANKNIFTY"
    panels = dict(window._instrument_panels[selected])
    window._tabs.setCurrentWidget(panels["tab"])
    panels["sections"].setCurrentIndex(6)
    window.refresh()
    assert window._tabs.tabText(window._tabs.currentIndex()) == selected
    assert window._instrument_panels[selected]["sections"].tabText(panels["sections"].currentIndex()) == "Journal"
    for key in ("market", "price_action", "option_chain", "ai", "strategy", "position", "journal"):
        assert window._instrument_panels[selected][key] is panels[key]


@pytest.mark.parametrize("size", ((1366, 768), (1600, 900), (1920, 1080)))
def test_common_windows_sizes_keep_required_widgets_accessible(size):
    app()
    window = three_instrument_window()
    process_layout(window, size)
    assert window.size().width() >= min(size[0], window.minimumWidth())
    assert window._main_tabs.height() > 300
    assert window._tabs.height() > 260
    assert window._system_tabs.count() == 2
    assert window._runtime_panel.height() > 0
    assert window._live_market_data_panel.height() > 0
    assert window._timer.interval() == 500
    for symbol, panels in window._instrument_panels.items():
        sections = panels["sections"]
        assert sections.height() > 240
        assert sections.count() == 7
        assert panels["journal"]._labels["Trade ID"].minimumHeight() >= 24
        assert panels["journal"]._labels["Exit Type"].minimumHeight() >= 24
        assert panels["option_chain"]._table.minimumHeight() >= 240


def test_reusable_widgets_have_readable_minimum_sizes():
    app()
    grid = FieldGrid(("Trade ID", "Exit Type"))
    assert all(label.minimumHeight() >= 24 for label in grid.labels.values())
    assert all(label.minimumHeight() >= 24 for label in grid.name_labels.values())
    card = MetricCard("Runtime Status")
    assert card.minimumHeight() >= 72
    assert card.value_label.minimumHeight() >= 24
    badge = StatusBadge("Ready")
    assert badge.minimumHeight() >= 28
    assert badge.minimumSizeHint().height() >= 24


def test_runtime_live_feed_and_journal_labels_have_readable_minimum_height():
    app()
    window = three_instrument_window()
    runtime_labels = ("Instruments", "Market Data", "Journal", "Starts", "Stops", "Restarts", "Started At", "Stopped At", "Last Error")
    live_labels = ("Ready", "Running", "Connected", "Raw Ticks", "Delivered Ticks", "Last Tick", "Last Error")
    for label in runtime_labels:
        assert window._runtime_panel._labels[label].minimumHeight() >= 24
    for label in live_labels:
        assert window._live_market_data_panel._labels[label].minimumHeight() >= 24
    for label in ("Trade ID", "Exit Type", "Realized P&L", "Opened", "Closed"):
        assert window._instrument_panels["NIFTY"]["journal"]._labels[label].minimumHeight() >= 24


def test_scroll_areas_are_resizable_and_no_extra_timer_is_introduced():
    app()
    window = three_instrument_window()
    scroll_areas = window.findChildren(QScrollArea)
    assert scroll_areas
    assert all(area.widgetResizable() for area in scroll_areas)
    assert len(window.findChildren(type(window._timer))) == 1
    assert window.minimumSize().expandedTo(QSize(1100, 680)) == window.minimumSize()
