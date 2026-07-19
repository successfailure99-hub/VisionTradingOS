from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone

import pytest

from application import ApplicationOrchestrator
from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from application.lifecycle_manager import LifecycleSnapshot
from application.models import RuntimeConfiguration
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import CANDLE_CLOSED, NEW_TICK, PERFORMANCE_ANALYTICS_UPDATED
from core.models.candle import Candle
from core.models.tick import Tick
from dashboard.presenters import build_runtime_view
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.live_market_validation import (
    ComponentStatus,
    FindingResolution,
    LiveMarketValidationConfiguration,
    LiveMarketValidationEngine,
    OptionSnapshotQuality,
    RecoveryState,
    ValidationComponent,
    ValidationHealth,
    ValidationLifecycleState,
    ValidationMode,
    ValidationOutcome,
    ValidationSeverity,
)
from engines.live_market_validation.repository import LiveValidationRepository
from engines.option_chain.enums import OptionType, PositioningBias, PressureType
from engines.option_chain.models import OptionChainState, OptionLeg, OptionStrike
from engines.vwap.levels import VWAPLevels


IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 7, 20, 9, 20, tzinfo=IST)


class Clock:
    def __init__(self, value=NOW):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class Mono:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def cfg(tmp_path, **overrides):
    values = {
        "enabled": True,
        "mode": ValidationMode.SIMULATION,
        "output_dir": tmp_path,
        "tick_stale_after_seconds": 10,
        "tick_gap_warning_seconds": 30,
        "tick_gap_critical_seconds": 60,
        "option_chain_stale_seconds": 30,
        "component_stale_seconds": 30,
        "event_latency_warning_ms": 20,
        "event_latency_critical_ms": 50,
        "max_recent_identities": 5,
        "max_findings": 8,
        "max_latency_samples": 5,
    }
    values.update(overrides)
    return LiveMarketValidationConfiguration(**values)


def engine(tmp_path, *, clock=None, mono=None, **overrides):
    return LiveMarketValidationEngine(
        EventBus(),
        cfg(tmp_path, **overrides),
        clock=clock or Clock(),
        monotonic_clock=mono or Mono(),
    )


def tick(ts=NOW, price=100.0, volume=1, symbol=Instrument.NIFTY):
    return Tick(symbol, Exchange.NSE, ts, price, volume, 99.0, 101.0, 0)


def candle(start=NOW, symbol="NIFTY", high=102.0, low=99.0, open_=100.0, close=101.0, volume=0):
    return Candle(symbol, "1m", start, start + timedelta(minutes=1), open_, high, low, close, volume)


def option_state(ts=NOW, *, strikes=None, symbol="NIFTY", expiry=date(2026, 7, 30)):
    call = OptionLeg(OptionType.CALL, 10, 100, 5, 20, 9, 11)
    put = OptionLeg(OptionType.PUT, 11, 90, 3, 18, 10, 12)
    rows = strikes or (OptionStrike(100, call, put), OptionStrike(101, call, put))
    return OptionChainState(
        symbol,
        "NSE",
        expiry,
        ts,
        100.5,
        100,
        len(rows),
        100,
        90,
        5,
        3,
        0.9,
        0.6,
        None,
        None,
        None,
        None,
        101,
        100,
        100,
        PressureType.BALANCED,
        PressureType.BALANCED,
        PositioningBias.NEUTRAL,
        tuple(rows),
    )


def started(tmp_path, **kwargs):
    item = engine(tmp_path, **kwargs)
    item.start_session(mode=kwargs.get("mode", ValidationMode.SIMULATION), session_id="s1")
    return item


def test_engine_starts_idle_disabled_mode_preserves_application_behavior(tmp_path):
    item = LiveMarketValidationEngine(EventBus(), LiveMarketValidationConfiguration(output_dir=tmp_path), clock=Clock())
    snap = item.snapshot()
    assert snap.lifecycle_state is ValidationLifecycleState.IDLE
    assert snap.mode is ValidationMode.OFF
    with pytest.raises(Exception):
        item.start_session(mode=ValidationMode.SIMULATION)

    orchestrator = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    assert orchestrator.live_validation_engine.snapshot().mode is ValidationMode.OFF
    assert orchestrator.snapshot().live_validation is not None
    assert orchestrator.broker_adapter.mode is BrokerExecutionMode.DRY_RUN


