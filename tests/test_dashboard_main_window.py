"""
Tests for the dashboard main window.
"""

import ast
import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel

from application import ApplicationBootstrap
from application.enums import RuntimeInstrument
from application.lifecycle_manager import ApplicationLifecycleManager
from application.models import RuntimeConfiguration
from application.runtime_supervisor import RuntimeSupervisorCheck, RuntimeSupervisorSnapshot
from core.event_bus import EventBus
from dashboard.main_window import VisionMainWindow
from dashboard.models import DashboardRuntimeComponentHealthView, DashboardRuntimeHealthSummary
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


def test_header_runtime_health_uses_canonical_runtime_view_not_stale_supervisor_aggregate():
    lifecycle = ApplicationBootstrap().bootstrap()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    window._runtime_supervisor._last_snapshot = RuntimeSupervisorSnapshot(
        "FAILED",
        window._runtime_supervisor.interval_ms,
        (
            RuntimeSupervisorCheck(
                "RuntimeSnapshot",
                "SymbolRuntime",
                "SymbolRuntime.snapshot",
                "Dashboard",
                "FAILED",
                "stale supervisor aggregate",
            ),
        ),
    )
    canonical = replace(
        view,
        runtime=replace(
            view.runtime,
            application_status="Running",
            primary_blocker="-",
            component_health=(
                DashboardRuntimeComponentHealthView(
                    "Runtime Contract",
                    "READY",
                    "Runtime contract valid.",
                    owner="SymbolRuntime",
                    producer="RuntimeContractValidator",
                    consumer="Dashboard",
                ),
            ),
            runtime_health_summary=DashboardRuntimeHealthSummary(
                "READY",
                tooltip="Component: Runtime\nStatus: READY\nReason: None\nUpdated: -\nBlocking: No",
            ),
        ),
    )

    window.render(canonical)

    assert window._health_badges["Runtime"].text() == "Runtime: READY"
    assert "Component: Runtime" in window._health_badges["Runtime"].toolTip()


def test_header_runtime_health_reports_failed_only_when_canonical_runtime_row_fails():
    lifecycle = ApplicationBootstrap().bootstrap()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    canonical_failure = replace(
        view,
        runtime=replace(
            view.runtime,
            application_status="Running",
            primary_blocker="-",
            component_health=(
                DashboardRuntimeComponentHealthView(
                    "Runtime Contract",
                    "FAILED",
                    "Runtime contract failed.",
                    owner="SymbolRuntime",
                    producer="RuntimeContractValidator",
                    consumer="Dashboard",
                ),
            ),
            runtime_health_summary=DashboardRuntimeHealthSummary(
                "FAILED",
                primary_failure="Runtime Contract",
                failure_reason="Runtime contract failed.",
                blocking=True,
                failed_component_count=1,
                tooltip="Component: Runtime Contract\nStatus: FAILED\nReason: Runtime contract failed.\nUpdated: -\nBlocking: Yes",
            ),
        ),
    )

    window.render(canonical_failure)

    assert window._health_badges["Runtime"].text() == "Runtime: FAILED"
    assert "Component: Runtime Contract" in window._health_badges["Runtime"].toolTip()
    assert "Reason: Runtime contract failed." in window._health_badges["Runtime"].toolTip()


def test_header_runtime_health_recovers_with_current_dashboard_view_generation():
    lifecycle = ApplicationBootstrap().bootstrap()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    failed = replace(
        view,
        runtime=replace(
            view.runtime,
            component_health=(DashboardRuntimeComponentHealthView("Option Chain", "FAILED", "Snapshot stale."),),
            runtime_health_summary=DashboardRuntimeHealthSummary(
                "FAILED",
                primary_failure="Option Chain",
                failure_reason="Snapshot stale.",
                blocking=True,
                failed_component_count=1,
                tooltip="Component: Option Chain\nStatus: FAILED\nReason: Snapshot stale.\nUpdated: -\nBlocking: Yes",
            ),
        ),
    )
    recovered = replace(
        view,
        runtime=replace(
            view.runtime,
            component_health=(DashboardRuntimeComponentHealthView("Option Chain", "READY", "Synchronized."),),
            runtime_health_summary=DashboardRuntimeHealthSummary(
                "READY",
                tooltip="Component: Runtime\nStatus: READY\nReason: None\nUpdated: -\nBlocking: No",
            ),
        ),
    )

    window.render(failed)
    assert window._health_badges["Runtime"].text() == "Runtime: FAILED"

    window.render(recovered)

    assert window._health_badges["Runtime"].text() == "Runtime: READY"
    assert "Snapshot stale" not in window._health_badges["Runtime"].toolTip()
    assert window.current_view() is recovered


def test_header_operational_badges_have_named_component_tooltips():
    lifecycle = ApplicationBootstrap().bootstrap()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()

    window.render(view)

    for name, badge in window._health_badges.items():
        tooltip = badge.toolTip()
        assert "Component:" in tooltip, name
        assert "Status:" in tooltip, name
        assert "Reason:" in tooltip, name


def test_refresh_calls_lifecycle_snapshot_once_and_stores_view():
    lifecycle = CountingLifecycle()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    assert lifecycle.calls == 1
    assert window.current_view() is view


