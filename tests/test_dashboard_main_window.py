"""
Tests for the dashboard main window.
"""

import ast
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel

from application import ApplicationBootstrap
from application.enums import RuntimeInstrument
from application.lifecycle_manager import ApplicationLifecycleManager
from application.models import RuntimeConfiguration
from core.event_bus import EventBus
from dashboard.main_window import VisionMainWindow
from dashboard.panels.option_chain_panel import OptionChainPanel
from dashboard.panels.price_action_panel import PriceActionPanel


def app():
    return QApplication.instance() or QApplication([])


class CountingLifecycle(ApplicationLifecycleManager):
    def __init__(self):
        super().__init__(ApplicationBootstrap().create_application().orchestrator)
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return super().snapshot()


def test_constructor_validates_lifecycle_and_interval():
    app()
    with pytest.raises(TypeError):
        VisionMainWindow(object())
    with pytest.raises(ValueError):
        VisionMainWindow(ApplicationBootstrap().create_application(), refresh_interval_ms=0)


def test_window_title_timer_default_and_tabs_match_runtime_snapshots():
    lifecycle = ApplicationBootstrap().create_application()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    assert window.windowTitle() == "Vision Trading OS"
    assert window._timer.interval() == 500
    assert len(window.findChildren(QTimer)) == 1
    assert window._tabs.count() == len(view.markets)
    assert window.findChild(QLabel, "HeaderTitle").text() == "Vision Trading OS"
    assert window.styleSheet()


def test_refresh_calls_lifecycle_snapshot_once_and_stores_view():
    lifecycle = CountingLifecycle()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    assert lifecycle.calls == 1
    assert window.current_view() is view


def test_render_updates_all_panels():
    lifecycle = ApplicationBootstrap().create_application()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    symbol = view.markets[0].symbol
    assert symbol in window._instrument_panels
    assert window._instrument_panels[symbol]["market"]._labels["Symbol"].text() == symbol
    assert window._instrument_panels[symbol]["price_action"]._labels["Symbol"].text() == view.price_actions[0].symbol
    assert window._instrument_panels[symbol]["option_chain"]._labels["Symbol"].text() == view.option_chains[0].symbol
    assert window._instrument_panels[symbol]["ai"]._labels["Summary"].text() == view.ai[0].market_summary
    assert window._instrument_panels[symbol]["journal"]._analytics_panel._status.text() == view.analytics[0].status


def test_selected_tab_is_preserved_across_refreshes():
    lifecycle = ApplicationBootstrap(
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.SENSEX, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.NIFTY)
        )
    ).create_application()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    assert [window._tabs.tabText(index) for index in range(window._tabs.count())] == ["NIFTY", "BANKNIFTY", "SENSEX"]
    selected = "BANKNIFTY"
    window._tabs.setCurrentWidget(window._instrument_panels[selected]["tab"])
    window.refresh()
    assert window._tabs.tabText(window._tabs.currentIndex()) == selected


def test_instrument_section_tabs_match_price_action_milestone_order_and_preserve_selection():
    lifecycle = ApplicationBootstrap().create_application()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    symbol = view.markets[0].symbol
    sections = window._instrument_panels[symbol]["sections"]
    assert [sections.tabText(index) for index in range(sections.count())] == [
        "Market",
        "Price Action",
        "Option Chain",
        "AI",
        "Strategy",
        "Position",
        "Journal",
    ]
    sections.setCurrentIndex(1)
    window.refresh()
    assert window._instrument_panels[symbol]["sections"].tabText(sections.currentIndex()) == "Price Action"


def test_each_instrument_tab_has_one_option_chain_panel_and_tabs_are_reused():
    lifecycle = ApplicationBootstrap(
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.SENSEX, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.NIFTY)
        )
    ).create_application()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    tabs = {symbol: window._instrument_panels[symbol]["tab"] for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")}
    option_panels = {symbol: window._instrument_panels[symbol]["option_chain"] for symbol in tabs}
    price_action_panels = {symbol: window._instrument_panels[symbol]["price_action"] for symbol in tabs}
    assert tuple(chain.symbol for chain in view.option_chains) == ("NIFTY", "BANKNIFTY", "SENSEX")
    assert tuple(price_action.symbol for price_action in view.price_actions) == ("NIFTY", "BANKNIFTY", "SENSEX")
    for symbol in tabs:
        assert isinstance(option_panels[symbol], OptionChainPanel)
        assert isinstance(price_action_panels[symbol], PriceActionPanel)
        assert len(tabs[symbol].findChildren(OptionChainPanel)) == 1
        assert len(tabs[symbol].findChildren(PriceActionPanel)) == 1
    window.refresh()
    for symbol in tabs:
        assert window._instrument_panels[symbol]["tab"] is tabs[symbol]
        assert window._instrument_panels[symbol]["option_chain"] is option_panels[symbol]
        assert window._instrument_panels[symbol]["price_action"] is price_action_panels[symbol]


def test_start_stop_refresh_are_idempotent_and_close_stops_timer():
    lifecycle = ApplicationBootstrap().create_application()
    window = VisionMainWindow(lifecycle)
    window.start_refresh()
    assert window._timer.isActive()
    window.start_refresh()
    assert window._timer.isActive()
    window.stop_refresh()
    assert not window._timer.isActive()
    window.start_refresh()
    window.close()
    assert not window._timer.isActive()


def test_public_main_window_api_remains_available():
    public = {name for name in dir(VisionMainWindow) if not name.startswith("_")}
    assert {"start_refresh", "stop_refresh", "refresh", "render", "current_view"}.issubset(public)


def test_panel_code_does_not_call_engines_or_broker_methods():
    forbidden_calls = {"process_tick", "submit_order", "place", "login"}
    allowed_attribute_calls = {"connect"}
    called = set()
    for path in Path("dashboard").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr not in allowed_attribute_calls:
                        called.add(node.func.attr)
    assert called.isdisjoint(forbidden_calls)
