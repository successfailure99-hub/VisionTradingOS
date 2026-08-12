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
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from core.models.tick import Tick
from dashboard.main_window import VisionMainWindow
from desktop.vision_method import (
    VisionMethodInspector,
    VisionMethodLiveInspectorBridge,
    VisionMethodLiveRuntimeState,
    VisionMethodLiveStatus,
)
from engines.adr import ADRExpansionState, ADRExhaustionState
from engines.adr.models import ADRSnapshot
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.vision_method import (
    VisionCandidateState,
    VisionMethodValidationTraceStep,
    VisionOptionConfirmation,
    VisionPriceActionTriggerStageStatus,
    VisionTriggerDirection,
    VisionTriggerType,
    build_pivot_flight_plan,
    failed_price_action_trigger_stage_result,
    VisionPivotFlightPlanRequest,
    validate_vision_method,
)
from core.models.daily_ohlc import DailyOHLC
from engines.cpr.calculator import CPRCalculator
from engines.camarilla.calculator import CamarillaCalculator
from engines.vwap.levels import VWAPLevels
from tests.test_vision_method_calculator_v1 import trigger
from tests.test_vision_method_validation_v1 import option, setup, snapshot


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
    assert panel._labels["Entry Location"].text() == "acceptable"
    assert panel._labels["Direction Quality"].text() == "high"
    assert panel._labels["Chase Risk"].text() == "low"
    assert panel._labels["Final Candidate"].text() == "long_eligible"
    assert panel._labels["Final Trigger Gate"].text() == "passed"
    assert panel._labels["Final Location Gate"].text() == "passed"
    assert panel._labels["Final Promotion Reason"].text() == "direction, trigger, location, and option state are aligned"


def test_inspector_renders_pivot_flight_plan_context():
    app()
    history = tuple(
        DailyOHLC((NOW.date() - timedelta(days=7)) + timedelta(days=index), 100.0 + index, 102.0 + index, 98.0 + index, 101.0 + index)
        for index in range(6)
    )
    source = DailyOHLC(NOW.date() - timedelta(days=1), 115.0, 120.0, 100.0, 116.0)
    plan = build_pivot_flight_plan(
        VisionPivotFlightPlanRequest(
            instrument=RuntimeInstrument.NIFTY,
            trading_date=NOW.date(),
            reference_session_date=NOW.date() - timedelta(days=1),
            generated_at=NOW,
            current_cpr=replace(CPRCalculator.calculate(source), trading_date=NOW.date()),
            current_camarilla=replace(CamarillaCalculator.calculate(source), trading_date=NOW.date()),
            historical_daily_ohlc=history,
        )
    )
    item = snapshot(pivot_flight_plan=plan)
    report = validate_vision_method(item)
    panel = VisionMethodInspector()

    panel.render(item, report)

    assert panel._labels["CPR Relationship"].text() != "-"
    assert panel._labels["Camarilla Relationship"].text() != "-"
    assert panel._labels["Opening Confirmation Required"].text() == "Yes"
    assert "H3_IF_OPEN_ABOVE_H3" in panel._labels["Bullish Action Zones"].text()


def test_inspector_renders_validation_metrics_and_trace_in_order():
    app()
    item = snapshot()
    report = validate_vision_method(item)
    panel = VisionMethodInspector()

    panel.render(item, report)

    assert panel._labels["Validation Result"].text() == "valid"
    assert panel._labels["Completed Steps"].text() == "11"
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

    assert panel._labels["Validation Result"].text() == "partial"
    assert panel._labels["Blocking Stage"].text() == "-"
    assert panel._labels["Option Contradicting Factors"].text() == "Call writing contradicts setup"
    assert panel._trace_labels[9].text() == "STEP 10 | Option Chain | contradicts | pass | Call writing contradicts setup"


