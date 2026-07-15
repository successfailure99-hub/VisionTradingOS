"""
Tests for the dashboard main window.
"""

import ast
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from application import ApplicationBootstrap
from application.enums import RuntimeInstrument
from application.lifecycle_manager import ApplicationLifecycleManager
from application.models import RuntimeConfiguration
from core.event_bus import EventBus
from dashboard.main_window import VisionMainWindow


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