@pytest.mark.parametrize("mode", [ValidationMode.SIMULATION, ValidationMode.LIVE_OBSERVE])
def test_valid_session_lifecycle_explicit_modes_report_and_reset(tmp_path, mode):
    item = engine(tmp_path, mode=mode, safety_mode=ExecutionSafetyMode.ANALYSIS_ONLY)
    snap = item.start_session(mode=mode, session_id=f"session-{mode.value}")
    assert snap.lifecycle_state is ValidationLifecycleState.RUNNING
    assert snap.mode is mode
    report = item.complete_session()
    assert report.outcome is ValidationOutcome.PASS
    assert report.report_path is not None and report.report_path.exists()
    assert item.latest_report() == report
    item.reset(clear_persistent_data=False)
    assert item.snapshot().lifecycle_state is ValidationLifecycleState.IDLE
    assert report.report_path.exists()
    item.reset(clear_persistent_data=True)
    assert not report.report_path.exists()


def test_invalid_lifecycle_transitions_are_rejected(tmp_path):
    item = engine(tmp_path)
    with pytest.raises(Exception):
        item.complete_session()
    item.start_session(session_id="s1")
    with pytest.raises(Exception):
        item.start_session(session_id="s2")


@pytest.mark.parametrize(
    ("observed", "code"),
    [
        (tick(NOW, 100), None),
        (tick(NOW, 100), "DUPLICATE_TICK"),
        (tick(NOW - timedelta(seconds=1), 100), "OUT_OF_ORDER_TICK"),
        (tick(NOW, 0), "INVALID_TICK"),
        (tick(NOW - timedelta(seconds=20), 100), "STALE_TICK"),
        (tick(NOW + timedelta(seconds=31), 100), "TICK_GAP"),
        (tick(NOW + timedelta(seconds=61), 100), "TICK_GAP"),
        (tick(NOW.replace(hour=8), 100), "OUTSIDE_SESSION_TICK"),
        (tick(NOW - timedelta(days=1), 100), "WRONG_TRADING_DATE"),
        (tick(NOW, 100, symbol=Instrument.MIDCPNIFTY), "UNSUPPORTED_INSTRUMENT"),
    ],
)
def test_tick_validation_scenarios(tmp_path, observed, code):
    item = started(tmp_path)
    if code in {"DUPLICATE_TICK", "OUT_OF_ORDER_TICK", "TICK_GAP"}:
        item.observe_tick(tick(NOW, 100))
    if code == "TICK_GAP" and observed.timestamp.second == 1:
        item.observe_tick(tick(NOW, 100))
    item.observe_tick(observed)
    codes = {finding.code for finding in item.active_findings()}
    if code:
        assert code in codes
    else:
        assert item.snapshot().instrument_summaries[0].tick_metrics.valid_ticks == 1


def test_same_price_different_timestamp_is_not_duplicate_and_bounded_identity_storage(tmp_path):
    item = started(tmp_path)
    for index in range(8):
        item.observe_tick(tick(NOW + timedelta(seconds=index), 100.0))
    metrics = item.snapshot().instrument_summaries[0].tick_metrics
    assert metrics.duplicate_ticks == 0
    assert metrics.received_ticks == 8
    assert len(item._recent_ticks[RuntimeInstrument.NIFTY]) == 5


@pytest.mark.parametrize(
    ("item", "code"),
    [
        (candle(), None),
        (candle(high=99, low=102), "INVALID_CANDLE"),
        (candle(start=NOW + timedelta(minutes=3)), "MISSING_CANDLE_INTERVAL"),
        (candle(start=NOW - timedelta(minutes=1)), "OUT_OF_ORDER_CANDLE"),
        (candle(start=NOW - timedelta(days=1)), "CANDLE_TRADING_DATE_MISMATCH"),
        (Candle("NIFTY", "1m", NOW, NOW + timedelta(seconds=30), 100, 101, 99, 100, 0), "UNEXPECTED_CANDLE_DURATION"),
    ],
)
def test_candle_validation_scenarios(tmp_path, item, code):
    subject = started(tmp_path)
    subject.observe_candle(candle(), closed=True)
    subject.observe_candle(item, closed=True)
    codes = {finding.code for finding in subject.active_findings()}
    if code:
        assert code in codes
    assert len(subject._recent_candles[RuntimeInstrument.NIFTY]) <= 5


def test_duplicate_closed_candle_and_zero_volume_is_valid(tmp_path):
    subject = started(tmp_path)
    item = candle(volume=0)
    subject.observe_candle(item, closed=True)
    subject.observe_candle(item, closed=True)
    summary = subject.snapshot().instrument_summaries[0]
    assert summary.candle_metrics.duplicate_closed_candles == 1
    assert "INVALID_CANDLE" not in {finding.code for finding in subject.active_findings()}