def test_live_status_cannot_override_canonical_snapshot_and_report_values():
    app()
    item = snapshot(option_confirmation_context=option(state=VisionOptionConfirmation.UNAVAILABLE))
    report = validate_vision_method(item)
    status = VisionMethodLiveStatus(
        instrument="NIFTY",
        timeframe="5m",
        market_timestamp=NOW.isoformat(),
        runtime_state=VisionMethodLiveRuntimeState.COLLECTING_CONTEXT,
        candidate_state="insufficient_data",
        quality="invalid",
        validation_result="insufficient_data",
        blocking_stage="Setup",
        blocking_reason="fallback status",
        available_contexts=("Market Data",),
        missing_contexts=(),
        failed_contexts=(),
        unexpected_error=None,
        updated_at=NOW,
    )
    panel = VisionMethodInspector()

    panel.render_live_status(status, item, report)

    assert report.candidate_state.value == "long_eligible"
    assert report.metrics.blocking_stage is None
    assert panel._labels["Candidate State"].text() == "long_eligible"
    assert panel._labels["Method Candidate State"].text() == "long_eligible"
    assert panel._labels["Quality"].text() == "low"
    assert panel._labels["Validation Result"].text() == "partial"
    assert panel._labels["Blocking Stage"].text() == "-"
    assert panel._labels["Setup Classification"].text() == "trend_continuation"
    assert panel._labels["Option Confirmation"].text() == "unavailable"
    assert panel._trace_labels[-1].text() == "FINAL | FINAL | long_eligible | pass | low"


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
    assert result.status.candidate_state == "avoid"
    assert result.status.validation_result == "invalid"
    assert result.status.level_context is not None
    assert result.status.opening_range_context is not None
    assert result.status.structure_context is not None
    assert result.status.structure_event_context is not None
    assert result.failures[0].stage == "Liquidity"
    assert result.failures[0].validation_message == "overlapping gaps"
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.DEGRADED
    assert panel._labels["Candidate State"].text() == "avoid"
    assert "Liquidity failed: overlapping gaps" in panel._labels["Assembly Failures"].text()
    assert "Structure Events not_evaluated: Liquidity context is unavailable." not in panel._labels["Assembly Failures"].text()
    assert panel._trace_labels[0].text() == "STEP 1 | CPR | above_cpr | pass"
    assert "overlapping gaps" in panel._labels["Failed Contexts"].text()


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
    assert panel._labels["Quality"].text() == "insufficient"
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
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.WAITING_DAILY_CONTEXT
    assert panel._labels["Available Contexts"].text() == "Market Data, Candle Engine, Opening Range, Structure, Liquidity, Structure Events"
    assert panel._labels["CPR Position"].text() == "missing"
    assert panel._labels["Camarilla Zone"].text() == "missing"
    assert "CPR missing: WAITING_DAILY_CONTEXT: Daily CPR levels are unavailable." in panel._labels["Assembly Failures"].text()
    assert "Camarilla missing: WAITING_DAILY_CONTEXT: Daily Camarilla levels are unavailable." in panel._labels["Assembly Failures"].text()


def test_live_bridge_blocks_previous_session_cpr_before_level_assembly():
    app()
    history = _candles()
    lifecycle = ApplicationBootstrap().create_application()
    runtime = _FakeRuntime(
        _runtime_snapshot(history=history, cpr=replace(_cpr(), trading_date=NOW.date() - timedelta(days=1))),
        history,
    )
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    panel = VisionMethodInspector()

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.snapshot is None
    assert result.validation_report is None
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.WAITING_DAILY_CONTEXT
    assert result.status.blocking_stage == "CPR"
    assert result.status.blocking_reason == f"WAITING_DAILY_CONTEXT: CPR levels are not refreshed for {NOW.date()}."
    assert panel._labels["Runtime State"].text() == "WAITING_DAILY_CONTEXT"
    assert panel._labels["Live Blocking Stage"].text() == "CPR"
    assert panel._labels["CPR Position"].text() == "missing"
    assert panel._labels["Opening High"].text() != "not_evaluated"
    assert panel._labels["Trend"].text() != "not_evaluated"
    assert panel._labels["Buy Side Sweep"].text() != "not_evaluated"
    assert f"CPR missing: WAITING_DAILY_CONTEXT: CPR levels are not refreshed for {NOW.date()}." in panel._labels["Assembly Failures"].text()


