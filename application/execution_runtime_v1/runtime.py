"""
Execution Runtime V1.
"""

from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock

from application.execution_runtime_v1.configuration import ExecutionRuntimeV1Configuration
from application.execution_runtime_v1.enums import (
    ExecutionDecision,
    ExecutionIntentStatus,
    ExecutionRuntimeStatus,
)
from application.execution_runtime_v1.models import (
    ExecutionIntent,
    ExecutionResult,
    ExecutionRuntimeV1Snapshot,
    intent_from_risk,
)
from application.execution_runtime_v1.simulator import DryRunExecutionSimulator
from application.execution_runtime_v1.validator import ExecutionEligibilityValidator
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import (
    EXECUTION_DRY_RUN_ACKNOWLEDGED,
    EXECUTION_DRY_RUN_CANCELLED,
    EXECUTION_DRY_RUN_FILLED,
    EXECUTION_DRY_RUN_PARTIALLY_FILLED,
    EXECUTION_DRY_RUN_REJECTED,
    EXECUTION_DRY_RUN_SUBMITTED,
    EXECUTION_INTENT_CREATED,
    EXECUTION_RUNTIME_V1_UPDATED,
)
from engines.risk_management_v2.models import SUPPORTED_INSTRUMENTS, RiskManagementV2Snapshot


