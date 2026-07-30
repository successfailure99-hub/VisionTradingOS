import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from application import ApplicationBootstrap, RuntimeSnapshot
from application.enums import RuntimeInstrument, RuntimeStatus
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.models.candle import Candle
from core.models.tick import Tick
from dashboard.main_window import VisionMainWindow
from desktop.vision_method import VisionMethodInspector, VisionMethodLiveInspectorBridge
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.vision_method import (
    VisionMethodValidationTraceStep,
    VisionOptionConfirmation,
    validate_vision_method,
)
from tests.test_vision_method_validation_v1 import option, snapshot


IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 7, 29, 10, 0, tzinfo=IST)


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


def test_live_bridge_generates_snapshot_validation_and_updates_inspector():
    app()
    lifecycle, runtime = _live_lifecycle()
    panel = VisionMethodInspector()
    bridge = VisionMethodLiveInspectorBridge(lifecycle, panel)

    result = bridge.refresh()

    assert result.ready is True
    assert result.snapshot is bridge.last_snapshot
    assert result.validation_report is bridge.last_report
    assert panel._labels["Instrument"].text() == "NIFTY"
    assert panel._labels["Candidate State"].text() != "-"
    assert panel._labels["Validation Result"].text() != "-"
    assert panel._labels["Option Confirmation"].text() == "unavailable"
    assert runtime.snapshot_calls == 1
    assert runtime.history_calls == 1


def test_live_bridge_refreshes_sequential_updates_without_stale_values():
    app()
    lifecycle, runtime = _live_lifecycle()
    panel = VisionMethodInspector()
    bridge = VisionMethodLiveInspectorBridge(lifecycle, panel)

    first = bridge.refresh()
    runtime.history = _candles(final_close=104.0)
    runtime.current_snapshot = _runtime_snapshot(
        history=runtime.history,
        timestamp=NOW + timedelta(minutes=5),
        price=104.0,
    )
    second = bridge.refresh()

    assert first.snapshot is not None
    assert second.snapshot is not None
    assert second.snapshot.timestamp == NOW + timedelta(minutes=5)
    assert panel._labels["Timestamp"].text() != "-"
    assert panel._labels["Timestamp"].text() != first.snapshot.timestamp.isoformat()


def test_live_bridge_missing_snapshot_or_validation_fails_closed(monkeypatch):
    app()
    lifecycle, runtime = _live_lifecycle(history=())
    panel = VisionMethodInspector()
    bridge = VisionMethodLiveInspectorBridge(lifecycle, panel)

    missing = bridge.refresh()

    assert missing.ready is False
    assert missing.snapshot is None
    assert panel._labels["Candidate State"].text() == "-"

    runtime.history = _candles()
    runtime.current_snapshot = _runtime_snapshot(history=runtime.history)

    def fail_validation(_snapshot):
        raise RuntimeError("validation unavailable")

    monkeypatch.setattr("desktop.vision_method.live_integration.validate_vision_method", fail_validation)
    invalid = bridge.refresh()

    assert invalid.ready is False
    assert invalid.validation_report is None
    assert "validation unavailable" in invalid.reason


def test_main_window_refresh_updates_live_vision_method_inspector():
    app()
    lifecycle, runtime = _live_lifecycle()
    window = VisionMainWindow(lifecycle)
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})

    window.refresh()

    assert window._vision_method_inspector._labels["Instrument"].text() == "NIFTY"
    assert window._vision_method_inspector._labels["Candidate State"].text() != "-"
    assert window._vision_method_bridge.last_report is not None


def test_live_bridge_invokes_existing_calculator_once_per_refresh(monkeypatch):
    app()
    lifecycle, _runtime = _live_lifecycle()
    from desktop.vision_method import live_integration

    calls = 0
    original = live_integration.calculate_vision_method_snapshot

    def wrapped(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(live_integration, "calculate_vision_method_snapshot", wrapped)

    result = VisionMethodLiveInspectorBridge(lifecycle, VisionMethodInspector()).refresh()

    assert result.ready is True
    assert calls == 1


class _FakeRuntime:
    def __init__(self, snapshot_value, history):
        self.instrument = RuntimeInstrument.NIFTY
        self.current_snapshot = snapshot_value
        self.history = tuple(history)
        self.snapshot_calls = 0
        self.history_calls = 0

    def snapshot(self, *_args, **_kwargs):
        self.snapshot_calls += 1
        return self.current_snapshot

    def get_candle_history(self, _timeframe=None):
        self.history_calls += 1
        return self.history


def _live_lifecycle(*, history=None):
    history = _candles() if history is None else tuple(history)
    lifecycle = ApplicationBootstrap().create_application()
    runtime = _FakeRuntime(_runtime_snapshot(history=history), history)
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    return lifecycle, runtime


def _runtime_snapshot(*, history=None, timestamp=NOW, price=102.0):
    history = _candles() if history is None else tuple(history)
    return RuntimeSnapshot(
        symbol=RuntimeInstrument.NIFTY,
        timeframe="5m",
        status=RuntimeStatus.RUNNING,
        latest_tick=Tick(Instrument.NIFTY, Exchange.NSE, timestamp, price, 10_000, price - 0.5, price + 0.5, 100),
        latest_candle=history[-1] if history else None,
        vwap=None,
        cpr=_cpr(),
        camarilla=_camarilla(),
        price_action=None,
        option_chain=None,
        market_context=None,
        ai_reasoning=None,
        strategy=None,
        risk=None,
        latest_order=None,
        position=None,
        latest_journal_record=None,
        updated_at=timestamp,
        latest_tick_at=timestamp,
        latest_closed_candle_at=timestamp,
        latest_analysis_at=timestamp,
        snapshot_created_at=timestamp,
    )


def _candles(*, final_close=103.0):
    start = datetime(2026, 7, 29, 9, 15, tzinfo=IST)
    values = (
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 102.0, 99.5, 101.0),
        (101.0, 101.5, 99.5, 100.0),
        (100.0, 103.0, 100.0, 102.0),
        (102.0, 102.5, 100.0, 101.0),
        (101.0, 104.0, 101.0, 103.0),
        (103.0, 103.5, 101.0, 102.0),
        (102.0, 105.0, 102.0, final_close),
    )
    return tuple(
        Candle(
            symbol="NIFTY",
            timeframe="5m",
            start_time=start + timedelta(minutes=5 * index),
            end_time=start + timedelta(minutes=5 * (index + 1)),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=1000 + index,
        )
        for index, (open_, high, low, close) in enumerate(values)
    )


def _cpr():
    return CPRLevels(
        trading_date=NOW.date(),
        previous_high=110.0,
        previous_low=90.0,
        previous_close=100.0,
        pivot=100.0,
        bc=99.0,
        tc=101.0,
        width=2.0,
        width_percentage=2.0,
    )


def _camarilla():
    return CamarillaLevels(
        trading_date=NOW.date(),
        previous_high=110.0,
        previous_low=90.0,
        previous_close=100.0,
        pivot=100.0,
        h3=103.0,
        h4=104.0,
        h5=105.0,
        h6=106.0,
        l3=97.0,
        l4=96.0,
        l5=95.0,
        l6=94.0,
    )