def test_live_bridge_independent_contexts_run_when_cpr_is_missing(monkeypatch):
    app()
    history = _candles()
    lifecycle = ApplicationBootstrap().create_application()
    runtime = _FakeRuntime(
        _runtime_snapshot(history=history, cpr=replace(_cpr(), trading_date=NOW.date() - timedelta(days=1))),
        history,
    )
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    from desktop.vision_method import live_integration

    calls = {"opening": 0, "structure": 0, "liquidity": 0, "option": 0}
    original_opening = live_integration.assemble_vision_opening_range_context
    original_structure = live_integration.assemble_vision_structure_context
    original_liquidity = live_integration.assemble_vision_liquidity_context
    original_option = live_integration.assemble_vision_option_confirmation_context

    def opening(*args, **kwargs):
        calls["opening"] += 1
        return original_opening(*args, **kwargs)

    def structure(*args, **kwargs):
        calls["structure"] += 1
        return original_structure(*args, **kwargs)

    def liquidity(*args, **kwargs):
        calls["liquidity"] += 1
        return original_liquidity(*args, **kwargs)

    def option_confirmation(*args, **kwargs):
        calls["option"] += 1
        return original_option(*args, **kwargs)

    monkeypatch.setattr(live_integration, "assemble_vision_opening_range_context", opening)
    monkeypatch.setattr(live_integration, "assemble_vision_structure_context", structure)
    monkeypatch.setattr(live_integration, "assemble_vision_liquidity_context", liquidity)
    monkeypatch.setattr(live_integration, "assemble_vision_option_confirmation_context", option_confirmation)

    result = VisionMethodLiveInspectorBridge(lifecycle, VisionMethodInspector()).refresh()

    assert result.snapshot is None
    assert result.status.opening_range_context is not None
    assert result.status.structure_context is not None
    assert result.status.liquidity_context is not None
    assert calls == {"opening": 1, "structure": 1, "liquidity": 1, "option": 0}


def test_live_bridge_blocks_previous_session_camarilla_before_level_assembly():
    app()
    history = _candles()
    lifecycle = ApplicationBootstrap().create_application()
    runtime = _FakeRuntime(
        _runtime_snapshot(history=history, camarilla=replace(_camarilla(), trading_date=NOW.date() - timedelta(days=1))),
        history,
    )
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    panel = VisionMethodInspector()

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.snapshot is None
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.WAITING_DAILY_CONTEXT
    assert result.status.blocking_stage == "CAMARILLA"
    assert result.status.blocking_reason == f"WAITING_DAILY_CONTEXT: Camarilla levels are not refreshed for {NOW.date()}."
    assert panel._labels["Available Contexts"].text() == "Market Data, Candle Engine, Opening Range, Structure, Liquidity, Structure Events"
    assert panel._labels["Camarilla Zone"].text() == "missing"


def test_live_bridge_omits_previous_session_optional_contexts_without_internal_error():
    app()
    history = _candles()
    lifecycle = ApplicationBootstrap().create_application()
    runtime = _FakeRuntime(
        _runtime_snapshot(
            history=history,
            adr=_adr(trading_date=NOW.date() - timedelta(days=1)),
            vwap=_vwap(trading_date=NOW.date() - timedelta(days=1)),
        ),
        history,
    )
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    panel = VisionMethodInspector()

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.snapshot is not None
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
    assert result.status.unexpected_error is None
    assert tuple(failure.stage for failure in result.failures[:2]) == ("ADR", "VWAP")
    assert panel._labels["ADR Used"].text() == "unavailable"
    assert panel._labels["VWAP Position"].text() == "unavailable"
    assert f"ADR missing: WAITING_DAILY_CONTEXT: ADR levels are not refreshed for {NOW.date()}." in panel._labels["Assembly Failures"].text()
    assert f"VWAP missing: WAITING_DAILY_CONTEXT: VWAP levels are not refreshed for {NOW.date()}." in panel._labels["Assembly Failures"].text()


