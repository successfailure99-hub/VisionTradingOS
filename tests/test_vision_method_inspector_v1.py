import os
from dataclasses import replace
from dataclasses import FrozenInstanceError
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
from desktop.vision_method import (
    VisionMethodInspector,
    VisionMethodLiveInspectorBridge,
    VisionMethodLiveRuntimeState,
)
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
_DEFAULT = object()


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
    assert missing.status.runtime_state is VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
    assert panel._labels["Candidate State"].text() == "insufficient_data"
    assert panel._labels["Assembly Failures"].text() == "Candle Engine missing: Closed candle history is unavailable."

    runtime.history = _candles()
    runtime.current_snapshot = _runtime_snapshot(history=runtime.history)

    def fail_validation(_snapshot):
        raise RuntimeError("validation unavailable")

    monkeypatch.setattr("desktop.vision_method.live_integration.validate_vision_method", fail_validation)
    invalid = bridge.refresh()

    assert invalid.ready is False
    assert invalid.validation_report is None
    assert "validation unavailable" in invalid.reason
    assert invalid.status.runtime_state is VisionMethodLiveRuntimeState.INTERNAL_ERROR


def test_live_bridge_converts_liquidity_failure_into_visible_insufficient_snapshot(monkeypatch):
    app()
    lifecycle, _runtime = _live_lifecycle()
    panel = VisionMethodInspector()

    def fail_liquidity(*_args, **_kwargs):
        raise ValueError("overlapping gaps")

    monkeypatch.setattr("desktop.vision_method.live_integration.assemble_vision_liquidity_context", fail_liquidity)

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.ready is False
    assert result.snapshot is not None
    assert result.validation_report is not None
    assert result.snapshot.candidate_state.value == "insufficient_data"
    assert result.validation_report.validation_result.value == "insufficient_data"
    assert result.failures[0].stage == "Liquidity"
    assert result.failures[0].validation_message == "ValueError: overlapping gaps"
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.DEGRADED
    assert panel._labels["Candidate State"].text() == "insufficient_data"
    assert "Liquidity failed: ValueError: overlapping gaps" in panel._labels["Assembly Failures"].text()
    assert "Structure Events failed: ValueError: insufficient liquidity context." in panel._labels["Assembly Failures"].text()
    assert "Liquidity" in panel._trace_labels[7].text()
    assert "overlapping gaps" in panel._trace_labels[7].text()


def test_live_bridge_startup_without_market_timestamp_renders_waiting_status():
    app()
    lifecycle = ApplicationBootstrap().create_application()
    runtime = _FakeRuntime(_runtime_snapshot_without_market_timestamp(), ())
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    panel = VisionMethodInspector()

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.snapshot is None
    assert result.validation_report is None
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.WAITING_FOR_MARKET_DATA
    assert panel._labels["Runtime State"].text() == "WAITING_FOR_MARKET_DATA"
    assert panel._labels["Candidate State"].text() == "insufficient_data"
    assert panel._labels["Quality"].text() == "invalid"
    assert panel._labels["Validation Result"].text() == "insufficient_data"
    assert panel._labels["Live Blocking Stage"].text() == "MARKET_DATA"
    assert panel._labels["Blocking Reason"].text() == "No market timestamp is available."
    assert panel._labels["Instrument"].text() != "-"


def test_live_bridge_early_market_data_without_closed_candle_collects_context():
    app()
    lifecycle, _runtime = _live_lifecycle(history=())
    panel = VisionMethodInspector()

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.status.runtime_state is VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
    assert panel._labels["Instrument"].text() == "NIFTY"
    assert panel._labels["Timeframe"].text() == "5m"
    assert panel._labels["Timestamp"].text() != "-"
    assert panel._labels["Live Blocking Stage"].text() == "CANDLE_ENGINE"
    assert panel._labels["Available Contexts"].text() == "Market Data"
    assert "Closed candle history is unavailable" in panel._labels["Blocking Reason"].text()


def test_live_bridge_missing_daily_context_keeps_candle_progress_visible():
    app()
    history = _candles()
    lifecycle = ApplicationBootstrap().create_application()
    runtime = _FakeRuntime(_runtime_snapshot(history=history, cpr=None, camarilla=None), history)
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    panel = VisionMethodInspector()

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.snapshot is None
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
    assert panel._labels["Available Contexts"].text() == "Market Data, Candle Engine"
    assert panel._labels["CPR Position"].text() == "missing"
    assert panel._labels["Camarilla Zone"].text() == "missing"
    assert panel._labels["Assembly Failures"].text() == "Level Context missing: Daily CPR levels are unavailable."