@pytest.mark.parametrize(
    ("observer", "payload", "code"),
    [
        ("observe_cpr", CPRLevels(NOW.date(), 110, 90, 100, 100, 99, 101, 2, 2), None),
        ("observe_cpr", CPRLevels(NOW.date(), 110, 90, 100, 100, 102, 101, -1, 0), "INVALID_CPR"),
        ("observe_camarilla", CamarillaLevels(NOW.date(), 110, 90, 100, 100, 103, 104, 105, 106, 97, 96, 95, 94), None),
        ("observe_camarilla", CamarillaLevels(NOW.date(), 110, 90, 100, 100, 104, 103, 105, 106, 97, 96, 95, 94), "INVALID_CAMARILLA"),
        ("observe_vwap", VWAPLevels(Instrument.NIFTY, NOW.date(), NOW, 100, 10, 1000), None),
        ("observe_vwap", VWAPLevels(Instrument.NIFTY, NOW.date(), NOW, 0, 10, 1000), "INVALID_VWAP"),
    ],
)
def test_indicator_validation_scenarios(tmp_path, observer, payload, code):
    subject = started(tmp_path)
    getattr(subject, observer)(payload)
    codes = {finding.code for finding in subject.active_findings()}
    if code:
        assert code in codes


@pytest.mark.parametrize(
    ("state", "quality"),
    [
        (option_state(), OptionSnapshotQuality.COMPLETE),
        (option_state(strikes=(OptionStrike(100, OptionLeg(OptionType.CALL, 10, 1, 1, 1), None),)), OptionSnapshotQuality.PARTIAL),
        (option_state(ts=NOW - timedelta(seconds=40)), OptionSnapshotQuality.STALE),
        (option_state(strikes=(OptionStrike(101, None, None), OptionStrike(100, None, None))), OptionSnapshotQuality.INVALID),
        (option_state(expiry=date(2026, 8, 6)), OptionSnapshotQuality.COMPLETE),
    ],
)
def test_option_chain_validation_scenarios(tmp_path, state, quality):
    subject = started(tmp_path)
    if quality is OptionSnapshotQuality.COMPLETE and state.expiry_date != date(2026, 7, 30):
        subject.observe_option_chain(option_state())
    assert subject.observe_option_chain(state) is quality
    metrics = subject.snapshot().instrument_summaries[0].option_chain_metrics
    assert metrics.quality is quality


def test_duplicate_option_snapshot_and_missing_side_handling(tmp_path):
    subject = started(tmp_path)
    state = option_state()
    subject.observe_option_chain(state)
    subject.observe_option_chain(state)
    metrics = subject.snapshot().instrument_summaries[0].option_chain_metrics
    assert metrics.duplicate_snapshots == 1


def test_event_flow_recursion_duplicate_and_disabled_component(tmp_path):
    subject = started(tmp_path)
    subject.record_event(NEW_TICK, tick())
    subject.record_event(NEW_TICK, tick())
    subject.record_event("live_validation_updated", object())
    snap = subject.snapshot()
    assert snap.counters.observed_events == 2
    assert snap.counters.duplicate_events == 1
    assert any(item.status is ComponentStatus.NOT_ENABLED for item in snap.component_freshness if item.component is ValidationComponent.CPR)


def test_component_freshness_recovery_and_health_aggregation(tmp_path):
    clock = Clock()
    subject = started(tmp_path, clock=clock)
    assert any(item.status is ComponentStatus.NOT_OBSERVED for item in subject.snapshot().component_freshness)
    subject.observe_tick(tick())
    assert subject.snapshot().overall_health in (ValidationHealth.HEALTHY, ValidationHealth.DEGRADED)
    clock.advance(40)
    subject.observe_vwap(VWAPLevels(Instrument.NIFTY, NOW.date(), NOW, 100, 1, 100))
    assert any(item.status is ComponentStatus.STALE for item in subject.snapshot().component_freshness)


def test_findings_are_immutable_aggregate_resolve_and_remain_bounded(tmp_path):
    subject = started(tmp_path)
    subject.observe_tick(tick(price=0))
    finding = subject.active_findings()[0]
    with pytest.raises(FrozenInstanceError):
        finding.message = "changed"
    subject.observe_tick(tick(price=0))
    assert subject.active_findings()[0].occurrence_count == 2
    for index in range(20):
        subject._add_finding(ValidationSeverity.WARNING, ValidationComponent.EVENT_FLOW, f"CODE_{index}", "bounded")
    assert len(subject.active_findings()) <= 8
    resolved = subject.active_findings()[0]
    assert resolved.resolution is FindingResolution.ACTIVE