def test_live_bridge_structure_failure_reports_blocking_without_blank_screen(monkeypatch):
    app()
    lifecycle, _runtime = _live_lifecycle()
    panel = VisionMethodInspector()

    def fail_structure(*_args, **_kwargs):
        raise ValueError("Insufficient closed candles.")

    monkeypatch.setattr("desktop.vision_method.live_integration.assemble_vision_structure_context", fail_structure)

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.status.runtime_state is VisionMethodLiveRuntimeState.DEGRADED
    assert result.snapshot is None
    assert result.status.level_context is not None
    assert result.status.opening_range_context is not None
    assert panel._labels["Trend"].text() == "unknown"
    assert "Structure failed: Waiting for required closed candle history." in panel._labels["Failed Contexts"].text()
    assert panel._labels["Candidate State"].text() == "insufficient_data"


def test_live_bridge_aligns_runtime_timestamp_to_closed_candle_timezone():
    app()
    history = _candles()
    lifecycle = ApplicationBootstrap().create_application()
    utc_timestamp = NOW.astimezone(timezone.utc)
    runtime = _FakeRuntime(_runtime_snapshot(history=history, timestamp=utc_timestamp), history)
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})

    result = VisionMethodLiveInspectorBridge(lifecycle, VisionMethodInspector()).refresh()

    assert result.snapshot is not None
    assert result.status.market_timestamp.endswith("+05:30")
    assert all("timezone" not in failure.validation_message.lower() for failure in result.failures)


def test_live_bridge_missing_option_chain_is_safe_and_deterministic():
    app()
    lifecycle, _runtime = _live_lifecycle()
    panel = VisionMethodInspector()

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.snapshot is not None
    assert result.validation_report is not None
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
    assert panel._labels["Option Confirmation"].text() == "unavailable"
    assert panel._labels["Validation Result"].text() == "invalid"
    assert panel._labels["Blocking Stage"].text() == "Setup"


def test_live_bridge_option_timezone_failure_is_neutral_without_hard_veto(monkeypatch):
    app()
    lifecycle, _runtime = _live_lifecycle()
    _runtime.current_snapshot = replace(
        _runtime.current_snapshot,
        price_action_trigger_context=trigger(
            direction=VisionTriggerDirection.BEARISH,
            trigger_type=VisionTriggerType.BEARISH_INITIATIVE_BREAKOUT,
            timestamp=NOW,
        ),
    )
    panel = VisionMethodInspector()

    def qualified_bearish_setup(*_args, **_kwargs):
        return setup(supporting=("Below CPR", "Below L3", "Bearish BOS"))

    def fail_option_confirmation(*_args, **_kwargs):
        raise ValueError("option_chain.timestamp timezone mismatch.")

    monkeypatch.setattr("desktop.vision_method.live_integration.assemble_vision_setup_qualification_context", qualified_bearish_setup)
    monkeypatch.setattr("desktop.vision_method.live_integration.assemble_vision_option_confirmation_context", fail_option_confirmation)

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.snapshot is not None
    assert result.validation_report is not None
    assert result.snapshot.candidate_state is VisionCandidateState.SHORT_ELIGIBLE
    assert result.snapshot.option_confirmation_context.confirmation_state is VisionOptionConfirmation.NEUTRAL
    assert result.validation_report.trace[9].status == "pass"
    assert result.validation_report.trace[-1].observed == "short_eligible"
    assert result.validation_report.trace[-1].status == "pass"
    assert panel._labels["Candidate State"].text() == "short_eligible"
    assert panel._labels["Option Confirmation"].text() == "neutral"
    assert panel._labels["Entry Location"].text() in {"acceptable", "favorable"}
    assert "ignored for setup evaluation" in panel._labels["Option Neutral Factors"].text()
    assert "timezone-aligned runtime data" not in panel._labels["Option Neutral Factors"].text()
    assert "timezone-aligned runtime data" not in panel._labels["Assembly Failures"].text()


