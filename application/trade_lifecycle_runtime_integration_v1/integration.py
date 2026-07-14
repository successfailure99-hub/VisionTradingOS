"""
Trade Lifecycle Runtime Integration V1.
"""

from datetime import datetime, timezone
from threading import RLock

from application.enums import ExecutionSafetyMode, RuntimeStatus
from application.lifecycle_manager import ApplicationLifecycleManager
from application.trade_lifecycle_runtime_integration_v1.configuration import TradeLifecycleRuntimeIntegrationV1Configuration
from application.trade_lifecycle_runtime_integration_v1.enums import (
    TradeLifecycleIntegrationChange,
    TradeLifecycleRoutingResult,
    TradeLifecycleRuntimeIntegrationStatus,
)
from application.trade_lifecycle_runtime_integration_v1.models import (
    TradeLifecycleInstrumentIntegrationSnapshot,
    TradeLifecyclePositionPriceRequest,
    TradeLifecycleRoutingRequest,
    TradeLifecycleRuntimeIntegrationV1Snapshot,
)
from application.trade_lifecycle_runtime_integration_v1.registry import TradeLifecycleCoordinatorRegistry
from application.trade_lifecycle_v1.enums import TradeLifecycleOutcome, TradeLifecycleStage
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import (
    TRADE_LIFECYCLE_CONTEXT_ROUTED,
    TRADE_LIFECYCLE_POSITION_PRICE_ROUTED,
    TRADE_LIFECYCLE_RUNTIME_INTEGRATION_ERROR,
    TRADE_LIFECYCLE_RUNTIME_INTEGRATION_V1_READY,
    TRADE_LIFECYCLE_RUNTIME_INTEGRATION_V1_UPDATED,
)