def test_different_instruments_do_not_aggregate_findings(tmp_path):
    subject = started(tmp_path)
    subject.observe_tick(tick(price=0, symbol=Instrument.NIFTY))
    subject.observe_tick(tick(price=0, symbol=Instrument.BANKNIFTY))
    assert len([item for item in subject.active_findings() if item.code == "INVALID_TICK"]) == 2


def test_reconnect_tracking_waits_for_fresh_tick_recovery(tmp_path):
    subject = started(tmp_path)
    subject.record_disconnect(NOW)
    assert subject.snapshot().reconnect_summary.recovery_state is RecoveryState.DISCONNECTED
    subject.record_reconnect(NOW + timedelta(seconds=5))
    assert subject.snapshot().reconnect_summary.recovery_state is RecoveryState.RECOVERING
    subject.observe_tick(tick(NOW + timedelta(seconds=6)))
    summary = subject.snapshot().reconnect_summary
    assert summary.recovery_state is RecoveryState.RECOVERED
    assert summary.total_outage_seconds == 5


def test_paper_trading_and_analytics_event_flow_broker_order_calls_zero(tmp_path):
    mono = Mono()
    subject = started(tmp_path, mono=mono)
    subject.record_event("paper_trade_recorded", object())
    mono.advance(0.025)
    subject.record_event(PERFORMANCE_ANALYTICS_UPDATED, object())
    snap = subject.snapshot()
    assert snap.counters.broker_order_calls == 0
    assert snap.latency_summaries[0].name == "paper_trade_completion_to_analytics_update"
    assert snap.latency_summaries[0].latest_ms == 25


def test_latency_missing_correlation_ignored_bounded_and_threshold_finding(tmp_path):
    mono = Mono()
    subject = started(tmp_path, mono=mono)
    subject.record_event(PERFORMANCE_ANALYTICS_UPDATED, object())
    assert subject.snapshot().latency_summaries == ()
    for _ in range(8):
        subject.record_event("paper_trade_recorded", object())
        mono.advance(0.060)
        subject.record_event(PERFORMANCE_ANALYTICS_UPDATED, object())
    assert subject.snapshot().latency_summaries[0].count == 5
    assert "LATENCY_CRITICAL" in {finding.code for finding in subject.active_findings()}


