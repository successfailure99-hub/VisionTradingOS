"""
Trade Journal Runtime Integration V1.
"""

from datetime import datetime, timezone
from threading import RLock

from application.enums import ExecutionSafetyMode
from application.trade_journal_runtime_integration_v1.configuration import TradeJournalRuntimeIntegrationV1Configuration
from application.trade_journal_runtime_integration_v1.enums import (
    TradeJournalIntegrationChange,
    TradeJournalRoutingResult,
    TradeJournalRuntimeIntegrationStatus,
)
from application.trade_journal_runtime_integration_v1.models import (
    TradeJournalInstrumentRoutingSnapshot,
    TradeJournalRoutingOutcome,
    TradeJournalRoutingRequest,
    TradeJournalRuntimeIntegrationV1Snapshot,
)
from application.trade_lifecycle_runtime_integration_v1 import TradeLifecycleRuntimeIntegrationV1
from application.trade_lifecycle_runtime_integration_v1.enums import TradeLifecycleRuntimeIntegrationStatus
from application.trade_lifecycle_v1.enums import TradeLifecycleOutcome, TradeLifecycleStage
from application.trade_lifecycle_v1.models import TradeLifecycleV1Snapshot
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import (
    TRADE_JOURNAL_DUPLICATE_SUPPRESSED,
    TRADE_JOURNAL_LIFECYCLE_ROUTED,
    TRADE_JOURNAL_RUNTIME_INTEGRATION_ERROR,
    TRADE_JOURNAL_RUNTIME_INTEGRATION_V1_READY,
    TRADE_JOURNAL_RUNTIME_INTEGRATION_V1_UPDATED,
    TRADE_JOURNAL_TRADE_RECORDED,
)
from engines.position_management_v1.enums import PositionStatus
from engines.trade_journal_v1 import TradeJournalV1Engine
from engines.trade_journal_v1.enums import TradeJournalStatus, TradeRecordStatus