def test_live_bridge_surfaces_trigger_technical_failure_without_trade_candidate():
    app()
    lifecycle, runtime = _live_lifecycle()
    stage = failed_price_action_trigger_stage_result(
        exc=ValueError("candle timeframe mismatch."),
        decision_timestamp=NOW,
        source_candle_reference="candle:NIFTY:1m:bad",
        trigger_zone_reference="hot_zone:bad",
        snapshot_generation=f"NIFTY:5m:{NOW.isoformat()}",
    )
    runtime.current_snapshot = replace(
        runtime.current_snapshot,
        price_action_trigger_context=None,
        price_action_trigger_stage_result=stage,
    )
    panel = VisionMethodInspector()

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.snapshot is not None
    assert result.snapshot.price_action_trigger_stage_result is stage
    assert result.status.runtime_state is VisionMethodLiveRuntimeState.DEGRADED
    assert panel._labels["Trigger Type"].text() == VisionPriceActionTriggerStageStatus.TRIGGER_ASSEMBLY_FAILED.value
    assert panel._labels["Trigger Reason"].text() == "candle timeframe mismatch."
    assert result.snapshot.candidate_state is not VisionCandidateState.LONG_ELIGIBLE
    assert result.snapshot.candidate_state is not VisionCandidateState.SHORT_ELIGIBLE


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


def test_live_bridge_opening_range_fallback_is_session_and_window_scoped():
    app()
    timestamp = datetime(2026, 8, 4, 9, 31, tzinfo=IST)
    session = datetime(2026, 8, 4, 9, 15, tzinfo=IST)
    previous_session = session - timedelta(days=1)
    previous = tuple(
        Candle(
            symbol="NIFTY",
            timeframe="1m",
            start_time=previous_session + timedelta(minutes=index),
            end_time=previous_session + timedelta(minutes=index + 1),
            open=25000.0,
            high=25053.05,
            low=24900.0,
            close=25000.0,
            volume=1000,
        )
        for index in range(15)
    )
    current = tuple(
        Candle(
            symbol="NIFTY",
            timeframe="1m",
            start_time=session + timedelta(minutes=index),
            end_time=session + timedelta(minutes=index + 1),
            open=24610.0,
            high=24620.0 + index,
            low=24600.75,
            close=24610.0,
            volume=1000,
        )
        for index in range(15)
        if index != 7
    )
    post_window = (
        Candle(
            symbol="NIFTY",
            timeframe="1m",
            start_time=session + timedelta(minutes=15),
            end_time=session + timedelta(minutes=16),
            open=24700.0,
            high=25053.05,
            low=24700.0,
            close=24750.0,
            volume=1000,
        ),
    )
    history = previous + current + post_window
    cpr = CPRLevels(timestamp.date(), 25000.0, 24500.0, 24700.0, 24700.0, 24650.0, 24750.0, 100.0, 0.4)
    camarilla = CamarillaLevels(
        timestamp.date(),
        25000.0,
        24500.0,
        24700.0,
        24700.0,
        24800.0,
        24900.0,
        25000.0,
        25100.0,
        24600.0,
        24500.0,
        24400.0,
        24300.0,
    )
    lifecycle = ApplicationBootstrap().create_application()
    runtime = _FakeRuntime(
        replace(
            _runtime_snapshot(history=history, timestamp=timestamp, cpr=cpr, camarilla=camarilla),
            timeframe="1m",
        ),
        history,
    )
    runtime.vision_decision_timeframe = TimeFrame.ONE_MINUTE
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    panel = VisionMethodInspector()

    result = VisionMethodLiveInspectorBridge(lifecycle, panel).refresh()

    assert result.status.opening_range_context is not None
    assert result.status.opening_range_context.range_complete is False
    assert panel._labels["Opening High"].text() == "24634.00"
    assert panel._labels["Opening Low"].text() == "24600.75"
    assert panel._labels["Opening Width"].text() == "33.25"
    assert panel._labels["Opening Expected Candles"].text() == "15"
    assert panel._labels["Opening Actual Candles"].text() == "14"
    assert "04-Aug-2026 09:22:00 IST" in panel._labels["Opening Missing Candles"].text()
    assert panel._labels["Candidate State"].text() == "insufficient_data"
    assert panel._labels["Quality"].text() == "insufficient"


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

    view = window.refresh()

    assert window._vision_method_inspector._labels["Instrument"].text() == "NIFTY"
    assert window._vision_method_inspector._labels["Candidate State"].text() != "-"
    assert window._vision_method_bridge.last_report is not None
    runtime_snapshot = lifecycle.orchestrator.snapshot().runtime_snapshots[0]
    assert runtime_snapshot.vision_method_snapshot is window._vision_method_bridge.last_snapshot
    assert runtime_snapshot.vision_method_validation_report is window._vision_method_bridge.last_report
    assert runtime_snapshot.vision_trade_candidate is not None
    assert view.strategies[0].candidate_state != "-"
    assert view.strategies[0].candidate_reference == runtime_snapshot.vision_trade_candidate.snapshot_reference


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

    def process_vision_method_paper_trade(self, snapshot, validation_report):
        from engines.runtime_adapter import adapt_vision_method_to_trade_candidate

        candidate = adapt_vision_method_to_trade_candidate(snapshot, validation_report)
        self.current_snapshot = replace(
            self.current_snapshot,
            vision_method_snapshot=snapshot,
            vision_method_validation_report=validation_report,
            vision_trade_candidate=candidate,
        )