def test_live_bridge_structure_failure_reports_blocking_without_blank_screen(monkeypatch):
    app()
    lifecycle, _runtime = _live_lifecycle()
    panel = VisionMethodInspector()

    def fail_structure(*_args, **_kwargs):
        raise ValueError("Insufficient closed candles.")

    monkeypatch.setattr("desktop.vision_method.live_integration.assemble_vision_structure_context", fail_structure)

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.status.runtime_state is VisionMethodLiveRuntimeState.DEGRADED
    assert result.snapshot is not None
    assert panel._labels["Trend"].text() == "unknown"
    assert "Structure failed: ValueError: Insufficient closed candles." in panel._labels["Failed Contexts"].text()
    assert panel._labels["Candidate State"].text() == "insufficient_data"


def test_live_bridge_missing_option_chain_is_safe_and_deterministic():
    app()
    lifecycle, _runtime = _live_lifecycle()
    panel = VisionMethodInspector()

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.snapshot is not None
    assert result.validation_report is not None
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
    assert panel._labels["Option Confirmation"].text() == "unavailable"
    assert panel._labels["Validation Result"].text() == "insufficient_data"


def test_live_bridge_status_transitions_are_rendered(monkeypatch):
    app()
    lifecycle = ApplicationBootstrap().create_application()
    runtime = _FakeRuntime(_runtime_snapshot_without_market_timestamp(), ())
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    panel = VisionMethodInspector()
    bridge = VisionMethodLiveInspectorBridge(lifecycle, panel)

    waiting = bridge.refresh()
    runtime.current_snapshot = _runtime_snapshot(history=(), timestamp=NOW)
    collecting = bridge.refresh()

    def fail_liquidity(*_args, **_kwargs):
        raise ValueError("overlapping gaps")

    monkeypatch.setattr("desktop.vision_method.live_integration.assemble_vision_liquidity_context", fail_liquidity)
    runtime.history = _candles()
    runtime.current_snapshot = _runtime_snapshot(history=runtime.history, timestamp=NOW)
    degraded = bridge.refresh()
    monkeypatch.undo()
    readyish = bridge.refresh()

    assert waiting.status.runtime_state is VisionMethodLiveRuntimeState.WAITING_FOR_MARKET_DATA
    assert collecting.status.runtime_state is VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
    assert degraded.status.runtime_state is VisionMethodLiveRuntimeState.DEGRADED
    assert readyish.status.runtime_state in {
        VisionMethodLiveRuntimeState.READY,
        VisionMethodLiveRuntimeState.COLLECTING_CONTEXT,
    }
    assert panel._labels["Runtime State"].text() == readyish.status.runtime_state.value


def test_live_bridge_status_model_is_immutable():
    app()
    lifecycle, _runtime = _live_lifecycle(history=())
    status = VisionMethodLiveInspectorBridge(lifecycle, VisionMethodInspector()).refresh().status

    with pytest.raises(FrozenInstanceError):
        status.blocking_reason = "changed"


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


def _runtime_snapshot(*, history=None, timestamp=NOW, price=102.0, cpr=_DEFAULT, camarilla=_DEFAULT):
    history = _candles() if history is None else tuple(history)
    return RuntimeSnapshot(
        symbol=RuntimeInstrument.NIFTY,
        timeframe="5m",
        status=RuntimeStatus.RUNNING,
        latest_tick=Tick(Instrument.NIFTY, Exchange.NSE, timestamp, price, 10_000, price - 0.5, price + 0.5, 100),
        latest_candle=history[-1] if history else None,
        vwap=None,
        cpr=_cpr() if cpr is _DEFAULT else cpr,
        camarilla=_camarilla() if camarilla is _DEFAULT else camarilla,
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


def _runtime_snapshot_without_market_timestamp():
    return RuntimeSnapshot(
        symbol=RuntimeInstrument.NIFTY,
        timeframe="5m",
        status=RuntimeStatus.RUNNING,
        latest_tick=None,
        latest_candle=None,
        vwap=None,
        cpr=None,
        camarilla=None,
        price_action=None,
        option_chain=None,
        market_context=None,
        ai_reasoning=None,
        strategy=None,
        risk=None,
        latest_order=None,
        position=None,
        latest_journal_record=None,
        updated_at=None,
        latest_tick_at=None,
        latest_closed_candle_at=None,
        latest_analysis_at=None,
        snapshot_created_at=None,
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