class TradeJournalRuntimeIntegrationV1:
    def __init__(
        self,
        *,
        lifecycle_integration: TradeLifecycleRuntimeIntegrationV1,
        journal_engine: TradeJournalV1Engine,
        configuration: TradeJournalRuntimeIntegrationV1Configuration | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ):
        if not isinstance(lifecycle_integration, TradeLifecycleRuntimeIntegrationV1):
            raise TypeError("lifecycle_integration must be TradeLifecycleRuntimeIntegrationV1")
        if not isinstance(journal_engine, TradeJournalV1Engine):
            raise TypeError("journal_engine must be TradeJournalV1Engine")
        self._lifecycle_integration = lifecycle_integration
        self._journal_engine = journal_engine
        self._configuration = configuration or TradeJournalRuntimeIntegrationV1Configuration()
        self._event_bus = event_bus or EventBus()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._status = TradeJournalRuntimeIntegrationStatus.CREATED
        self._change = TradeJournalIntegrationChange.INITIAL
        self._instrument_state = {
            instrument: _MutableInstrumentRoutingState()
            for instrument in self._configuration.enabled_instruments
        }
        self._history: tuple[TradeJournalRuntimeIntegrationV1Snapshot, ...] = ()
        self._routing_count = 0
        self._recorded_count = 0
        self._duplicate_count = 0
        self._not_closed_count = 0
        self._rejected_count = 0
        self._error_count = 0
        self._validation_count = 0
        self._start_count = 0
        self._stop_count = 0
        self._last_validated_at = None
        self._last_started_at = None
        self._last_stopped_at = None
        self._last_routed_at = None
        self._last_error = None

    @property
    def lifecycle_integration(self) -> TradeLifecycleRuntimeIntegrationV1:
        return self._lifecycle_integration

    @property
    def journal_engine(self) -> TradeJournalV1Engine:
        return self._journal_engine

    def validate(self) -> TradeJournalRuntimeIntegrationV1Snapshot:
        with self._lock:
            try:
                lifecycle_snapshot = self._lifecycle_integration.snapshot()
                if lifecycle_snapshot.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
                    raise ValueError("lifecycle integration safety mode must be ANALYSIS_ONLY")
                if lifecycle_snapshot.broker_mode is not BrokerExecutionMode.DRY_RUN:
                    raise ValueError("lifecycle integration broker mode must be DRY_RUN")
                lifecycle_instruments = tuple(item.instrument for item in lifecycle_snapshot.instruments)
                if lifecycle_instruments and lifecycle_instruments != self._configuration.enabled_instruments:
                    raise ValueError("configured instruments must match lifecycle integration instruments")
                if self._journal_engine.snapshot().status is TradeJournalStatus.ERROR:
                    raise RuntimeError("journal engine is in ERROR state")
                self._status = TradeJournalRuntimeIntegrationStatus.READY
                self._change = TradeJournalIntegrationChange.VALIDATED
                self._validation_count += 1
                self._last_validated_at = self._now()
                self._last_error = None
                snapshot = self._store_snapshot()
            except Exception as exc:
                self._status = TradeJournalRuntimeIntegrationStatus.ERROR
                self._change = TradeJournalIntegrationChange.BECAME_ERROR
                self._error_count += 1
                self._last_error = _safe_error(exc)
                raise
        self._event_bus.publish(TRADE_JOURNAL_RUNTIME_INTEGRATION_V1_READY, snapshot)
        return snapshot

    def start(self) -> TradeJournalRuntimeIntegrationV1Snapshot:
        with self._lock:
            if self._status is TradeJournalRuntimeIntegrationStatus.RUNNING:
                return self.snapshot()
            try:
                self.validate()
                lifecycle_status = self._lifecycle_integration.snapshot().status
                if lifecycle_status is TradeLifecycleRuntimeIntegrationStatus.ERROR:
                    raise RuntimeError("lifecycle integration is in ERROR state")
                if self._configuration.auto_start_journal and not self._journal_engine.snapshot().running:
                    self._journal_engine.start()
                if not self._journal_engine.snapshot().ready:
                    raise RuntimeError("journal engine is not ready")
                self._status = TradeJournalRuntimeIntegrationStatus.RUNNING
                self._change = TradeJournalIntegrationChange.STARTED
                self._start_count += 1
                self._last_started_at = self._now()
                self._last_error = None
                snapshot = self._store_snapshot()
            except Exception as exc:
                self._status = TradeJournalRuntimeIntegrationStatus.ERROR
                self._change = TradeJournalIntegrationChange.BECAME_ERROR
                self._error_count += 1
                self._last_error = _safe_error(exc)
                self._event_bus.publish(TRADE_JOURNAL_RUNTIME_INTEGRATION_ERROR, self.snapshot())
                raise
        self._event_bus.publish(TRADE_JOURNAL_RUNTIME_INTEGRATION_V1_UPDATED, snapshot)
        return snapshot

    def stop(self) -> TradeJournalRuntimeIntegrationV1Snapshot:
        with self._lock:
            if self._status is TradeJournalRuntimeIntegrationStatus.STOPPED:
                return self.snapshot()
            if self._journal_engine.snapshot().running:
                self._journal_engine.stop()
            self._status = TradeJournalRuntimeIntegrationStatus.STOPPED
            self._change = TradeJournalIntegrationChange.STOPPED
            self._stop_count += 1
            self._last_stopped_at = self._now()
            snapshot = self._store_snapshot()
        self._event_bus.publish(TRADE_JOURNAL_RUNTIME_INTEGRATION_V1_UPDATED, snapshot)
        return snapshot

    def route_lifecycle(self, request: TradeJournalRoutingRequest) -> TradeJournalRoutingOutcome:
        if not isinstance(request, TradeJournalRoutingRequest):
            raise TypeError("request must be TradeJournalRoutingRequest")
        with self._lock:
            if self._status is not TradeJournalRuntimeIntegrationStatus.RUNNING:
                raise RuntimeError("trade journal runtime integration must be RUNNING")
            if not self._configuration.auto_record_closed_positions:
                raise RuntimeError("automatic journal routing is disabled")
            if request.instrument not in self._configuration.enabled_instruments:
                raise ValueError("instrument is not configured")
            try:
                eligibility = self._eligibility_result(request.lifecycle_snapshot)
                if eligibility is not None:
                    result, message = eligibility
                    outcome = self._make_outcome(request, result, None, message)
                else:
                    journal_result = self._journal_engine.record(request.lifecycle_snapshot)
                    result = _map_journal_result(journal_result.status)
                    outcome = self._make_outcome(request, result, journal_result, journal_result.message)
                self._record_outcome(outcome)
                snapshot = self._store_snapshot()
            except Exception as exc:
                self._status = TradeJournalRuntimeIntegrationStatus.ERROR
                self._change = TradeJournalIntegrationChange.BECAME_ERROR
                self._error_count += 1
                self._last_error = _safe_error(exc)
                state = self._instrument_state.setdefault(request.instrument, _MutableInstrumentRoutingState())
                state.error_count += 1
                state.last_error = self._last_error
                self._store_snapshot()
                self._event_bus.publish(TRADE_JOURNAL_RUNTIME_INTEGRATION_ERROR, self.snapshot())
                raise
        self._publish_outcome(outcome, snapshot)
        return outcome

    def route_if_closed(self, lifecycle_snapshot: TradeLifecycleV1Snapshot) -> TradeJournalRoutingOutcome:
        if not isinstance(lifecycle_snapshot, TradeLifecycleV1Snapshot):
            raise TypeError("lifecycle_snapshot must be TradeLifecycleV1Snapshot")
        return self.route_lifecycle(
            TradeJournalRoutingRequest(
                instrument=lifecycle_snapshot.instrument,
                lifecycle_snapshot=lifecycle_snapshot,
            )
        )

    def snapshot(self) -> TradeJournalRuntimeIntegrationV1Snapshot:
        journal_snapshot = self._journal_engine.snapshot()
        analytics_snapshot = self._journal_engine.analytics_snapshot()
        instruments = tuple(self._instrument_snapshot(instrument) for instrument in self._configuration.enabled_instruments)
        return TradeJournalRuntimeIntegrationV1Snapshot(
            timestamp=self._now(),
            status=self._status,
            change=self._change,
            safety_mode=self._configuration.safety_mode,
            broker_mode=self._configuration.broker_mode,
            journal_snapshot=journal_snapshot,
            analytics_snapshot=analytics_snapshot,
            instruments=instruments,
            routing_count=self._routing_count,
            recorded_count=self._recorded_count,
            duplicate_count=self._duplicate_count,
            not_closed_count=self._not_closed_count,
            rejected_count=self._rejected_count,
            error_count=self._error_count,
            validation_count=self._validation_count,
            start_count=self._start_count,
            stop_count=self._stop_count,
            running=self._status is TradeJournalRuntimeIntegrationStatus.RUNNING,
            ready=self._status in {TradeJournalRuntimeIntegrationStatus.READY, TradeJournalRuntimeIntegrationStatus.RUNNING},
            last_validated_at=self._last_validated_at,
            last_started_at=self._last_started_at,
            last_stopped_at=self._last_stopped_at,
            last_routed_at=self._last_routed_at,
            last_error=self._last_error,
        )

    def history(self) -> tuple[TradeJournalRuntimeIntegrationV1Snapshot, ...]:
        return self._history

    def clear(self) -> TradeJournalRuntimeIntegrationV1Snapshot:
        with self._lock:
            if self._status is TradeJournalRuntimeIntegrationStatus.CLEARED:
                return self.snapshot()
            if self._status is not TradeJournalRuntimeIntegrationStatus.STOPPED:
                raise RuntimeError("integration must be stopped before clear")
            if self._journal_engine.snapshot().status is TradeJournalStatus.STOPPED:
                self._journal_engine.clear()
            self._instrument_state = {
                instrument: _MutableInstrumentRoutingState()
                for instrument in self._configuration.enabled_instruments
            }
            self._history = ()
            self._routing_count = self._recorded_count = self._duplicate_count = 0
            self._not_closed_count = self._rejected_count = self._error_count = 0
            self._last_error = None
            self._status = TradeJournalRuntimeIntegrationStatus.CLEARED
            self._change = TradeJournalIntegrationChange.CLEARED
            snapshot = self.snapshot()
        self._event_bus.publish(TRADE_JOURNAL_RUNTIME_INTEGRATION_V1_UPDATED, snapshot)
        return snapshot

    def _eligibility_result(self, lifecycle: TradeLifecycleV1Snapshot):
        if self._configuration.require_position_closed_stage and lifecycle.stage is not TradeLifecycleStage.POSITION_CLOSED:
            return TradeJournalRoutingResult.NOT_CLOSED, "Lifecycle has not reached POSITION_CLOSED stage."
        if self._configuration.require_position_closed_outcome and lifecycle.outcome is not TradeLifecycleOutcome.POSITION_CLOSED:
            return TradeJournalRoutingResult.NOT_CLOSED, "Lifecycle outcome is not POSITION_CLOSED."
        required = (
            lifecycle.position_result,
            lifecycle.execution_result,
            lifecycle.risk_decision,
            lifecycle.strategy_decision,
        )
        if any(value is None for value in required):
            return TradeJournalRoutingResult.REJECTED, "Lifecycle is missing required journal data."
        position = lifecycle.position_result.position
        if position is None:
            return TradeJournalRoutingResult.REJECTED, "Lifecycle has no position."
        if position.open_quantity != 0:
            return TradeJournalRoutingResult.NOT_CLOSED, "Position is not fully closed."
        if position.status not in {PositionStatus.CLOSED, PositionStatus.INVALIDATED}:
            return TradeJournalRoutingResult.NOT_CLOSED, "Position status is not closed or invalidated."
        return None

    def _make_outcome(self, request, result, journal_result, message):
        return TradeJournalRoutingOutcome(
            instrument=request.instrument,
            result=result,
            lifecycle_snapshot=request.lifecycle_snapshot,
            journal_result=journal_result,
            routed_at=self._now(),
            message=message,
        )

    def _record_outcome(self, outcome):
        state = self._instrument_state[outcome.instrument]
        state.routed_count += 1
        self._routing_count += 1
        if outcome.result is TradeJournalRoutingResult.RECORDED:
            state.recorded_count += 1
            self._recorded_count += 1
            self._change = TradeJournalIntegrationChange.TRADE_RECORDED
        elif outcome.result is TradeJournalRoutingResult.DUPLICATE:
            state.duplicate_count += 1
            self._duplicate_count += 1
            self._change = TradeJournalIntegrationChange.DUPLICATE_SUPPRESSED
        elif outcome.result is TradeJournalRoutingResult.NOT_CLOSED:
            state.not_closed_count += 1
            self._not_closed_count += 1
            self._change = TradeJournalIntegrationChange.UNCHANGED
        else:
            state.rejected_count += 1
            self._rejected_count += 1
            self._change = TradeJournalIntegrationChange.TRADE_REJECTED
        state.last_outcome = outcome
        state.last_routed_at = outcome.routed_at
        state.last_error = None
        self._last_routed_at = outcome.routed_at
        self._last_error = None

    def _instrument_snapshot(self, instrument):
        state = self._instrument_state[instrument]
        return TradeJournalInstrumentRoutingSnapshot(
            instrument=instrument,
            routed_count=state.routed_count,
            recorded_count=state.recorded_count,
            duplicate_count=state.duplicate_count,
            not_closed_count=state.not_closed_count,
            rejected_count=state.rejected_count,
            error_count=state.error_count,
            last_outcome=state.last_outcome,
            last_routed_at=state.last_routed_at,
            last_error=state.last_error,
        )

    def _store_snapshot(self):
        snapshot = self.snapshot()
        history = self._history + (snapshot,)
        if len(history) > self._configuration.history_limit:
            history = history[-self._configuration.history_limit:]
        self._history = history
        return snapshot

    def _publish_outcome(self, outcome, snapshot):
        self._event_bus.publish(TRADE_JOURNAL_LIFECYCLE_ROUTED, outcome)
        if outcome.result is TradeJournalRoutingResult.RECORDED:
            self._event_bus.publish(TRADE_JOURNAL_TRADE_RECORDED, outcome)
        elif outcome.result is TradeJournalRoutingResult.DUPLICATE:
            self._event_bus.publish(TRADE_JOURNAL_DUPLICATE_SUPPRESSED, outcome)
        self._event_bus.publish(TRADE_JOURNAL_RUNTIME_INTEGRATION_V1_UPDATED, snapshot)

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value


class _MutableInstrumentRoutingState:
    def __init__(self):
        self.routed_count = 0
        self.recorded_count = 0
        self.duplicate_count = 0
        self.not_closed_count = 0
        self.rejected_count = 0
        self.error_count = 0
        self.last_outcome = None
        self.last_routed_at = None
        self.last_error = None


def _map_journal_result(status):
    if status is TradeRecordStatus.RECORDED:
        return TradeJournalRoutingResult.RECORDED
    if status is TradeRecordStatus.DUPLICATE:
        return TradeJournalRoutingResult.DUPLICATE
    if status is TradeRecordStatus.REJECTED:
        return TradeJournalRoutingResult.REJECTED
    return TradeJournalRoutingResult.ERROR


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("token", "[redacted]").replace("credential", "[redacted]")