def _live_lifecycle(*, history=None):
    history = _candles() if history is None else tuple(history)
    lifecycle = ApplicationBootstrap().create_application()
    runtime = _FakeRuntime(_runtime_snapshot(history=history), history)
    object.__setattr__(lifecycle.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: runtime})
    return lifecycle, runtime


def _runtime_snapshot(
    *,
    history=None,
    timestamp=NOW,
    price=102.0,
    cpr=_DEFAULT,
    camarilla=_DEFAULT,
    adr=_DEFAULT,
    vwap=_DEFAULT,
    price_action_trigger_context=_DEFAULT,
    price_action_trigger_stage_result=None,
):
    history = _candles() if history is None else tuple(history)
    return RuntimeSnapshot(
        symbol=RuntimeInstrument.NIFTY,
        timeframe="5m",
        status=RuntimeStatus.RUNNING,
        latest_tick=Tick(Instrument.NIFTY, Exchange.NSE, timestamp, price, 10_000, price - 0.5, price + 0.5, 100),
        latest_candle=history[-1] if history else None,
        vwap=None if vwap is _DEFAULT else vwap,
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
        adr=None if adr is _DEFAULT else adr,
        price_action_trigger_context=trigger(timestamp=timestamp) if price_action_trigger_context is _DEFAULT else price_action_trigger_context,
        price_action_trigger_stage_result=price_action_trigger_stage_result,
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


def _adr(*, trading_date=NOW.date()):
    return ADRSnapshot(
        trading_date=trading_date,
        instrument="NIFTY",
        adr_period=20,
        adr_value=100.0,
        today_high=150.0,
        today_low=50.0,
        today_range=100.0,
        adr_high=160.0,
        adr_low=60.0,
        range_consumed_pct=75.0,
        range_remaining_pct=25.0,
        expansion_state=ADRExpansionState.EXPANDING,
        exhaustion_state=ADRExhaustionState.NOT_EXHAUSTED,
        timestamp=NOW,
    )


def _vwap(*, trading_date=NOW.date()):
    return VWAPLevels(
        symbol=Instrument.NIFTY,
        trading_date=trading_date,
        timestamp=NOW,
        vwap=100.0,
        cumulative_volume=1000,
        cumulative_price_volume=100000.0,
    )