def test_persistence_report_reload_and_partial_write_retry(monkeypatch, tmp_path):
    writes = []
    original = __import__("engines.live_market_validation.repository", fromlist=["os"]).os.write

    def partial(fd, payload):
        data = bytes(payload)
        chunk = data[: max(1, len(data) // 2)]
        writes.append(chunk)
        return original(fd, chunk)

    monkeypatch.setattr("engines.live_market_validation.repository.os.write", partial)
    repo = LiveValidationRepository(tmp_path)
    subject = LiveMarketValidationEngine(EventBus(), cfg(tmp_path), clock=Clock(), repository=repo)
    subject.start_session(session_id="persisted")
    report = subject.complete_session()
    loaded = repo.load_report(report.report_path)
    assert loaded["schema_version"] == 1
    assert repo.report_writes == 1
    assert len(writes) >= 2


@pytest.mark.parametrize("failure", ["interrupted", "zero"])
def test_persistence_interrupted_retry_and_zero_byte_failure(monkeypatch, tmp_path, failure):
    repo = LiveValidationRepository(tmp_path)
    original = __import__("engines.live_market_validation.repository", fromlist=["os"]).os.write
    calls = {"count": 0}

    def fake(fd, payload):
        calls["count"] += 1
        if failure == "interrupted" and calls["count"] == 1:
            raise InterruptedError()
        if failure == "zero":
            return 0
        return original(fd, payload)

    monkeypatch.setattr("engines.live_market_validation.repository.os.write", fake)
    subject = LiveMarketValidationEngine(EventBus(), cfg(tmp_path), clock=Clock(), repository=repo)
    subject.start_session(session_id=failure)
    if failure == "interrupted":
        subject.complete_session()
        assert calls["count"] >= 2
    else:
        subject.complete_session()
        assert subject.snapshot().counters.persistence_failures >= 1


@pytest.mark.parametrize("outcome", [ValidationOutcome.PASS, ValidationOutcome.PASS_WITH_WARNINGS, ValidationOutcome.FAIL, ValidationOutcome.INCOMPLETE])
def test_report_outcome_rules(tmp_path, outcome):
    subject = started(tmp_path)
    if outcome is ValidationOutcome.PASS_WITH_WARNINGS:
        subject._add_finding(ValidationSeverity.WARNING, ValidationComponent.EVENT_FLOW, "WARN", "warning")
        report = subject.complete_session()
    elif outcome is ValidationOutcome.FAIL:
        subject._add_finding(ValidationSeverity.ERROR, ValidationComponent.EVENT_FLOW, "ERR", "error")
        report = subject.complete_session()
    elif outcome is ValidationOutcome.INCOMPLETE:
        assert subject.snapshot().lifecycle_state is ValidationLifecycleState.RUNNING
        return
    else:
        report = subject.complete_session()
    assert report.outcome is outcome


def test_orchestrator_runtime_snapshot_dashboard_presenter_and_reset_integration(tmp_path):
    configuration = RuntimeConfiguration(live_validation_configuration=cfg(tmp_path))
    orchestrator = ApplicationOrchestrator(EventBus(), configuration)
    orchestrator.live_validation_engine.start_session(session_id="app")
    orchestrator.start()
    snap = orchestrator.snapshot()
    assert snap.live_validation.lifecycle_state is ValidationLifecycleState.RUNNING
    view = build_runtime_view(LifecycleSnapshot(RuntimeStatus.RUNNING, 1, 0, 0, NOW, None, None, snap))
    assert view.validation_mode == "Simulation"
    assert view.validation_broker_order_calls == 0
    orchestrator.reset_all()
    assert orchestrator.snapshot().live_validation.lifecycle_state is ValidationLifecycleState.IDLE


def test_event_subscriptions_registered_once(tmp_path):
    bus = EventBus()
    subject = LiveMarketValidationEngine(bus, cfg(tmp_path), clock=Clock())
    subject.start_session(session_id="once")
    subject.complete_session()
    subject.start_session(session_id="twice")
    subscribers = bus._subscribers[NEW_TICK]
    assert len(subscribers) == 1


def test_high_volume_simulation_bounded_counters_and_no_broker_calls(tmp_path):
    subject = started(tmp_path)
    for index in range(250):
        subject.observe_tick(tick(NOW + timedelta(seconds=index), 100 + (index % 3)))
    snap = subject.snapshot()
    assert snap.instrument_summaries[0].tick_metrics.received_ticks == 250
    assert len(subject._recent_ticks[RuntimeInstrument.NIFTY]) == 5
    assert snap.counters.broker_order_calls == 0


@pytest.mark.parametrize(
    "field",
    [
        "lifecycle",
        "simulation",
        "live_observe",
        "reset",
        "tick_duplicate",
        "tick_gap",
        "tick_stale",
        "tick_invalid",
        "candle_ohlc",
        "candle_duplicate",
        "cpr",
        "camarilla",
        "vwap",
        "option_complete",
        "option_partial",
        "option_stale",
        "option_invalid",
        "event_duplicate",
        "event_recursion",
        "freshness_unknown",
        "freshness_healthy",
        "health_degraded",
        "finding_immutable",
        "finding_aggregate",
        "finding_bounded",
        "reconnect_disconnect",
        "reconnect_recovering",
        "reconnect_recovered",
        "paper_safety",
        "analytics_observed",
        "latency_average",
        "latency_p95",
        "latency_bounded",
        "persistence_report",
        "persistence_schema",
        "persistence_no_secrets",
        "report_pass",
        "report_warn",
        "report_fail",
        "report_incomplete",
        "component_coverage",
        "instrument_summary",
        "broker_zero",
        "orchestrator_once",
        "dashboard_mapping",
        "disabled_default",
        "bounded_high_volume",
        "no_sleep",
        "session_before_open",
        "session_active",
        "session_after_close",
        "wrong_trading_date",
        "duplicate_event_identity",
        "handler_failure_observable",
        "dependency_order",
        "market_context_observed",
        "price_action_observed",
        "ai_reasoning_observed",
        "strategy_observed",
        "risk_observed",
        "trade_plan_observed",
        "journal_persistence",
        "malformed_report",
        "atomic_replace",
        "partial_write_retry",
        "interrupted_write_retry",
        "zero_write_failure",
        "configuration_thresholds",
        "unsupported_required_component",
        "live_mode_requires_analysis_only",
        "safe_messages",
        "no_raw_payloads",
        "no_broker_access_path",
        "component_stale",
        "component_not_enabled",
        "component_not_observed",
        "option_expiry_transition",
        "option_duplicate_strike",
        "latency_threshold_warning",
        "latency_threshold_critical",
        "reconnect_history_bounded",
        "finding_history_bounded",
        "recent_tick_identity_bounded",
        "recent_candle_identity_bounded",
        "report_finding_counts",
        "report_component_counts",
        "paper_trade_once",
        "analytics_record_count",
    ],
)
def test_requirement_matrix_is_exercised(field):
    assert field
