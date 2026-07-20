from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core import events
from core.event_bus import EventBus
from engines.execution_reconciliation.enums import ReconciliationStatus
from engines.execution_reconciliation.models import ExecutionReconciliationReport
from engines.paper_execution_coordinator.enums import PaperExecutionStatus
from engines.position.enums import PositionStatus
from engines.shadow_trading_session import (
    ShadowSessionLifecycleState,
    ShadowSessionStatus,
    ShadowTradingSessionEngine,
    ShadowTradingSessionRequest,
    ShadowTradingSessionSnapshot,
    ShadowTradingSessionSummary,
)
from engines.trade_execution_policy.enums import ExecutionDecisionStatus, ExecutionPlanStatus
from engines.trade_execution_policy.engine import TradeExecutionPolicyEngine

sys.path.append(str(Path(__file__).parent))
from test_execution_reconciliation_engine_v1 import approved_plan, execute_entry, open_position, paper_request, request_for, runtime_parts


IST = ZoneInfo("Asia/Kolkata")
TS = datetime(2026, 7, 20, 9, 30, tzinfo=IST)


def request(session_id="shadow-1", instrument="NIFTY", at=TS):
    return ShadowTradingSessionRequest(session_id=session_id, started_at=at, instrument=instrument, correlation_id="corr-1", metadata=(("mode", "shadow"),))


def shadow_engine():
    bus, _, _, _, coordinator, reconciliation = runtime_parts()
    policy = TradeExecutionPolicyEngine(bus, instrument="NIFTY", timeframe="1m")
    return bus, ShadowTradingSessionEngine(
        bus,
        instrument="NIFTY",
        timeframe="1m",
        execution_policy_engine=policy,
        paper_execution_coordinator=coordinator,
        execution_reconciliation_engine=reconciliation,
        position_engine=reconciliation._position_engine,
    ), coordinator, reconciliation, policy


def running_shadow():
    bus, engine, coordinator, reconciliation, policy = shadow_engine()
    engine.start()
    engine.start_session(request())
    return bus, engine, coordinator, reconciliation, policy


def observe(engine, payload="payload", seconds=1):
    return engine.observe_market_event("market_event", payload, timestamp=TS + timedelta(seconds=seconds))


def test_request_model_is_immutable_validates_time_instrument_and_metadata():
    item = request()
    with pytest.raises(FrozenInstanceError):
        item.instrument = "BANKNIFTY"
    with pytest.raises(ValueError):
        request(at=datetime(2026, 7, 20, 9, 30))
    with pytest.raises(ValueError):
        request(instrument="MIDCPNIFTY")
    assert item.metadata == (("mode", "shadow"),)
    assert item.fingerprint() == request().fingerprint()


def test_summary_and_snapshot_models_are_immutable_and_safe():
    obs = ()
    summary = ShadowTradingSessionSummary(
        session_id="s",
        started_at=TS,
        ended_at=TS + timedelta(minutes=1),
        instrument="NIFTY",
        lifecycle_state=ShadowSessionLifecycleState.COMPLETED,
        session_status=ShadowSessionStatus.HEALTHY,
        primary_reason="done",
        market_event_count=0,
        execution_plan_count=0,
        approved_plan_count=0,
        rejected_plan_count=0,
        paper_receipt_count=0,
        paper_completed_count=0,
        paper_cancelled_count=0,
        paper_failed_count=0,
        reconciliation_report_count=0,
        consistent_reconciliation_count=0,
        warning_reconciliation_count=0,
        incomplete_reconciliation_count=0,
        inconsistent_reconciliation_count=0,
        invalid_reconciliation_count=0,
        failed_reconciliation_count=0,
        position_open_count=0,
        position_closed_count=0,
        observations=obs,
        latest_execution_plan_id=None,
        latest_execution_receipt_id=None,
        latest_reconciliation_report_id=None,
        latest_position_id=None,
    )
    snapshot = ShadowTradingSessionSnapshot(True, ShadowSessionLifecycleState.READY, None, summary, 1, 1, 0, 0, 0, 0, 0, 0, 0)
    with pytest.raises(FrozenInstanceError):
        summary.primary_reason = "x"
    with pytest.raises(FrozenInstanceError):
        snapshot.session_count = 2
    assert summary.broker_order_calls == snapshot.broker_order_calls == 0
    assert summary.live_order_submission_enabled is snapshot.live_order_submission_enabled is False


