"""
Tests for runtime dashboard panel.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dashboard.models import DashboardRuntimeComponentHealthView, DashboardRuntimeHealthSummary, DashboardRuntimeView
from dashboard.panels.runtime_panel import RuntimePanel


def app():
    return QApplication.instance() or QApplication([])


def runtime_view(**overrides):
    values = dict(
        application_status="Running",
        broker_mode="Dry Run",
        safety_mode="Analysis Only",
        configured_instruments=("NIFTY",),
        market_data_ready=True,
        trade_journal_ready=False,
        start_count=1,
        stop_count=0,
        restart_count=0,
        last_started_at=None,
        last_stopped_at=None,
        last_error=None,
    )
    values.update(overrides)
    return DashboardRuntimeView(**values)


def test_runtime_status_safety_and_broker_render():
    app()
    panel = RuntimePanel()
    panel.render(runtime_view())
    assert panel._labels["Application"].text() == "Running"
    assert panel._labels["Safety"].text() == "Analysis Only"
    assert panel._labels["Broker"].text() == "Dry Run"
    assert panel._labels["Application"].property("status") == "positive"


def test_counters_and_readiness_render():
    panel = RuntimePanel()
    panel.render(runtime_view(start_count=2, stop_count=1, restart_count=3))
    assert panel._labels["Starts"].text() == "2"
    assert panel._labels["Stops"].text() == "1"
    assert panel._labels["Restarts"].text() == "3"
    assert panel._labels["Market Data"].text() == "Ready"
    assert panel._labels["Journal"].text() == "Not Ready"
    assert panel._labels["Market Data"].property("status") == "positive"
    assert panel._labels["Journal"].property("status") == "warning"


def test_last_error_and_missing_timestamps_render_safely():
    panel = RuntimePanel()
    panel.render(runtime_view(last_error="boom"))
    assert panel._labels["Last Error"].text() == "boom"
    assert panel._labels["Started At"].text() == "-"
    assert panel._labels["Stopped At"].text() == "-"


def test_runtime_component_health_renders_as_status_badges():
    panel = RuntimePanel()
    panel.render(
        runtime_view(
            component_health=(
                DashboardRuntimeComponentHealthView("AI Reasoning", "Ready"),
                DashboardRuntimeComponentHealthView("Fusion", "Waiting"),
                DashboardRuntimeComponentHealthView("Vision Daily Context", "READY", "Owner=SymbolRuntime | Producer=CPR"),
            ),
        )
    )
    assert panel._labels["Health: AI Reasoning"].text() == "Ready"
    assert panel._labels["Health: AI Reasoning"].property("status") == "positive"
    assert panel._labels["Health: Fusion"].text() == "Waiting"
    assert panel._labels["Health: Vision Daily Context"].text() == "READY"
    assert panel._labels["Health: Vision Daily Context"].toolTip() == "Owner=SymbolRuntime | Producer=CPR"


def test_runtime_health_summary_renders_near_top():
    panel = RuntimePanel()
    panel.render(
        runtime_view(
            runtime_health_summary=DashboardRuntimeHealthSummary(
                "FAILED",
                primary_failure="Runtime Contract",
                failure_reason="Runtime Contract Failed | Reason=Timezone mismatch",
                blocking=True,
                failed_component_count=1,
                tooltip="Component: Runtime Contract\nStatus: FAILED\nReason: Runtime Contract Failed | Reason=Timezone mismatch\nUpdated: -\nBlocking: Yes",
            ),
        )
    )

    assert panel._labels["Runtime Health"].text() == "FAILED"
    assert panel._labels["Runtime Health"].toolTip().startswith("Component: Runtime Contract")
    assert panel._labels["Primary Failure"].text() == "Runtime Contract"
    assert "Timezone mismatch" in panel._labels["Failure Reason"].text()
    assert panel._labels["Failure Blocking"].text() == "Yes"
    assert panel._labels["Failed Components"].text() == "1"
