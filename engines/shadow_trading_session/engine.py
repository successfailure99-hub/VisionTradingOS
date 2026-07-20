"""
Shadow Trading Session Engine V1.
"""

from __future__ import annotations

from datetime import datetime

from core import events
from core.base_engine import BaseEngine
from engines.execution_reconciliation.enums import ReconciliationStatus
from engines.execution_reconciliation.models import ExecutionReconciliationReport
from engines.paper_execution_coordinator.enums import PaperExecutionStatus
from engines.paper_execution_coordinator.models import PaperExecutionReceipt
from engines.position.enums import PositionStatus
from engines.position.models import PositionState
from engines.trade_execution_policy.enums import ExecutionDecisionStatus, ExecutionPlanStatus
from engines.trade_execution_policy.models import TradeExecutionPlan

from .enums import ShadowSessionLifecycleState, ShadowSessionStatus
from .models import (
    ShadowSessionObservation,
    ShadowTradingSessionRequest,
    ShadowTradingSessionSnapshot,
    ShadowTradingSessionSummary,
    _aware,
    _instrument,
    _text,
    fingerprint_payload,
)


class ShadowTradingSessionEngine(BaseEngine):
    def __init__(
        self,
        event_bus,
        *,
        instrument: str,
        timeframe: str,
        execution_policy_engine,
        paper_execution_coordinator,
        execution_reconciliation_engine,
        position_engine,
        performance_analytics_engine=None,
        trading_journal_engine=None,
    ):
        super().__init__(event_bus)
        self._instrument = _instrument(instrument)
        self._timeframe = _text(timeframe, "timeframe")
        self._execution_policy_engine = execution_policy_engine
        self._paper_execution_coordinator = paper_execution_coordinator
        self._execution_reconciliation_engine = execution_reconciliation_engine
        self._position_engine = position_engine
        self._performance_analytics_engine = performance_analytics_engine
        self._trading_journal_engine = trading_journal_engine
        self._state = ShadowSessionLifecycleState.CREATED
        self._active_request: ShadowTradingSessionRequest | None = None
        self._summaries: dict[str, ShadowTradingSessionSummary] = {}
        self._last_summary: ShadowTradingSessionSummary | None = None
        self._observations: tuple[ShadowSessionObservation, ...] = ()
        self._seen_market_events: set[str] = set()
        self._seen_observations: set[str] = set()
        self._seen_plan_ids: set[str] = set()
        self._seen_receipt_ids: set[str] = set()
        self._seen_report_ids: set[str] = set()
        self._seen_position_fingerprints: set[str] = set()
        self._opened_position_ids: set[str] = set()
        self._closed_position_ids: set[str] = set()
        self._session_count = 0
        self._completed_session_count = 0
        self._failed_session_count = 0
        self._market_event_count = 0
        self._execution_plan_count = 0
        self._approved_plan_count = 0
        self._rejected_plan_count = 0
        self._paper_receipt_count = 0
        self._paper_completed_count = 0
        self._paper_cancelled_count = 0
        self._paper_failed_count = 0
        self._reconciliation_report_count = 0
        self._consistent_reconciliation_count = 0
        self._warning_reconciliation_count = 0
        self._incomplete_reconciliation_count = 0
        self._inconsistent_reconciliation_count = 0
        self._invalid_reconciliation_count = 0
        self._failed_reconciliation_count = 0
        self._position_open_count = 0
        self._position_closed_count = 0
        self._latest_execution_plan_id: str | None = None
        self._latest_execution_receipt_id: str | None = None
        self._latest_reconciliation_report_id: str | None = None
        self._latest_position_id: str | None = None
        self._completed_stop_keys: dict[str, ShadowTradingSessionSummary] = {}

    def start(self) -> ShadowTradingSessionSnapshot:
        if self._state is ShadowSessionLifecycleState.CREATED:
            self._state = ShadowSessionLifecycleState.READY
        self._publish_state()
        return self.snapshot()

    def stop(self) -> ShadowTradingSessionSnapshot:
        if self._state is not ShadowSessionLifecycleState.FAILED:
            self._state = ShadowSessionLifecycleState.STOPPED
        self._publish_state()
        return self.snapshot()

    def start_session(self, request: ShadowTradingSessionRequest) -> ShadowTradingSessionSnapshot:
        if not isinstance(request, ShadowTradingSessionRequest):
            raise TypeError("request must be ShadowTradingSessionRequest")
        if request.instrument != self._instrument:
            raise ValueError("Shadow session instrument does not match runtime instrument.")
        if self._state in {ShadowSessionLifecycleState.STOPPED, ShadowSessionLifecycleState.FAILED}:
            raise RuntimeError("Reset the shadow session before starting a new session.")
        if self._state is ShadowSessionLifecycleState.RUNNING:
            if self._active_request is not None and self._active_request.session_id == request.session_id:
                return self.snapshot()
            raise ValueError("A different shadow session is already running.")
        self._active_request = request
        self._reset_observed_state()
        self._state = ShadowSessionLifecycleState.RUNNING
        self._session_count += 1
        self._event_bus.publish(events.SHADOW_SESSION_STARTED, request)
        self._publish_state()
        return self.snapshot()

    def observe_market_event(self, event_name: str, payload, *, timestamp: datetime) -> ShadowTradingSessionSnapshot:
        event_name = _text(event_name, "event_name")
        if self._state is not ShadowSessionLifecycleState.RUNNING:
            return self.snapshot()
        timestamp = _aware(timestamp, "timestamp")
        key = fingerprint_payload(
            {
                "session": self._active_request.session_id if self._active_request is not None else None,
                "event_name": event_name,
                "timestamp": timestamp.isoformat(),
                "payload_identity": _payload_identity(payload),
            }
        )
        if key in self._seen_market_events:
            return self.snapshot()
        self._seen_market_events.add(key)
        try:
            plan = self._latest_plan()
            receipt = self._latest_receipt()
            report = self._latest_report()
            position = self._current_position()
            changed = self._record_identities(plan, receipt, report, position)
            self._market_event_count += 1
            if changed:
                observation = self._observation(timestamp, event_name, plan, receipt, report, position)
                if observation.observation_id not in self._seen_observations:
                    self._seen_observations.add(observation.observation_id)
                    self._observations = self._observations + (observation,)
                    self._event_bus.publish(events.SHADOW_SESSION_OBSERVATION_RECORDED, observation)
            self._publish_state()
        except Exception:
            self._state = ShadowSessionLifecycleState.FAILED
            self._failed_session_count += 1
            self._event_bus.publish(events.SHADOW_SESSION_FAILED, self.snapshot())
            self._publish_state()
        return self.snapshot()

    def stop_session(self, *, timestamp: datetime, reason: str = "session_completed") -> ShadowTradingSessionSummary:
        timestamp = _aware(timestamp, "timestamp")
        reason = _text(reason, "reason")
        if self._last_summary is not None and self._state in {
            ShadowSessionLifecycleState.COMPLETED,
            ShadowSessionLifecycleState.FAILED,
        }:
            return self._last_summary
        if self._active_request is None:
            if self._last_summary is not None:
                return self._last_summary
            raise RuntimeError("No active shadow session.")
        status = self._classify_status()
        primary_reason = "internal_failure" if status is ShadowSessionStatus.FAILED else reason
        lifecycle_state = (
            ShadowSessionLifecycleState.FAILED
            if status is ShadowSessionStatus.FAILED
            else ShadowSessionLifecycleState.COMPLETED
        )
        summary = self._summary(timestamp, status, primary_reason, lifecycle_state)
        self._summaries[summary.session_id] = summary
        self._last_summary = summary
        self._data = summary
        self._active_request = None
        self._state = lifecycle_state
        if status is ShadowSessionStatus.FAILED:
            self._event_bus.publish(events.SHADOW_SESSION_FAILED, summary)
        else:
            self._completed_session_count += 1
            if status is ShadowSessionStatus.DEGRADED:
                self._event_bus.publish(events.SHADOW_SESSION_DEGRADED, summary)
            elif status in {ShadowSessionStatus.HEALTHY_WITH_WARNINGS, ShadowSessionStatus.BLOCKED}:
                self._event_bus.publish(events.SHADOW_SESSION_WARNING, summary)
        self._event_bus.publish(events.SHADOW_SESSION_COMPLETED, summary)
        self._publish_state()
        return summary

    def get_summary(self, session_id: str) -> ShadowTradingSessionSummary | None:
        if not isinstance(session_id, str):
            return None
        return self._summaries.get(session_id.strip())

    def snapshot(self) -> ShadowTradingSessionSnapshot:
        return ShadowTradingSessionSnapshot(
            enabled=True,
            lifecycle_state=self._state,
            active_session_id=None if self._active_request is None else self._active_request.session_id,
            last_summary=self._last_summary,
            session_count=self._session_count,
            completed_session_count=self._completed_session_count,
            failed_session_count=self._failed_session_count,
            market_event_count=self._market_event_count,
            execution_plan_count=self._execution_plan_count,
            paper_receipt_count=self._paper_receipt_count,
            reconciliation_report_count=self._reconciliation_report_count,
            open_position_count=self._position_open_count,
            closed_position_count=self._position_closed_count,
            broker_order_calls=0,
            mutation_calls=0,
            live_order_submission_enabled=False,
        )

    def reset_session(self) -> ShadowTradingSessionSnapshot:
        if self._state is ShadowSessionLifecycleState.RUNNING:
            raise RuntimeError("Cannot reset a running shadow session.")
        self._active_request = None
        self._summaries = {}
        self._last_summary = None
        self._reset_observed_state()
        self._session_count = 0
        self._completed_session_count = 0
        self._failed_session_count = 0
        self._state = ShadowSessionLifecycleState.READY
        self._data = None
        self._publish_state()
        return self.snapshot()

    def _reset_observed_state(self) -> None:
        self._observations = ()
        self._seen_market_events = set()
        self._seen_observations = set()
        self._seen_plan_ids = set()
        self._seen_receipt_ids = set()
        self._seen_report_ids = set()
        self._seen_position_fingerprints = set()
        self._opened_position_ids = set()
        self._closed_position_ids = set()
        self._market_event_count = 0
        self._execution_plan_count = 0
        self._approved_plan_count = 0
        self._rejected_plan_count = 0
        self._paper_receipt_count = 0
        self._paper_completed_count = 0
        self._paper_cancelled_count = 0
        self._paper_failed_count = 0
        self._reconciliation_report_count = 0
        self._consistent_reconciliation_count = 0
        self._warning_reconciliation_count = 0
        self._incomplete_reconciliation_count = 0
        self._inconsistent_reconciliation_count = 0
        self._invalid_reconciliation_count = 0
        self._failed_reconciliation_count = 0
        self._position_open_count = 0
        self._position_closed_count = 0
        self._latest_execution_plan_id = None
        self._latest_execution_receipt_id = None
        self._latest_reconciliation_report_id = None
        self._latest_position_id = None

    def _latest_plan(self) -> TradeExecutionPlan | None:
        plan = self._execution_policy_engine.last_plan
        if plan is not None and (not isinstance(plan, TradeExecutionPlan) or plan.instrument != self._instrument):
            return None
        return plan

    def _latest_receipt(self) -> PaperExecutionReceipt | None:
        receipt = self._paper_execution_coordinator.last_receipt
        if receipt is not None and (not isinstance(receipt, PaperExecutionReceipt) or receipt.instrument != self._instrument):
            return None
        return receipt

    def _latest_report(self) -> ExecutionReconciliationReport | None:
        report = self._execution_reconciliation_engine.snapshot().last_report
        if report is not None and (not isinstance(report, ExecutionReconciliationReport) or report.instrument != self._instrument):
            return None
        return report

    def _current_position(self) -> PositionState | None:
        position = self._position_engine.state
        if position is not None and (not isinstance(position, PositionState) or position.symbol != self._instrument):
            return None
        return position

    def _record_identities(self, plan, receipt, report, position) -> bool:
        changed = False
        if plan is not None and plan.execution_plan_id not in self._seen_plan_ids:
            self._seen_plan_ids.add(plan.execution_plan_id)
            self._execution_plan_count += 1
            self._latest_execution_plan_id = plan.execution_plan_id
            if plan.status is ExecutionPlanStatus.READY_FOR_PAPER or plan.decision_status is ExecutionDecisionStatus.APPROVED:
                self._approved_plan_count += 1
            elif plan.decision_status in {ExecutionDecisionStatus.REJECTED, ExecutionDecisionStatus.LOCKED, ExecutionDecisionStatus.INVALID, ExecutionDecisionStatus.EXPIRED}:
                self._rejected_plan_count += 1
            changed = True
        if receipt is not None and receipt.receipt_id not in self._seen_receipt_ids:
            self._seen_receipt_ids.add(receipt.receipt_id)
            self._paper_receipt_count += 1
            self._latest_execution_receipt_id = receipt.receipt_id
            if receipt.status is PaperExecutionStatus.COMPLETED:
                self._paper_completed_count += 1
            elif receipt.status is PaperExecutionStatus.CANCELLED:
                self._paper_cancelled_count += 1
            elif receipt.status in {PaperExecutionStatus.FAILED, PaperExecutionStatus.REJECTED}:
                self._paper_failed_count += 1
            changed = True
        if report is not None and report.report_id not in self._seen_report_ids:
            self._seen_report_ids.add(report.report_id)
            self._reconciliation_report_count += 1
            self._latest_reconciliation_report_id = report.report_id
            if report.reconciliation_status is ReconciliationStatus.CONSISTENT:
                self._consistent_reconciliation_count += 1
            elif report.reconciliation_status is ReconciliationStatus.CONSISTENT_WITH_WARNINGS:
                self._warning_reconciliation_count += 1
            elif report.reconciliation_status is ReconciliationStatus.INCOMPLETE:
                self._incomplete_reconciliation_count += 1
            elif report.reconciliation_status is ReconciliationStatus.INCONSISTENT:
                self._inconsistent_reconciliation_count += 1
            elif report.reconciliation_status is ReconciliationStatus.INVALID:
                self._invalid_reconciliation_count += 1
            elif report.reconciliation_status is ReconciliationStatus.FAILED:
                self._failed_reconciliation_count += 1
            changed = True
        if position is not None:
            position_fp = _position_fingerprint(position)
            if position_fp not in self._seen_position_fingerprints:
                self._seen_position_fingerprints.add(position_fp)
                self._latest_position_id = _position_id(position)
                if position.status is PositionStatus.OPEN and self._latest_position_id not in self._opened_position_ids:
                    self._opened_position_ids.add(self._latest_position_id)
                    self._position_open_count += 1
                elif position.status is PositionStatus.CLOSED and self._latest_position_id not in self._closed_position_ids:
                    self._closed_position_ids.add(self._latest_position_id)
                    self._position_closed_count += 1
                changed = True
        return changed

    def _observation(self, timestamp, event_name, plan, receipt, report, position) -> ShadowSessionObservation:
        plan_id = None if plan is None else plan.execution_plan_id
        receipt_id = None if receipt is None else receipt.receipt_id
        report_id = None if report is None else report.report_id
        position_id = None if position is None else _position_id(position)
        status = self._classify_status().value
        reason = _reason(plan, receipt, report)
        observation_id = fingerprint_payload(
            {
                "session": self._active_request.session_id if self._active_request is not None else None,
                "timestamp": timestamp.isoformat(),
                "event": event_name,
                "plan": plan_id,
                "receipt": receipt_id,
                "report": report_id,
                "position": None if position is None else _position_fingerprint(position),
            }
        )
        correlation_id = self._active_request.correlation_id if self._active_request is not None else None
        return ShadowSessionObservation(
            observation_id=observation_id,
            timestamp=timestamp,
            instrument=self._instrument,
            event_name=event_name,
            execution_plan_id=plan_id,
            execution_receipt_id=receipt_id,
            reconciliation_report_id=report_id,
            position_id=position_id,
            status=status,
            reason=reason,
            correlation_id=correlation_id,
        )

    def _summary(self, ended_at, status, primary_reason, lifecycle_state) -> ShadowTradingSessionSummary:
        request = self._active_request
        return ShadowTradingSessionSummary(
            session_id=request.session_id,
            started_at=request.started_at,
            ended_at=ended_at,
            instrument=self._instrument,
            lifecycle_state=lifecycle_state,
            session_status=status,
            primary_reason=primary_reason,
            market_event_count=self._market_event_count,
            execution_plan_count=self._execution_plan_count,
            approved_plan_count=self._approved_plan_count,
            rejected_plan_count=self._rejected_plan_count,
            paper_receipt_count=self._paper_receipt_count,
            paper_completed_count=self._paper_completed_count,
            paper_cancelled_count=self._paper_cancelled_count,
            paper_failed_count=self._paper_failed_count,
            reconciliation_report_count=self._reconciliation_report_count,
            consistent_reconciliation_count=self._consistent_reconciliation_count,
            warning_reconciliation_count=self._warning_reconciliation_count,
            incomplete_reconciliation_count=self._incomplete_reconciliation_count,
            inconsistent_reconciliation_count=self._inconsistent_reconciliation_count,
            invalid_reconciliation_count=self._invalid_reconciliation_count,
            failed_reconciliation_count=self._failed_reconciliation_count,
            position_open_count=self._position_open_count,
            position_closed_count=self._position_closed_count,
            observations=self._observations,
            latest_execution_plan_id=self._latest_execution_plan_id,
            latest_execution_receipt_id=self._latest_execution_receipt_id,
            latest_reconciliation_report_id=self._latest_reconciliation_report_id,
            latest_position_id=self._latest_position_id,
            broker_order_calls=0,
            mutation_calls=0,
            live_order_submission_enabled=False,
            correlation_id=request.correlation_id,
        )

    def _classify_status(self) -> ShadowSessionStatus:
        if self._state is ShadowSessionLifecycleState.FAILED:
            return ShadowSessionStatus.FAILED
        if self._failed_reconciliation_count > 0 or self._invalid_reconciliation_count > 0 or self._inconsistent_reconciliation_count > 0 or self._incomplete_reconciliation_count > 0:
            return ShadowSessionStatus.DEGRADED
        if self._execution_plan_count > 0 and self._approved_plan_count == 0 and self._rejected_plan_count > 0:
            return ShadowSessionStatus.BLOCKED
        if self._warning_reconciliation_count > 0 or self._rejected_plan_count > 0 or self._paper_failed_count > 0:
            return ShadowSessionStatus.HEALTHY_WITH_WARNINGS
        return ShadowSessionStatus.HEALTHY

    def _publish_state(self) -> None:
        self._event_bus.publish(events.SHADOW_SESSION_STATE_UPDATED, self.snapshot())


def _payload_identity(payload) -> str:
    for name in ("event_id", "id", "request_id", "execution_plan_id", "receipt_id", "report_id"):
        value = getattr(payload, name, None)
        if isinstance(value, str) and value.strip():
            return f"{name}:{value.strip()}"
    return payload.__class__.__name__


def _position_id(position: PositionState) -> str:
    return f"{position.symbol}:{position.timeframe}"


def _position_fingerprint(position: PositionState) -> str:
    return fingerprint_payload(
        {
            "symbol": position.symbol,
            "timeframe": position.timeframe,
            "status": position.status.value,
            "side": position.side.value,
            "net": position.net_quantity,
            "abs": position.absolute_quantity,
            "version": position.version,
            "updated_at": position.updated_at.isoformat(),
        }
    )


def _reason(plan, receipt, report) -> str:
    if report is not None:
        return report.primary_reason.value
    if receipt is not None:
        return receipt.primary_reason.value
    if plan is not None:
        return plan.primary_reason.value
    return "observed"