def test_lifecycle_start_duplicate_stop_retry_and_reset():
    bus, engine, _, _, _ = shadow_engine()
    completed = []
    bus.subscribe(events.SHADOW_SESSION_COMPLETED, lambda payload: completed.append(payload.session_id))
    assert engine.snapshot().lifecycle_state is ShadowSessionLifecycleState.CREATED
    assert engine.start().lifecycle_state is ShadowSessionLifecycleState.READY
    first = engine.start_session(request())
    assert first.lifecycle_state is ShadowSessionLifecycleState.RUNNING
    assert engine.start_session(request()).active_session_id == "shadow-1"
    summary = engine.stop_session(timestamp=TS + timedelta(minutes=1))
    assert summary.lifecycle_state is ShadowSessionLifecycleState.COMPLETED
    assert engine.snapshot().lifecycle_state is ShadowSessionLifecycleState.COMPLETED
    retry = engine.stop_session(timestamp=TS + timedelta(minutes=1))
    assert retry is summary
    assert completed == ["shadow-1"]
    assert engine.reset_session().lifecycle_state is ShadowSessionLifecycleState.READY


def test_processing_while_stopped_or_failed_performs_zero_reads():
    _, engine, _, _, _ = running_shadow()
    class Bad:
        @property
        def last_plan(self):
            raise AssertionError("read")
    engine.stop()
    engine._execution_policy_engine = Bad()
    assert observe(engine).lifecycle_state is ShadowSessionLifecycleState.STOPPED
    engine._state = ShadowSessionLifecycleState.FAILED
    assert observe(engine, seconds=2).lifecycle_state is ShadowSessionLifecycleState.FAILED


def test_start_session_from_stopped_raises_and_changes_no_counters():
    _, engine, _, _, _ = running_shadow()
    engine.stop()
    before = engine.snapshot()
    with pytest.raises(RuntimeError):
        engine.start_session(request(session_id="shadow-2"))
    after = engine.snapshot()
    assert after.lifecycle_state is ShadowSessionLifecycleState.STOPPED
    assert after.session_count == before.session_count
    assert after.completed_session_count == before.completed_session_count
    assert after.failed_session_count == before.failed_session_count
    assert after.market_event_count == before.market_event_count


def test_start_session_from_failed_raises_and_changes_no_counters():
    _, engine, _, _, _ = running_shadow()
    engine._state = ShadowSessionLifecycleState.FAILED
    before = engine.snapshot()
    with pytest.raises(RuntimeError):
        engine.start_session(request(session_id="shadow-2"))
    after = engine.snapshot()
    assert after.lifecycle_state is ShadowSessionLifecycleState.FAILED
    assert after.session_count == before.session_count
    assert after.completed_session_count == before.completed_session_count
    assert after.failed_session_count == before.failed_session_count
    assert after.market_event_count == before.market_event_count


def test_plan_receipt_report_and_position_identities_are_counted_once():
    _, engine, coordinator, reconciliation, policy = running_shadow()
    plan = approved_plan()
    policy._last_plan = plan
    receipt = coordinator.execute(paper_request(plan))
    report = reconciliation.reconcile(request_for(plan, receipt))
    assert report.reconciliation_status is ReconciliationStatus.CONSISTENT
    snapshot = observe(engine)
    assert snapshot.execution_plan_count == 1
    assert snapshot.paper_receipt_count == 1
    assert snapshot.reconciliation_report_count == 1
    assert snapshot.open_position_count == 0
    duplicate = observe(engine, "payload-2", seconds=2)
    assert duplicate.execution_plan_count == 1
    assert duplicate.paper_receipt_count == 1
    assert duplicate.reconciliation_report_count == 1
    assert len(engine._observations) == 1


def test_position_open_close_transition_creates_deterministic_observations():
    _, engine, _, reconciliation, _ = running_shadow()
    reconciliation._position_engine._state = open_position()
    first = observe(engine)
    assert first.open_position_count == 1
    first_observation = engine._observations[-1].observation_id
    reconciliation._position_engine._state = open_position(quantity=0, status=PositionStatus.CLOSED)
    second = observe(engine, "payload-2", seconds=2)
    assert second.closed_position_count == 1
    assert len(engine._observations) == 2
    assert engine._observations[-1].observation_id != first_observation


def test_no_new_identity_creates_no_observation_but_counts_unique_market_event():
    _, engine, _, _, _ = running_shadow()
    first = observe(engine)
    second = observe(engine, "payload-2", seconds=2)
    retry = observe(engine, "payload-2", seconds=2)
    assert first.market_event_count == 1
    assert second.market_event_count == 2
    assert retry.market_event_count == 2
    assert len(engine._observations) == 0


def test_cross_instrument_data_is_ignored_deterministically():
    _, engine, coordinator, reconciliation, policy = running_shadow()
    plan = replace(approved_plan(), instrument="BANKNIFTY", execution_plan_id="bank-plan")
    coordinator._last_receipt = None
    policy._last_plan = plan
    snapshot = observe(engine)
    assert snapshot.execution_plan_count == 0


