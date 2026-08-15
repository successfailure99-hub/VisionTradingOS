"""
UI-PERF-1 dashboard rendering and navigation performance guards.
"""

import os
from dataclasses import replace
from datetime import timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from application import ApplicationBootstrap
from application.enums import RuntimeInstrument
from dashboard.main_window import VisionMainWindow
from dashboard.widgets import MetricCard, StatusBadge
from engines.vision_method import validate_vision_method
from tests.test_vision_method_inspector_v1 import _live_lifecycle
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
    lifecycle, runtime = _live_lifecycle()
    item = snapshot()
    report = validate_vision_method(item)
    runtime.current_snapshot = replace(
        runtime.current_snapshot,
        vision_method_snapshot=item,
        vision_method_validation_report=report,
    )
    window = VisionMainWindow(lifecycle)
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    calls = {"assemble": 0, "calculate": 0, "validate": 0, "render": 0}

    from desktop.vision_method import live_integration

    def forbidden(name):
        def _raise(*_args, **_kwargs):
            calls[name] += 1
            raise AssertionError(f"{name} must not run during dashboard capture")

        return _raise

    monkeypatch.setattr(live_integration, "assemble_vision_method_runtime", forbidden("assemble"))
    monkeypatch.setattr(live_integration, "calculate_vision_method_snapshot", forbidden("calculate"))
    monkeypatch.setattr(live_integration, "validate_vision_method", forbidden("validate"))
    monkeypatch.setattr(window._vision_method_inspector, "render_live_status", lambda *_args, **_kwargs: calls.__setitem__("render", calls["render"] + 1))

    window.refresh()
    assert window._vision_method_bridge.last_report is report
    assert calls == {"assemble": 0, "calculate": 0, "validate": 0, "render": 0}
    assert window.diagnostics()["vision_hidden_compute_count"] == 0

    window._main_tabs.setCurrentWidget(window._vision_method_area)
    app().processEvents()
    window._render_current_view()
    assert calls["render"] == 1


def test_hidden_vision_100_refresh_cycles_do_not_calculate_or_render(monkeypatch):
    app()
    lifecycle, runtime = _live_lifecycle()
    item = snapshot()
    report = validate_vision_method(item)
    runtime.current_snapshot = replace(
        runtime.current_snapshot,
        vision_method_snapshot=item,
        vision_method_validation_report=report,
    )
    window = VisionMainWindow(lifecycle)
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    calls = {"assemble": 0, "calculate": 0, "validate": 0, "render": 0}
    from desktop.vision_method import live_integration

    def forbidden(name):
        def _raise(*_args, **_kwargs):
            calls[name] += 1
            raise AssertionError(f"{name} must not run during hidden dashboard refresh")

        return _raise

    monkeypatch.setattr(live_integration, "assemble_vision_method_runtime", forbidden("assemble"))
    monkeypatch.setattr(live_integration, "calculate_vision_method_snapshot", forbidden("calculate"))
    monkeypatch.setattr(live_integration, "validate_vision_method", forbidden("validate"))
    monkeypatch.setattr(window._vision_method_inspector, "render_live_status", lambda *_args, **_kwargs: calls.__setitem__("render", calls["render"] + 1))

    for _ in range(100):
        window.refresh()

    assert calls == {"assemble": 0, "calculate": 0, "validate": 0, "render": 0}
    assert window.diagnostics()["vision_hidden_compute_count"] == 0


def test_visible_changed_vision_renders_once_and_unchanged_skips(monkeypatch):
    app()
    lifecycle, runtime = _live_lifecycle()
    first = snapshot()
    first_report = validate_vision_method(first)
    second = snapshot(timestamp=first.timestamp + timedelta(minutes=5))
    second_report = validate_vision_method(second)
    runtime.current_snapshot = replace(
        runtime.current_snapshot,
        vision_method_snapshot=first,
        vision_method_validation_report=first_report,
    )
    window = VisionMainWindow(lifecycle)
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    renders = []
    original_render = window._vision_method_inspector.render_live_status
    monkeypatch.setattr(
        window._vision_method_inspector,
        "render_live_status",
        lambda *args, **kwargs: (renders.append(args), original_render(*args, **kwargs))[1],
    )

    window.refresh()
    window._main_tabs.setCurrentWidget(window._vision_method_area)
    app().processEvents()
    window._render_current_view()
    assert len(renders) == 1

    window.refresh()
    assert len(renders) == 1
    assert window.diagnostics()["vision_visual_render_skipped"] is True

    runtime.current_snapshot = replace(
        runtime.current_snapshot,
        vision_method_snapshot=second,
        vision_method_validation_report=second_report,
    )
    window.refresh()

    assert len(renders) == 2
    assert window._vision_method_inspector._labels["Timestamp"].text() == "29-Jul-2026 10:35:00 IST"


def test_vision_dirty_render_preserves_scroll_position():
    app()
    lifecycle, runtime = _live_lifecycle()
    first = snapshot()
    first_report = validate_vision_method(first)
    runtime.current_snapshot = replace(
        runtime.current_snapshot,
        vision_method_snapshot=first,
        vision_method_validation_report=first_report,
    )
    window = VisionMainWindow(lifecycle)
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    window.refresh()
    window._main_tabs.setCurrentWidget(window._vision_method_area)
    app().processEvents()
    window._render_current_view()
    window._vision_method_scroll.verticalScrollBar().setValue(25)
    second = snapshot(timestamp=first.timestamp + timedelta(minutes=5))
    second_report = validate_vision_method(second)
    runtime.current_snapshot = replace(
        runtime.current_snapshot,
        vision_method_snapshot=second,
        vision_method_validation_report=second_report,
    )

    window.refresh()

    bar = window._vision_method_scroll.verticalScrollBar()
    assert bar.value() == min(25, bar.maximum())
    assert window._vision_method_scroll is window._main_tabs.widget(1).layout().itemAt(0).widget()


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
