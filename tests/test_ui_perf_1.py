"""
UI-PERF-1 dashboard rendering and navigation performance guards.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from application import ApplicationBootstrap
from dashboard.main_window import VisionMainWindow
from dashboard.widgets import MetricCard, StatusBadge
from engines.vision_method import validate_vision_method
from tests.test_vision_method_validation_v1 import snapshot


def app():
    return QApplication.instance() or QApplication([])


def test_unchanged_status_badge_and_metric_card_skip_repolish():
    app()
    badge = StatusBadge()
    card = MetricCard("Runtime")

    assert badge.set_status_text("READY", kind="positive") is True
    assert card.set_value("READY", kind="positive") is True
    badge_repolish = badge.repolish_count
    card_repolish = card.repolish_count

    assert badge.set_status_text("READY", kind="positive") is False
    assert card.set_value("READY", kind="positive") is False
    assert badge.repolish_count == badge_repolish
    assert card.repolish_count == card_repolish


def test_vision_inspector_reuses_trace_labels_for_identical_report():
    app()
    item = snapshot()
    report = validate_vision_method(item)
    window = VisionMainWindow(ApplicationBootstrap().create_application())
    panel = window._vision_method_inspector

    panel.render(item, report)
    labels = tuple(panel._trace_labels)
    counters = panel.render_counters()
    panel.render(item, report)

    assert tuple(panel._trace_labels) == labels
    assert panel.render_counters()["trace_rebuild_count"] == counters["trace_rebuild_count"]
    assert panel.render_counters()["field_skips_count"] > counters["field_skips_count"]


def test_hidden_vision_inspector_refresh_updates_data_without_visual_render(monkeypatch):
    app()
    window = VisionMainWindow(ApplicationBootstrap().create_application())
    calls = []

    def record_refresh(*, render_visual=True):
        calls.append(render_visual)

    monkeypatch.setattr(window._vision_method_bridge, "refresh", record_refresh)

    window.refresh()
    assert calls[-1] is False

    window._main_tabs.setCurrentWidget(window._vision_method_area)
    app().processEvents()
    window.refresh()
    assert calls[-1] is True


def test_rapid_tab_switch_coalesces_to_final_visible_panel(monkeypatch):
    app()
    window = VisionMainWindow(ApplicationBootstrap().create_application())
    window.refresh()
    panels = window._instrument_panels["NIFTY"]
    sections = panels["sections"]
    calls = {"ai": 0, "strategy": 0}

    monkeypatch.setattr(panels["ai"], "render", lambda _view: calls.__setitem__("ai", calls["ai"] + 1))
    monkeypatch.setattr(panels["strategy"], "render", lambda _view: calls.__setitem__("strategy", calls["strategy"] + 1))

    sections.setCurrentIndex(_section_index(sections, "AI"))
    sections.setCurrentIndex(_section_index(sections, "Strategy"))
    app().processEvents()

    assert calls == {"ai": 0, "strategy": 1}
    assert window.diagnostics()["last_tab_target"] == "Trading/NIFTY/Strategy"
    assert window.diagnostics()["last_widget_rebuilt"] is False


def test_visible_panel_render_preserves_scroll_position():
    app()
    window = VisionMainWindow(ApplicationBootstrap().create_application())
    view = window.refresh()
    panels = window._instrument_panels["NIFTY"]
    sections = panels["sections"]
    sections.setCurrentIndex(_section_index(sections, "AI"))
    app().processEvents()
    scroll = sections.currentWidget()
    scroll.verticalScrollBar().setValue(12)

    window._render_cached(("NIFTY", "AI"), view.ai[0], panels["ai"].render)

    assert scroll.verticalScrollBar().value() == min(12, scroll.verticalScrollBar().maximum())
    assert window.diagnostics()["scroll_restore_count"] >= 1


def _section_index(sections, name: str) -> int:
    return next(index for index in range(sections.count()) if sections.tabText(index) == name)