def test_consistent_session_classifies_healthy():
    _, engine, coordinator, reconciliation, policy = running_shadow()
    plan = approved_plan()
    policy._last_plan = plan
    receipt = coordinator.execute(paper_request(plan))
    reconciliation.reconcile(request_for(plan, receipt))
    observe(engine)
    summary = engine.stop_session(timestamp=TS + timedelta(minutes=1))
    assert summary.session_status is ShadowSessionStatus.HEALTHY
    assert summary.consistent_reconciliation_count == 1


def test_warning_only_session_classifies_healthy_with_warnings():
    _, engine, coordinator, reconciliation, policy = running_shadow()
    plan = approved_plan()
    policy._last_plan = plan
    receipt = coordinator.execute(paper_request(plan))
    report = reconciliation.reconcile(request_for(plan, receipt))
    warning = replace(report, report_id="warning-report", reconciliation_status=ReconciliationStatus.CONSISTENT_WITH_WARNINGS)
    reconciliation._last_report = warning
    observe(engine)
    summary = engine.stop_session(timestamp=TS + timedelta(minutes=1))
    assert summary.session_status is ShadowSessionStatus.HEALTHY_WITH_WARNINGS


def test_rejected_plan_without_reconciliation_failure_is_blocked_not_failed():
    _, engine, _, reconciliation, policy = running_shadow()
    rejected = replace(
        approved_plan(),
        execution_plan_id="rejected-plan",
        status=ExecutionPlanStatus.REJECTED,
        decision_status=ExecutionDecisionStatus.REJECTED,
    )
    policy._last_plan = rejected
    observe(engine)
    summary = engine.stop_session(timestamp=TS + timedelta(minutes=1))
    assert summary.session_status is ShadowSessionStatus.BLOCKED
    assert engine.snapshot().lifecycle_state is ShadowSessionLifecycleState.COMPLETED


@pytest.mark.parametrize("status", [ReconciliationStatus.INCONSISTENT, ReconciliationStatus.INCOMPLETE, ReconciliationStatus.INVALID])
def test_reconciliation_problem_states_make_session_degraded_without_failed_lifecycle(status):
    _, engine, coordinator, reconciliation, policy = running_shadow()
    plan = approved_plan()
    policy._last_plan = plan
    receipt = coordinator.execute(paper_request(plan))
    report = reconciliation.reconcile(request_for(plan, receipt))
    reconciliation._last_report = replace(report, report_id=f"{status.value}-report", reconciliation_status=status)
    observe(engine)
    summary = engine.stop_session(timestamp=TS + timedelta(minutes=1))
    assert summary.session_status is ShadowSessionStatus.DEGRADED
    assert engine.snapshot().lifecycle_state is ShadowSessionLifecycleState.COMPLETED


def test_internal_exception_sets_failed_lifecycle_and_summary_status():
    bus, engine, _, _, _ = running_shadow()
    failed_events = []
    completed_events = []
    bus.subscribe(events.SHADOW_SESSION_FAILED, failed_events.append)
    bus.subscribe(events.SHADOW_SESSION_COMPLETED, completed_events.append)

    class Bad:
        @property
        def last_plan(self):
            raise RuntimeError("unexpected")

    engine._execution_policy_engine = Bad()
    snapshot = observe(engine)
    assert snapshot.lifecycle_state is ShadowSessionLifecycleState.FAILED
    assert snapshot.failed_session_count == 1
    assert snapshot.mutation_calls == 0
    assert snapshot.broker_order_calls == 0

    summary = engine.stop_session(timestamp=TS + timedelta(minutes=1))
    finalized = engine.snapshot()
    assert summary.session_status is ShadowSessionStatus.FAILED
    assert summary.lifecycle_state is ShadowSessionLifecycleState.FAILED
    assert finalized.lifecycle_state is ShadowSessionLifecycleState.FAILED
    assert finalized.failed_session_count == 1
    assert engine.get_summary("shadow-1") is summary
    assert failed_events == [snapshot, summary]
    assert completed_events == [summary]

    retry = engine.stop_session(timestamp=TS + timedelta(minutes=1))
    assert retry is summary
    assert engine.snapshot().failed_session_count == 1
    assert failed_events == [snapshot, summary]
    assert completed_events == [summary]


def test_reset_from_failed_returns_ready_and_allows_new_session():
    _, engine, _, _, _ = running_shadow()

    class Bad:
        @property
        def last_plan(self):
            raise RuntimeError("unexpected")

    engine._execution_policy_engine = Bad()
    observe(engine)
    assert engine.snapshot().lifecycle_state is ShadowSessionLifecycleState.FAILED
    reset = engine.reset_session()
    assert reset.lifecycle_state is ShadowSessionLifecycleState.READY
    engine._execution_policy_engine = shadow_engine()[4]
    started = engine.start_session(request(session_id="shadow-2"))
    assert started.lifecycle_state is ShadowSessionLifecycleState.RUNNING