def test_first_render_initializes_visible_panel_and_defers_hidden_panels():
    lifecycle = ApplicationBootstrap().create_application()
    window = VisionMainWindow(lifecycle)
    view = window.refresh()
    symbol = view.markets[0].symbol
    assert symbol in window._instrument_panels
    assert window._instrument_panels[symbol]["market"]._labels["Symbol"].text() == symbol
    assert (symbol, "Market") in window._panel_render_cache
    assert (symbol, "Price Action") not in window._panel_render_cache
    assert (symbol, "Option Chain") not in window._panel_render_cache
    assert (symbol, "AI") not in window._panel_render_cache
    assert (symbol, "Journal") not in window._panel_render_cache
    assert window.current_view() is view
    assert window.diagnostics()["active_panel_render_ms"] >= 0.0


def test_cached_tab_change_renders_without_runtime_snapshot_supervisor_or_bridge_work(monkeypatch):
    lifecycle = ApplicationBootstrap().create_application()
    window = VisionMainWindow(lifecycle)
    window.refresh()
    calls = {"snapshot": 0, "bridge": 0, "supervisor": 0, "market": 0}
    original_snapshot = lifecycle.snapshot
    original_market = window._instrument_panels["NIFTY"]["price_action"].render

    def count_snapshot():
        calls["snapshot"] += 1
        return original_snapshot()

    def count_market(view):
        calls["market"] += 1
        return original_market(view)

    monkeypatch.setattr(lifecycle, "snapshot", count_snapshot)
    monkeypatch.setattr(window._vision_method_bridge, "refresh", lambda: calls.__setitem__("bridge", calls["bridge"] + 1))
    monkeypatch.setattr(window._runtime_supervisor, "monitor", lambda _snapshot: calls.__setitem__("supervisor", calls["supervisor"] + 1))
    monkeypatch.setattr(window._instrument_panels["NIFTY"]["price_action"], "render", count_market)

    window._instrument_panels["NIFTY"]["sections"].setCurrentIndex(1)

    assert calls == {"snapshot": 0, "bridge": 0, "supervisor": 0, "market": 1}
    assert window.diagnostics()["tab_change_ms"] >= 0.0
    assert window.diagnostics()["tab_change_p95_ms"] >= 0.0
    assert window.diagnostics()["ui_responsiveness"] in {"HEALTHY", "NOTICE", "SLOW", "UI_STALL"}


def test_changed_refresh_renders_visible_panel_only(monkeypatch):
    lifecycle = ApplicationBootstrap(
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.SENSEX, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.NIFTY)
        )
    ).create_application()
    window = VisionMainWindow(lifecycle)
    first = window.refresh()
    window._tabs.setCurrentWidget(window._instrument_panels["NIFTY"]["tab"])
    window._instrument_panels["NIFTY"]["sections"].setCurrentIndex(0)
    calls = {"market": 0, "price_action": 0, "banknifty_market": 0}

    def count_market(view):
        calls["market"] += 1

    def count_price_action(view):
        calls["price_action"] += 1

    def count_banknifty_market(view):
        calls["banknifty_market"] += 1

    monkeypatch.setattr(window._instrument_panels["NIFTY"]["market"], "render", count_market)
    monkeypatch.setattr(window._instrument_panels["NIFTY"]["price_action"], "render", count_price_action)
    monkeypatch.setattr(window._instrument_panels["BANKNIFTY"]["market"], "render", count_banknifty_market)

    changed = replace(
        first,
        runtime=replace(first.runtime, last_error="connection was closed uncleanly"),
        markets=(replace(first.markets[0], last_price=25001.0), *first.markets[1:]),
    )
    window.render(changed)

    assert calls == {"market": 1, "price_action": 0, "banknifty_market": 0}


def test_hidden_panel_activation_uses_latest_prepared_view_without_refresh(monkeypatch):
    lifecycle = ApplicationBootstrap().create_application()
    window = VisionMainWindow(lifecycle)
    first = window.refresh()
    changed_option = replace(first.option_chains[0], runtime_status="Receiving", runtime_message="Live option chain synchronized")
    changed = replace(first, option_chains=(changed_option, *first.option_chains[1:]))
    calls = {"snapshot": 0}

    monkeypatch.setattr(lifecycle, "snapshot", lambda: calls.__setitem__("snapshot", calls["snapshot"] + 1))
    window.render(changed)

    sections = window._instrument_panels[first.markets[0].symbol]["sections"]
    sections.setCurrentIndex(2)

    option_panel = window._instrument_panels[first.markets[0].symbol]["option_chain"]
    assert calls["snapshot"] == 0
    assert option_panel._labels["Status"].text() == "Receiving"
    assert option_panel._labels["Message"].text() == "Live option chain synchronized"


def test_repeated_tab_switches_reuse_prepared_view_and_keep_ui_responsive(monkeypatch):
    lifecycle = ApplicationBootstrap().create_application()
    window = VisionMainWindow(lifecycle)
    window.refresh()
    calls = {"snapshot": 0}

    monkeypatch.setattr(lifecycle, "snapshot", lambda: calls.__setitem__("snapshot", calls["snapshot"] + 1))
    sections = window._instrument_panels["NIFTY"]["sections"]
    for index in range(140):
        sections.setCurrentIndex(index % sections.count())

    diagnostics = window.diagnostics()
    assert calls["snapshot"] == 0
    assert diagnostics["tab_change_p95_ms"] < 50.0
    assert len(window.findChildren(QTimer)) == 1


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
    assert {"start_refresh", "stop_refresh", "refresh", "render", "current_view", "render_vision_method"}.issubset(public)


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