class TradeLifecycleRuntimeIntegrationV1:
    def __init__(
        self,
        *,
        application_lifecycle: ApplicationLifecycleManager,
        registry: TradeLifecycleCoordinatorRegistry,
        configuration: TradeLifecycleRuntimeIntegrationV1Configuration | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ):
        if not isinstance(application_lifecycle, ApplicationLifecycleManager):
            raise TypeError("application_lifecycle must be ApplicationLifecycleManager")
        if not isinstance(registry, TradeLifecycleCoordinatorRegistry):
            raise TypeError("registry must be TradeLifecycleCoordinatorRegistry")
        self._application_lifecycle = application_lifecycle
        self._registry = registry
        self._configuration = configuration or TradeLifecycleRuntimeIntegrationV1Configuration()
        self._event_bus = event_bus or EventBus()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._status = TradeLifecycleRuntimeIntegrationStatus.CREATED
        self._change = TradeLifecycleIntegrationChange.INITIAL
        self._instrument_state = {
            instrument: _MutableInstrumentState()
            for instrument in self._configuration.enabled_instruments
        }
        self._history: tuple[TradeLifecycleRuntimeIntegrationV1Snapshot, ...] = ()
        self._last_context_request: dict[Instrument, TradeLifecycleRoutingRequest] = {}
        self._last_context_snapshot: dict[Instrument, TradeLifecycleInstrumentIntegrationSnapshot] = {}
        self._last_price_request: dict[Instrument, TradeLifecyclePositionPriceRequest] = {}
        self._last_price_snapshot: dict[Instrument, TradeLifecycleInstrumentIntegrationSnapshot] = {}
        self._validation_count = 0
        self._start_count = 0
        self._stop_count = 0
        self._routing_count = 0
        self._duplicate_count = 0
        self._error_count = 0
        self._last_validated_at = None
        self._last_started_at = None
        self._last_stopped_at = None
        self._last_routed_at = None
        self._last_error = None

    @property
    def application_lifecycle(self):
        return self._application_lifecycle

    @property
    def registry(self) -> TradeLifecycleCoordinatorRegistry:
        return self._registry

    def validate(self) -> TradeLifecycleRuntimeIntegrationV1Snapshot:
        with self._lock:
            try:
                if self._configuration.require_application_running and self._application_lifecycle.status not in {RuntimeStatus.CREATED, RuntimeStatus.RUNNING, RuntimeStatus.STOPPED}:
                    raise RuntimeError("application lifecycle is not startable")
                app_snapshot = self._application_lifecycle.snapshot().orchestrator_snapshot
                if app_snapshot.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
                    raise ValueError("application safety mode must be ANALYSIS_ONLY")
                if app_snapshot.broker_mode is not BrokerExecutionMode.DRY_RUN:
                    raise ValueError("application broker mode must be DRY_RUN")
                if self._registry.instruments() != self._configuration.enabled_instruments:
                    raise ValueError("registry instruments must match configured instruments")
                seen = set()
                for instrument in self._configuration.enabled_instruments:
                    coordinator = self._registry.get(instrument)
                    if id(coordinator) in seen:
                        raise ValueError("coordinator owners must be unique")
                    seen.add(id(coordinator))
                    coordinator.validate()
                self._status = TradeLifecycleRuntimeIntegrationStatus.READY
                self._change = TradeLifecycleIntegrationChange.VALIDATED
                self._validation_count += 1
                self._last_validated_at = self._now()
                self._last_error = None
                snapshot = self._store_snapshot()
            except Exception as exc:
                self._status = TradeLifecycleRuntimeIntegrationStatus.ERROR
                self._change = TradeLifecycleIntegrationChange.BECAME_ERROR
                self._error_count += 1
                self._last_error = _safe_error(exc)
                raise
        self._event_bus.publish(TRADE_LIFECYCLE_RUNTIME_INTEGRATION_V1_READY, snapshot)
        return snapshot

    def start(self) -> TradeLifecycleRuntimeIntegrationV1Snapshot:
        with self._lock:
            if self._status is TradeLifecycleRuntimeIntegrationStatus.RUNNING:
                return self.snapshot()
            try:
                self.validate()
                if self._configuration.require_application_running and self._application_lifecycle.status is not RuntimeStatus.RUNNING:
                    raise RuntimeError("application lifecycle must be RUNNING")
                if self._configuration.auto_start_coordinators:
                    for coordinator in self._registry.coordinators():
                        coordinator.start()
                self._status = TradeLifecycleRuntimeIntegrationStatus.RUNNING
                self._change = TradeLifecycleIntegrationChange.STARTED
                self._start_count += 1
                self._last_started_at = self._now()
                self._last_error = None
                snapshot = self._store_snapshot()
            except Exception as exc:
                self._status = TradeLifecycleRuntimeIntegrationStatus.ERROR
                self._change = TradeLifecycleIntegrationChange.BECAME_ERROR
                self._error_count += 1
                self._last_error = _safe_error(exc)
                raise
        self._event_bus.publish(TRADE_LIFECYCLE_RUNTIME_INTEGRATION_V1_UPDATED, snapshot)
        return snapshot

    def stop(self) -> TradeLifecycleRuntimeIntegrationV1Snapshot:
        with self._lock:
            if self._status is TradeLifecycleRuntimeIntegrationStatus.STOPPED:
                return self.snapshot()
            for coordinator in reversed(self._registry.coordinators()):
                snapshot = coordinator.snapshot()
                if snapshot.execution_snapshot.open_intent_count or snapshot.position_snapshot.has_open_position:
                    raise RuntimeError("active execution or position blocks integration stop")
            for coordinator in reversed(self._registry.coordinators()):
                coordinator.stop()
            self._status = TradeLifecycleRuntimeIntegrationStatus.STOPPED
            self._change = TradeLifecycleIntegrationChange.STOPPED
            self._stop_count += 1
            self._last_stopped_at = self._now()
            snapshot = self._store_snapshot()
        self._event_bus.publish(TRADE_LIFECYCLE_RUNTIME_INTEGRATION_V1_UPDATED, snapshot)
        return snapshot

    def route_context(self, request: TradeLifecycleRoutingRequest) -> TradeLifecycleInstrumentIntegrationSnapshot:
        if not isinstance(request, TradeLifecycleRoutingRequest):
            raise TypeError("request must be TradeLifecycleRoutingRequest")
        with self._lock:
            self._require_running()
            if not self._configuration.route_context_updates:
                raise RuntimeError("context routing is disabled")
            if request.instrument not in self._configuration.enabled_instruments:
                raise ValueError("instrument is not configured")
            if self._configuration.reject_duplicate_context and self._last_context_request.get(request.instrument) == request:
                previous = self._last_context_snapshot[request.instrument]
                if previous.coordinator_snapshot.execution_result is not None or previous.coordinator_snapshot.position_result is not None:
                    raise RuntimeError("duplicate trade creation request")
                self._duplicate_count += 1
                self._instrument_state[request.instrument].duplicate_count += 1
                return previous
            coordinator = self._registry.get(request.instrument)
            lifecycle_snapshot = coordinator.process(request.lifecycle_request)
            routing_result = _routing_result(lifecycle_snapshot.stage, lifecycle_snapshot.outcome)
            instrument_snapshot = self._record_instrument(request.instrument, lifecycle_snapshot, routing_result, context=True)
            self._last_context_request[request.instrument] = request
            self._last_context_snapshot[request.instrument] = instrument_snapshot
            self._change = TradeLifecycleIntegrationChange.REQUEST_PROCESSED
            self._routing_count += 1
            self._last_routed_at = self._now()
            self._store_snapshot()
        self._event_bus.publish(TRADE_LIFECYCLE_CONTEXT_ROUTED, instrument_snapshot)
        self._event_bus.publish(TRADE_LIFECYCLE_RUNTIME_INTEGRATION_V1_UPDATED, self.snapshot())
        return instrument_snapshot

    def route_position_price(self, request: TradeLifecyclePositionPriceRequest) -> TradeLifecycleInstrumentIntegrationSnapshot:
        if not isinstance(request, TradeLifecyclePositionPriceRequest):
            raise TypeError("request must be TradeLifecyclePositionPriceRequest")
        with self._lock:
            self._require_running()
            if not self._configuration.route_position_price_updates:
                raise RuntimeError("position price routing is disabled")
            if request.instrument not in self._configuration.enabled_instruments:
                raise ValueError("instrument is not configured")
            if self._last_price_request.get(request.instrument) == request:
                return self._last_price_snapshot[request.instrument]
            coordinator = self._registry.get(request.instrument)
            lifecycle_snapshot = coordinator.update_position_price(request.update)
            instrument_snapshot = self._record_instrument(request.instrument, lifecycle_snapshot, TradeLifecycleRoutingResult.POSITION_UPDATED, price=True)
            self._last_price_request[request.instrument] = request
            self._last_price_snapshot[request.instrument] = instrument_snapshot
            self._change = TradeLifecycleIntegrationChange.POSITION_UPDATED
            self._routing_count += 1
            self._last_routed_at = self._now()
            self._store_snapshot()
        self._event_bus.publish(TRADE_LIFECYCLE_POSITION_PRICE_ROUTED, instrument_snapshot)
        self._event_bus.publish(TRADE_LIFECYCLE_RUNTIME_INTEGRATION_V1_UPDATED, self.snapshot())
        return instrument_snapshot

    def confirm_execution_fill(self, *, instrument: Instrument, fill_quantity: int, fill_price: float) -> TradeLifecycleInstrumentIntegrationSnapshot:
        with self._lock:
            self._require_running()
            coordinator = self._registry.get(instrument)
            lifecycle_snapshot = coordinator.confirm_execution_fill(fill_quantity=fill_quantity, fill_price=fill_price)
            instrument_snapshot = self._record_instrument(instrument, lifecycle_snapshot, TradeLifecycleRoutingResult.PROCESSED)
            self._routing_count += 1
            self._last_routed_at = self._now()
            self._store_snapshot()
            return instrument_snapshot

    def partial_exit_position(self, *, instrument: Instrument, quantity: int, exit_price: float) -> TradeLifecycleInstrumentIntegrationSnapshot:
        with self._lock:
            self._require_running()
            lifecycle_snapshot = self._registry.get(instrument).partial_exit_position(quantity=quantity, exit_price=exit_price)
            instrument_snapshot = self._record_instrument(instrument, lifecycle_snapshot, TradeLifecycleRoutingResult.POSITION_UPDATED, price=True)
            self._routing_count += 1
            self._last_routed_at = self._now()
            self._store_snapshot()
            return instrument_snapshot

    def close_position(self, *, instrument: Instrument, exit_price: float) -> TradeLifecycleInstrumentIntegrationSnapshot:
        with self._lock:
            self._require_running()
            lifecycle_snapshot = self._registry.get(instrument).close_position(exit_price=exit_price)
            instrument_snapshot = self._record_instrument(instrument, lifecycle_snapshot, TradeLifecycleRoutingResult.POSITION_UPDATED, price=True)
            self._change = TradeLifecycleIntegrationChange.POSITION_CLOSED
            self._routing_count += 1
            self._last_routed_at = self._now()
            self._store_snapshot()
            return instrument_snapshot

    def snapshot(self) -> TradeLifecycleRuntimeIntegrationV1Snapshot:
        app_status = self._application_lifecycle.status
        instruments = tuple(self._instrument_snapshot(instrument) for instrument in self._registry.instruments())
        return TradeLifecycleRuntimeIntegrationV1Snapshot(
            timestamp=self._now(),
            status=self._status,
            change=self._change,
            application_status=app_status,
            safety_mode=self._configuration.safety_mode,
            broker_mode=self._configuration.broker_mode,
            instruments=instruments,
            configured_instrument_count=len(self._configuration.enabled_instruments),
            ready_instrument_count=sum(1 for item in instruments if item.coordinator_snapshot.ready),
            running_instrument_count=sum(1 for item in instruments if item.coordinator_snapshot.running),
            active_execution_count=sum(item.coordinator_snapshot.execution_snapshot.open_intent_count for item in instruments),
            active_position_count=sum(1 for item in instruments if item.coordinator_snapshot.position_snapshot.has_open_position),
            validation_count=self._validation_count,
            start_count=self._start_count,
            stop_count=self._stop_count,
            routing_count=self._routing_count,
            duplicate_count=self._duplicate_count,
            error_count=self._error_count,
            running=self._status is TradeLifecycleRuntimeIntegrationStatus.RUNNING,
            ready=self._status in {TradeLifecycleRuntimeIntegrationStatus.READY, TradeLifecycleRuntimeIntegrationStatus.RUNNING},
            last_validated_at=self._last_validated_at,
            last_started_at=self._last_started_at,
            last_stopped_at=self._last_stopped_at,
            last_routed_at=self._last_routed_at,
            last_error=self._last_error,
        )

    def history(self) -> tuple[TradeLifecycleRuntimeIntegrationV1Snapshot, ...]:
        return self._history

    def clear(self) -> TradeLifecycleRuntimeIntegrationV1Snapshot:
        with self._lock:
            if self._status is not TradeLifecycleRuntimeIntegrationStatus.STOPPED:
                raise RuntimeError("integration must be stopped before clear")
            if self.snapshot().active_execution_count or self.snapshot().active_position_count:
                raise RuntimeError("cannot clear active execution or position state")
            self._status = TradeLifecycleRuntimeIntegrationStatus.CLEARED
            self._change = TradeLifecycleIntegrationChange.CLEARED
            self._history = ()
            self._routing_count = self._duplicate_count = self._error_count = 0
            snapshot = self.snapshot()
        self._event_bus.publish(TRADE_LIFECYCLE_RUNTIME_INTEGRATION_V1_UPDATED, snapshot)
        return snapshot

    def _record_instrument(self, instrument, lifecycle_snapshot, result, *, context=False, price=False):
        state = self._instrument_state[instrument]
        state.routing_count += 1
        if context:
            state.context_process_count += 1
        if price:
            state.price_update_count += 1
        if result is TradeLifecycleRoutingResult.BLOCKED:
            state.blocked_count += 1
        if result is TradeLifecycleRoutingResult.REJECTED:
            state.rejected_count += 1
        state.last_routed_at = self._now()
        state.last_routing_result = result
        state.last_snapshot = lifecycle_snapshot
        return self._instrument_snapshot(instrument)

    def _instrument_snapshot(self, instrument):
        state = self._instrument_state.setdefault(instrument, _MutableInstrumentState())
        lifecycle_snapshot = state.last_snapshot or self._registry.get(instrument).snapshot()
        return TradeLifecycleInstrumentIntegrationSnapshot(
            instrument=instrument,
            coordinator_snapshot=lifecycle_snapshot,
            routing_count=state.routing_count,
            context_process_count=state.context_process_count,
            price_update_count=state.price_update_count,
            duplicate_count=state.duplicate_count,
            blocked_count=state.blocked_count,
            rejected_count=state.rejected_count,
            error_count=state.error_count,
            last_routed_at=state.last_routed_at,
            last_routing_result=state.last_routing_result,
            last_error=state.last_error,
        )

    def _store_snapshot(self):
        snapshot = self.snapshot()
        history = self._history + (snapshot,)
        if len(history) > self._configuration.history_limit:
            history = history[-self._configuration.history_limit:]
        self._history = history
        return snapshot

    def _require_running(self):
        if self._status is not TradeLifecycleRuntimeIntegrationStatus.RUNNING:
            raise RuntimeError("trade lifecycle runtime integration must be running")
        if self._configuration.require_application_running and self._application_lifecycle.status is not RuntimeStatus.RUNNING:
            raise RuntimeError("application lifecycle must be RUNNING")

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value


class _MutableInstrumentState:
    def __init__(self):
        self.routing_count = 0
        self.context_process_count = 0
        self.price_update_count = 0
        self.duplicate_count = 0
        self.blocked_count = 0
        self.rejected_count = 0
        self.error_count = 0
        self.last_routed_at = None
        self.last_routing_result = None
        self.last_error = None
        self.last_snapshot = None


def _routing_result(stage, outcome):
    if outcome is TradeLifecycleOutcome.WAITING:
        return TradeLifecycleRoutingResult.WAITING
    if outcome is TradeLifecycleOutcome.BLOCKED:
        return TradeLifecycleRoutingResult.BLOCKED
    if outcome is TradeLifecycleOutcome.REJECTED:
        return TradeLifecycleRoutingResult.REJECTED
    if outcome is TradeLifecycleOutcome.INSUFFICIENT_DATA:
        return TradeLifecycleRoutingResult.INSUFFICIENT_DATA
    return TradeLifecycleRoutingResult.PROCESSED


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("token", "[redacted]").replace("credential", "[redacted]")