class ExecutionRuntimeV1:
    def __init__(
        self,
        *,
        instrument: Instrument,
        configuration: ExecutionRuntimeV1Configuration | None = None,
        validator: ExecutionEligibilityValidator | None = None,
        simulator: DryRunExecutionSimulator | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ):
        if instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        self.instrument = instrument
        self._configuration = configuration or ExecutionRuntimeV1Configuration()
        self._validator = validator or ExecutionEligibilityValidator()
        self._simulator = simulator or DryRunExecutionSimulator()
        self._event_bus = event_bus or EventBus()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._status = ExecutionRuntimeStatus.CREATED
        self._active_intent: ExecutionIntent | None = None
        self._last_result: ExecutionResult | None = None
        self._history: tuple[ExecutionResult, ...] = ()
        self._executed_cache: dict[RiskManagementV2Snapshot, ExecutionResult] = {}
        self._submitted_count = 0
        self._acknowledged_count = 0
        self._partial_fill_count = 0
        self._fill_count = 0
        self._cancel_count = 0
        self._reject_count = 0
        self._last_error: str | None = None

    def start(self) -> ExecutionRuntimeV1Snapshot:
        with self._lock:
            if self._status is not ExecutionRuntimeStatus.RUNNING:
                self._configuration = ExecutionRuntimeV1Configuration(
                    broker_mode=self._configuration.broker_mode,
                    safety_mode=self._configuration.safety_mode,
                    order_type=self._configuration.order_type,
                    fill_policy=self._configuration.fill_policy,
                    allow_partial_fill=self._configuration.allow_partial_fill,
                    require_manual_fill_confirmation=self._configuration.require_manual_fill_confirmation,
                    reject_zero_quantity=self._configuration.reject_zero_quantity,
                    require_risk_execution_eligibility=self._configuration.require_risk_execution_eligibility,
                    maximum_open_intents=self._configuration.maximum_open_intents,
                    history_limit=self._configuration.history_limit,
                )
                self._status = ExecutionRuntimeStatus.RUNNING
                self._last_error = None
            snapshot = self.snapshot()
        self._event_bus.publish(EXECUTION_RUNTIME_V1_UPDATED, snapshot)
        return snapshot

    def stop(self) -> ExecutionRuntimeV1Snapshot:
        with self._lock:
            if self._active_intent is not None:
                raise RuntimeError("cannot stop while an active execution intent remains open")
            if self._status is not ExecutionRuntimeStatus.STOPPED:
                self._status = ExecutionRuntimeStatus.STOPPED
            snapshot = self.snapshot()
        self._event_bus.publish(EXECUTION_RUNTIME_V1_UPDATED, snapshot)
        return snapshot

    def submit(self, risk: RiskManagementV2Snapshot) -> ExecutionResult:
        if not isinstance(risk, RiskManagementV2Snapshot):
            raise TypeError("risk must be RiskManagementV2Snapshot")
        with self._lock:
            if self._status is not ExecutionRuntimeStatus.RUNNING:
                raise RuntimeError("execution runtime must be running")
            if risk.instrument is not self.instrument:
                raise ValueError("risk instrument mismatch")
            if self._active_intent is not None:
                if self._active_intent.risk_snapshot == risk:
                    raise RuntimeError("duplicate active execution intent")
                raise RuntimeError("maximum open execution intents reached")
            cached = self._executed_cache.get(risk)
            if cached is not None:
                return cached
            decision, messages = self._validator.validate(risk, self._configuration)
            if decision is not ExecutionDecision.ACCEPTED:
                result = ExecutionResult(decision, None, (), 0, 0, 0, None, messages[0])
                self._last_result = result
                self._reject_count += 1 if decision is ExecutionDecision.REJECTED else 0
                self._append_history(result)
                snapshot = self.snapshot()
                self._event_bus.publish(EXECUTION_RUNTIME_V1_UPDATED, snapshot)
                self._event_bus.publish(EXECUTION_DRY_RUN_REJECTED, result)
                return result
            if self._configuration.maximum_open_intents <= 0:
                raise RuntimeError("maximum open execution intents reached")
            now = self._now()
            intent = intent_from_risk(risk, created_at=now, order_type=self._configuration.order_type)
            result = self._simulator.submit(intent, self._configuration, timestamp=now)
            self._active_intent = result.intent if result.remaining_quantity > 0 else None
            self._last_result = result
            self._submitted_count += 1
            self._acknowledged_count += 1
            if result.intent and result.intent.status is ExecutionIntentStatus.PARTIALLY_FILLED:
                self._partial_fill_count += 1
            if result.intent and result.intent.status is ExecutionIntentStatus.FILLED:
                self._fill_count += 1
            if self._active_intent is None:
                self._executed_cache[risk] = result
            self._append_history(result)
            snapshot = self.snapshot()
        self._publish_result_events(result, created=True)
        self._event_bus.publish(EXECUTION_RUNTIME_V1_UPDATED, snapshot)
        return result

    def confirm_fill(self, *, fill_quantity: int, fill_price: float) -> ExecutionResult:
        with self._lock:
            if self._active_intent is None or self._last_result is None:
                raise RuntimeError("no active execution intent")
            result = self._simulator.confirm_fill(
                self._active_intent,
                fill_quantity=fill_quantity,
                fill_price=fill_price,
                timestamp=self._now(),
                prior_result=self._last_result,
            )
            self._last_result = result
            if result.intent and result.intent.status is ExecutionIntentStatus.FILLED:
                self._fill_count += 1
                self._executed_cache[self._active_intent.risk_snapshot] = result
                self._active_intent = None
            else:
                self._partial_fill_count += 1
                self._active_intent = result.intent
            self._append_history(result)
            snapshot = self.snapshot()
        self._publish_result_events(result)
        self._event_bus.publish(EXECUTION_RUNTIME_V1_UPDATED, snapshot)
        return result

    def cancel_active(self) -> ExecutionResult:
        with self._lock:
            if self._active_intent is None or self._last_result is None:
                raise RuntimeError("no active execution intent")
            result = self._simulator.cancel(
                self._active_intent,
                timestamp=self._now(),
                prior_result=self._last_result,
            )
            self._last_result = result
            self._executed_cache[self._active_intent.risk_snapshot] = result
            self._active_intent = None
            self._cancel_count += 1
            self._append_history(result)
            snapshot = self.snapshot()
        self._event_bus.publish(EXECUTION_DRY_RUN_CANCELLED, result)
        self._event_bus.publish(EXECUTION_RUNTIME_V1_UPDATED, snapshot)
        return result

    def snapshot(self) -> ExecutionRuntimeV1Snapshot:
        return ExecutionRuntimeV1Snapshot(
            instrument=self.instrument,
            timestamp=self._now(),
            runtime_status=self._status,
            execution_decision=self._last_result.decision if self._last_result else ExecutionDecision.REJECTED,
            active_intent=self._active_intent,
            last_result=self._last_result,
            submitted_count=self._submitted_count,
            acknowledged_count=self._acknowledged_count,
            partial_fill_count=self._partial_fill_count,
            fill_count=self._fill_count,
            cancel_count=self._cancel_count,
            reject_count=self._reject_count,
            open_intent_count=1 if self._active_intent else 0,
            running=self._status is ExecutionRuntimeStatus.RUNNING,
            ready=self._status is ExecutionRuntimeStatus.RUNNING,
            history_size=len(self._history),
            last_error=self._last_error,
        )

    def history(self) -> tuple[ExecutionResult, ...]:
        return self._history

    def clear(self) -> ExecutionRuntimeV1Snapshot:
        with self._lock:
            if self._status is not ExecutionRuntimeStatus.STOPPED:
                raise RuntimeError("execution runtime must be stopped before clear")
            if self._active_intent is not None:
                raise RuntimeError("cannot clear while an active execution intent remains open")
            self._last_result = None
            self._history = ()
            self._executed_cache = {}
            self._submitted_count = 0
            self._acknowledged_count = 0
            self._partial_fill_count = 0
            self._fill_count = 0
            self._cancel_count = 0
            self._reject_count = 0
            self._last_error = None
            self._status = ExecutionRuntimeStatus.CLEARED
            snapshot = self.snapshot()
        self._event_bus.publish(EXECUTION_RUNTIME_V1_UPDATED, snapshot)
        return snapshot

    def _append_history(self, result: ExecutionResult) -> None:
        history = self._history + (result,)
        if len(history) > self._configuration.history_limit:
            history = history[-self._configuration.history_limit:]
        self._history = history

    def _publish_result_events(self, result: ExecutionResult, *, created: bool = False) -> None:
        if created:
            self._event_bus.publish(EXECUTION_INTENT_CREATED, result.intent)
            self._event_bus.publish(EXECUTION_DRY_RUN_SUBMITTED, result)
            self._event_bus.publish(EXECUTION_DRY_RUN_ACKNOWLEDGED, result)
        status = result.intent.status if result.intent else None
        if status is ExecutionIntentStatus.PARTIALLY_FILLED:
            self._event_bus.publish(EXECUTION_DRY_RUN_PARTIALLY_FILLED, result)
        if status is ExecutionIntentStatus.FILLED:
            self._event_bus.publish(EXECUTION_DRY_RUN_FILLED, result)

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value