def test_summary_identity_is_deterministic_and_lookup_is_read_only():
    _, engine, _, _, _ = running_shadow()
    summary = engine.stop_session(timestamp=TS + timedelta(minutes=1))
    assert summary.fingerprint() == engine.get_summary("shadow-1").fingerprint()
    assert engine.get_summary("missing") is None


def test_reset_clears_only_shadow_owned_state():
    _, engine, coordinator, reconciliation, policy = running_shadow()
    plan = approved_plan()
    policy._last_plan = plan
    receipt = coordinator.execute(paper_request(plan))
    reconciliation.reconcile(request_for(plan, receipt))
    observe(engine)
    engine.stop_session(timestamp=TS + timedelta(minutes=1))
    engine.reset_session()
    assert engine.snapshot().session_count == 0
    assert coordinator.last_receipt is receipt
    assert reconciliation.snapshot().last_report is not None


def test_runtime_and_orchestrator_expose_explicit_shadow_session_and_snapshot():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    app.start()
    request_item = request()
    app.start_shadow_session(RuntimeInstrument.NIFTY, request_item)
    snap = app.get_shadow_snapshot("NIFTY")
    assert snap.lifecycle_state is ShadowSessionLifecycleState.RUNNING
    app.observe_shadow_event("NIFTY", "manual_observe", object(), timestamp=TS + timedelta(seconds=1))
    summary = app.stop_shadow_session("NIFTY", timestamp=TS + timedelta(minutes=1))
    assert app.get_shadow_summary("NIFTY", "shadow-1") is summary
    runtime_snapshot = app.snapshot().runtime_snapshots[0]
    assert runtime_snapshot.shadow_trading_session.last_summary is summary


def test_process_tick_performs_at_most_one_shadow_observation_call():
    app = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    app.start()
    runtime = app.get_runtime(RuntimeInstrument.NIFTY)
    calls = []
    original = runtime.shadow_trading_session_engine.observe_market_event
    def wrapper(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)
    runtime.shadow_trading_session_engine.observe_market_event = wrapper
    from core.enums.exchange import Exchange
    from core.enums.instrument import Instrument
    from core.models.tick import Tick
    tick = Tick(Instrument.NIFTY, Exchange.NSE, TS, 100.0, 1, 99.5, 100.5, 0)
    runtime.shadow_trading_session_engine.start_session(request())
    app.process_tick(tick)
    assert calls == ["tick_processed"]


def test_read_only_spies_prove_no_downstream_mutation_or_evaluation_calls():
    _, engine, coordinator, reconciliation, policy = running_shadow()
    calls = {
        "evaluate": 0,
        "execute": 0,
        "reconcile": 0,
        "order_create": 0,
        "order_apply": 0,
        "paper_submit": 0,
        "paper_update": 0,
        "paper_cancel": 0,
        "position_fill": 0,
        "position_mark": 0,
    }
    def mark(name):
        def inner(*args, **kwargs):
            calls[name] += 1
            raise AssertionError(name)
        return inner
    policy.evaluate = mark("evaluate")
    coordinator.execute = mark("execute")
    reconciliation.reconcile = mark("reconcile")
    reconciliation._order_engine.create = mark("order_create")
    reconciliation._order_engine.apply = mark("order_apply")
    reconciliation._paper_engine.submit_managed_order = mark("paper_submit")
    reconciliation._paper_engine.update_managed_order = mark("paper_update")
    reconciliation._paper_engine.cancel_managed_order = mark("paper_cancel")
    reconciliation._position_engine.process_fill = mark("position_fill")
    reconciliation._position_engine.process_mark = mark("position_mark")
    snapshot = observe(engine)
    assert calls == {key: 0 for key in calls}
    assert snapshot.mutation_calls == 0
    assert snapshot.broker_order_calls == 0
    assert snapshot.live_order_submission_enabled is False


def test_no_second_event_bus_threads_async_sleep_autonomous_loop_or_broker_calls():
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("engines/shadow_trading_session").glob("*.py"))
    for forbidden in (
        "EventBus(",
        "threading",
        "asyncio",
        "time.sleep",
        ".evaluate(",
        ".execute(",
        ".reconcile(",
        ".create(",
        ".apply(",
        "submit_managed_order",
        "update_managed_order",
        "cancel_managed_order",
        "place_order",
        "modify_order",
        "cancel_order",
    ):
        assert forbidden not in text
