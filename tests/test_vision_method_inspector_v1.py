import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from application import ApplicationBootstrap
from dashboard.main_window import VisionMainWindow
from desktop.vision_method import VisionMethodInspector
from engines.vision_method import (
    VisionMethodValidationTraceStep,
    VisionOptionConfirmation,
    validate_vision_method,
)
from tests.test_vision_method_validation_v1 import option, snapshot


def app():
    return QApplication.instance() or QApplication([])


def test_inspector_renders_snapshot_header_and_method_sections():
    app()
    item = snapshot()
    report = validate_vision_method(item)
    panel = VisionMethodInspector()

    panel.render(item, report)

    assert panel._labels["Instrument"].text() == "NIFTY"
    assert panel._labels["Timeframe"].text() == "5m"
    assert panel._labels["Candidate State"].text() == "long_eligible"
    assert panel._labels["Method Candidate State"].text() == "long_eligible"
    assert panel._labels["Method Quality"].text() == "high"
    assert panel._labels["CPR Position"].text() == "above_cpr"
    assert panel._labels["Camarilla Zone"].text() == "h3_h4"
    assert panel._labels["Setup Classification"].text() == "trend_continuation"
    assert panel._labels["Option Confirmation"].text() == "confirms"


def test_inspector_renders_validation_metrics_and_trace_in_order():
    app()
    item = snapshot()
    report = validate_vision_method(item)
    panel = VisionMethodInspector()

    panel.render(item, report)

    assert panel._labels["Validation Result"].text() == "valid"
    assert panel._labels["Completed Steps"].text() == "10"
    assert panel._labels["Failed Steps"].text() == "0"
    assert panel._labels["Missing Steps"].text() == "0"
    assert panel._trace_labels[0].text() == "STEP 1 | CPR | above_cpr | pass"
    assert panel._trace_labels[-1].text() == "FINAL | FINAL | long_eligible | pass | high"


def test_inspector_exposes_conflict_without_summarizing_trace():
    app()
    item = snapshot(option_confirmation_context=option(state=VisionOptionConfirmation.CONTRADICTS))
    report = validate_vision_method(item)
    panel = VisionMethodInspector()

    panel.render(item, report)

    assert panel._labels["Validation Result"].text() == "conflict"
    assert panel._labels["Blocking Stage"].text() == "Option Chain"
    assert panel._labels["Option Contradicting Factors"].text() == "Call writing contradicts setup"
    assert panel._trace_labels[9].text() == "STEP 10 | Option Chain | contradicts | fail | Call writing contradicts setup"


def test_inspector_missing_data_state_uses_placeholders():
    app()
    panel = VisionMethodInspector()

    panel.render(None, None)

    assert panel._labels["Instrument"].text() == "-"
    assert panel._labels["Validation Result"].text() == "-"
    assert panel._labels["ADR Used"].text() == "-"
    assert tuple(label.text() for label in panel._trace_labels) == ("-",)


def test_inspector_renders_large_validation_trace_without_collapsing_steps():
    app()
    item = snapshot()
    report = validate_vision_method(item)
    trace = tuple(
        VisionMethodValidationTraceStep(index, f"Stage {index}", f"Observed {index}", "pass")
        for index in range(1, 41)
    )
    export_record = replace(report.export_record, trace=tuple(f"STEP {index} | Stage {index} | Observed {index} | pass" for index in range(1, 41)))
    large_report = replace(report, trace=trace, export_record=export_record)
    panel = VisionMethodInspector()

    panel.render(item, large_report)

    assert len(panel._trace_labels) == 40
    assert panel._trace_labels[0].text() == "STEP 1 | Stage 1 | Observed 1 | pass"
    assert panel._trace_labels[-1].text() == "STEP 40 | Stage 40 | Observed 40 | pass"


def test_inspector_is_read_only_and_rejects_invalid_inputs():
    app()
    panel = VisionMethodInspector()

    assert panel.findChildren(QPushButton) == []
    with pytest.raises(TypeError):
        panel.render(object(), None)
    with pytest.raises(TypeError):
        panel.render(None, object())


def test_main_window_exposes_top_level_vision_method_tab_without_runtime_ownership():
    app()
    window = VisionMainWindow(ApplicationBootstrap().create_application())

    assert [window._main_tabs.tabText(index) for index in range(window._main_tabs.count())] == [
        "Trading",
        "Vision Method",
        "System",
    ]
    assert isinstance(window._vision_method_inspector, VisionMethodInspector)
    item = snapshot()
    report = validate_vision_method(item)
    window.render_vision_method(item, report)
    assert window._vision_method_inspector._labels["Candidate State"].text() == "long_eligible"
