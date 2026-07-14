"""
Trade Lifecycle Coordinator V1.
"""

from datetime import datetime, timezone
from threading import RLock

from application.execution_runtime_v1 import ExecutionRuntimeV1
from application.execution_runtime_v1.enums import ExecutionDecision, ExecutionIntentStatus
from application.trade_lifecycle_v1.configuration import TradeLifecycleV1Configuration
from application.trade_lifecycle_v1.enums import (
    TradeLifecycleBlockSource,
    TradeLifecycleChange,
    TradeLifecycleOutcome,
    TradeLifecycleStage,
    TradeLifecycleStatus,
)
from application.trade_lifecycle_v1.models import TradeLifecycleStageRecord, TradeLifecycleV1Request, TradeLifecycleV1Snapshot
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import (
    TRADE_LIFECYCLE_BLOCKED,
    TRADE_LIFECYCLE_POSITION_CLOSED,
    TRADE_LIFECYCLE_POSITION_OPENED,
    TRADE_LIFECYCLE_STAGE_CHANGED,
    TRADE_LIFECYCLE_V1_READY,
    TRADE_LIFECYCLE_V1_UPDATED,
)
from engines.ai_reasoning_v2 import AIReasoningV2Engine
from engines.market_context_v2.models import SUPPORTED_INSTRUMENTS
from engines.position_management_v1 import PositionChange, PositionDecision, PositionExitReason, PositionManagementV1Engine, PositionPriceUpdate
from engines.risk_management_v2 import RiskDecision, RiskManagementV2Engine, RiskManagementV2Input
from engines.strategy_decision_v2 import StrategyAction, StrategyDecisionV2Engine, StrategyDecisionV2Input


class TradeLifecycleCoordinatorV1:
    def __init__(
        self,
        *,
        instrument: Instrument,
        ai_reasoning_engine: AIReasoningV2Engine,
        strategy_engine: StrategyDecisionV2Engine,
        risk_engine: RiskManagementV2Engine,
        execution_runtime: ExecutionRuntimeV1,
        position_engine: PositionManagementV1Engine,
        configuration: TradeLifecycleV1Configuration | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ):
        if instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if not isinstance(ai_reasoning_engine, AIReasoningV2Engine):
            raise TypeError("ai_reasoning_engine must be AIReasoningV2Engine")
        if not isinstance(strategy_engine, StrategyDecisionV2Engine):
            raise TypeError("strategy_engine must be StrategyDecisionV2Engine")
        if not isinstance(risk_engine, RiskManagementV2Engine):
            raise TypeError("risk_engine must be RiskManagementV2Engine")
        if not isinstance(execution_runtime, ExecutionRuntimeV1):
            raise TypeError("execution_runtime must be ExecutionRuntimeV1")
        if not isinstance(position_engine, PositionManagementV1Engine):
            raise TypeError("position_engine must be PositionManagementV1Engine")
        for dependency in (ai_reasoning_engine, strategy_engine, risk_engine, execution_runtime, position_engine):
            if dependency.instrument is not instrument:
                raise ValueError("all trade lifecycle dependencies must use the same instrument")
        self.instrument = instrument
        self._ai_reasoning_engine = ai_reasoning_engine
        self._strategy_engine = strategy_engine
        self._risk_engine = risk_engine
        self._execution_runtime = execution_runtime
        self._position_engine = position_engine
        self._configuration = configuration or TradeLifecycleV1Configuration()
        self._event_bus = event_bus or EventBus()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._status = TradeLifecycleStatus.CREATED
        self._stage = TradeLifecycleStage.IDLE
        self._outcome = TradeLifecycleOutcome.IN_PROGRESS
        self._change = TradeLifecycleChange.INITIAL
        self._block_source = TradeLifecycleBlockSource.NONE
        self._market_context = None
        self._ai_reasoning = None
        self._strategy_decision = None
        self._risk_decision = None
        self._execution_result = None
        self._position_result = None
        self._stage_records: tuple[TradeLifecycleStageRecord, ...] = ()
        self._history: tuple[TradeLifecycleV1Snapshot, ...] = ()
        self._last_request: TradeLifecycleV1Request | None = None
        self._last_request_snapshot: TradeLifecycleV1Snapshot | None = None
        self._last_position_update: PositionPriceUpdate | None = None
        self._processing_count = 0
        self._waiting_count = 0
        self._blocked_count = 0
        self._rejected_count = 0
        self._execution_count = 0
        self._position_open_count = 0
        self._position_close_count = 0
        self._last_started_at = None
        self._last_stopped_at = None
        self._last_processed_at = None
        self._last_error = None

    @property
    def ai_reasoning_engine(self) -> AIReasoningV2Engine:
        return self._ai_reasoning_engine

    @property
    def strategy_engine(self) -> StrategyDecisionV2Engine:
        return self._strategy_engine

    @property
    def risk_engine(self) -> RiskManagementV2Engine:
        return self._risk_engine

    @property
    def execution_runtime(self) -> ExecutionRuntimeV1:
        return self._execution_runtime

    @property
    def position_engine(self) -> PositionManagementV1Engine:
        return self._position_engine

    def validate(self) -> TradeLifecycleV1Snapshot:
        with self._lock:
            try:
                if self._configuration.require_no_active_position_before_new_trade and self._position_engine.snapshot().has_open_position:
                    raise RuntimeError("active position blocks new trade lifecycle")
                self._status = TradeLifecycleStatus.READY
                self._last_error = None
                snapshot = self.snapshot()
            except Exception as exc:
                self._status = TradeLifecycleStatus.ERROR
                self._last_error = _safe_error(exc)
                raise
        self._event_bus.publish(TRADE_LIFECYCLE_V1_READY, snapshot)
        return snapshot

    def start(self) -> TradeLifecycleV1Snapshot:
        with self._lock:
            if self._status is TradeLifecycleStatus.RUNNING:
                return self.snapshot()
            self.validate()
            if not self._execution_runtime.snapshot().running:
                self._execution_runtime.start()
            self._status = TradeLifecycleStatus.RUNNING
            self._last_started_at = self._now()
            self._change = TradeLifecycleChange.STARTED
            self._record(TradeLifecycleStage.IDLE, TradeLifecycleOutcome.IN_PROGRESS, "Trade lifecycle coordinator started.")
            snapshot = self._store_snapshot()
        self._event_bus.publish(TRADE_LIFECYCLE_V1_UPDATED, snapshot)
        return snapshot

    def stop(self) -> TradeLifecycleV1Snapshot:
        with self._lock:
            if self._status is TradeLifecycleStatus.STOPPED:
                return self.snapshot()
            if self._execution_runtime.snapshot().open_intent_count:
                raise RuntimeError("active execution intent blocks stop")
            if self._position_engine.snapshot().has_open_position:
                raise RuntimeError("active position blocks stop")
            if self._execution_runtime.snapshot().running:
                self._execution_runtime.stop()
            self._status = TradeLifecycleStatus.STOPPED
            self._last_stopped_at = self._now()
            snapshot = self._store_snapshot()
        self._event_bus.publish(TRADE_LIFECYCLE_V1_UPDATED, snapshot)
        return snapshot

    def process(self, request: TradeLifecycleV1Request) -> TradeLifecycleV1Snapshot:
        if not isinstance(request, TradeLifecycleV1Request):
            raise TypeError("request must be TradeLifecycleV1Request")
        with self._lock:
            if self._status is not TradeLifecycleStatus.RUNNING:
                raise RuntimeError("trade lifecycle coordinator must be running")
            if request.market_context.instrument is not self.instrument:
                raise ValueError("request instrument mismatch")
            if self._last_request == request and self._last_request_snapshot is not None:
                if self._execution_result is not None or self._position_result is not None:
                    raise RuntimeError("duplicate trade creation request")
                return self._last_request_snapshot
            if self._execution_runtime.snapshot().open_intent_count:
                raise RuntimeError("active execution intent blocks new lifecycle processing")
            if self._configuration.require_no_active_position_before_new_trade and self._position_engine.snapshot().has_open_position:
                raise RuntimeError("active position blocks new lifecycle processing")
            self._processing_count += 1
            self._market_context = request.market_context
            self._stage_records = ()
            self._record(TradeLifecycleStage.CONTEXT_RECEIVED, TradeLifecycleOutcome.IN_PROGRESS, "Market Context V2 snapshot received.")
            self._ai_reasoning = self._ai_reasoning_engine.process(request.market_context)
            self._record(TradeLifecycleStage.REASONING_COMPLETED, TradeLifecycleOutcome.IN_PROGRESS, "AI Reasoning V2 completed.")
            strategy_input = StrategyDecisionV2Input(self._ai_reasoning, request.current_price, request.camarilla, request.cpr, request.vwap)
            self._strategy_decision = self._strategy_engine.process(strategy_input)
            self._record(TradeLifecycleStage.STRATEGY_COMPLETED, TradeLifecycleOutcome.IN_PROGRESS, "Strategy Decision V2 completed.")
            gate = self._strategy_gate()
            if gate is not None:
                snapshot = self._finish_request(request, *gate)
                return snapshot
            risk_input = RiskManagementV2Input(
                self._strategy_decision,
                request.account_risk_state,
                request.session_risk_state,
                request.instrument_exposure_state,
                request.proposed_entry_price,
                request.proposed_invalidation_price,
                request.proposed_objective_price,
                request.quantity_step,
                request.contract_multiplier,
            )
            self._risk_decision = self._risk_engine.process(risk_input)
            self._record(TradeLifecycleStage.RISK_COMPLETED, TradeLifecycleOutcome.IN_PROGRESS, "Risk Management V2 completed.")
            gate = self._risk_gate()
            if gate is not None:
                snapshot = self._finish_request(request, *gate)
                return snapshot
            if self._configuration.auto_submit_risk_approved_execution:
                self._execution_result = self._execution_runtime.submit(self._risk_decision)
                self._execution_count += 1
                self._record_execution_stages()
                if self._execution_result.decision is not ExecutionDecision.ACCEPTED:
                    snapshot = self._finish_request(request, TradeLifecycleStage.BLOCKED, TradeLifecycleOutcome.BLOCKED, TradeLifecycleChange.BECAME_BLOCKED, TradeLifecycleBlockSource.EXECUTION)
                    return snapshot
                if self._should_open_position(self._execution_result):
                    self._position_result = self._position_engine.open_from_execution(self._execution_result)
                    self._position_open_count += 1
                    self._record(TradeLifecycleStage.POSITION_OPEN, TradeLifecycleOutcome.POSITION_ACTIVE, "Position Management V1 opened a dry-run position.")
                    snapshot = self._finish_request(request, TradeLifecycleStage.POSITION_OPEN, TradeLifecycleOutcome.POSITION_ACTIVE, TradeLifecycleChange.POSITION_OPENED, TradeLifecycleBlockSource.NONE)
                    return snapshot
            snapshot = self._finish_request(request, self._stage, TradeLifecycleOutcome.IN_PROGRESS, TradeLifecycleChange.EXECUTION_STARTED, TradeLifecycleBlockSource.NONE)
            return snapshot

    def confirm_execution_fill(self, *, fill_quantity: int, fill_price: float) -> TradeLifecycleV1Snapshot:
        with self._lock:
            if self._status is not TradeLifecycleStatus.RUNNING:
                raise RuntimeError("trade lifecycle coordinator must be running")
            if self._position_engine.snapshot().has_open_position:
                raise RuntimeError("V1 does not add later fills to an already-open position")
            self._execution_result = self._execution_runtime.confirm_fill(fill_quantity=fill_quantity, fill_price=fill_price)
            self._record_execution_stages()
            if self._should_open_position(self._execution_result):
                self._position_result = self._position_engine.open_from_execution(self._execution_result)
                self._position_open_count += 1
                self._record(TradeLifecycleStage.POSITION_OPEN, TradeLifecycleOutcome.POSITION_ACTIVE, "Position Management V1 opened a dry-run position.")
                snapshot = self._finish(TradeLifecycleStage.POSITION_OPEN, TradeLifecycleOutcome.POSITION_ACTIVE, TradeLifecycleChange.POSITION_OPENED, TradeLifecycleBlockSource.NONE)
            else:
                snapshot = self._finish(self._stage, TradeLifecycleOutcome.IN_PROGRESS, TradeLifecycleChange.STAGE_ADVANCED, TradeLifecycleBlockSource.NONE)
        self._event_bus.publish(TRADE_LIFECYCLE_V1_UPDATED, snapshot)
        return snapshot

    def update_position_price(self, update: PositionPriceUpdate) -> TradeLifecycleV1Snapshot:
        with self._lock:
            if self._last_position_update == update and self._history:
                return self._history[-1]
            same_timestamp = self._last_position_update is not None and update.timestamp == self._last_position_update.timestamp
            self._position_result = self._position_engine.update_price(update)
            self._last_position_update = update
            stage, outcome, change = self._position_mapping(self._position_result)
            if stage is TradeLifecycleStage.POSITION_CLOSED:
                self._position_close_count += 1
            self._record(stage, outcome, self._position_result.message)
            snapshot = self._finish(stage, outcome, change, TradeLifecycleBlockSource.NONE, replace_latest=same_timestamp)
        self._publish_position(snapshot)
        return snapshot

    def partial_exit_position(self, *, quantity: int, exit_price: float) -> TradeLifecycleV1Snapshot:
        with self._lock:
            self._position_result = self._position_engine.partial_exit(quantity=quantity, exit_price=exit_price)
            self._record(TradeLifecycleStage.POSITION_PARTIALLY_CLOSED, TradeLifecycleOutcome.POSITION_ACTIVE, self._position_result.message)
            snapshot = self._finish(TradeLifecycleStage.POSITION_PARTIALLY_CLOSED, TradeLifecycleOutcome.POSITION_ACTIVE, TradeLifecycleChange.POSITION_UPDATED, TradeLifecycleBlockSource.NONE)
        self._event_bus.publish(TRADE_LIFECYCLE_V1_UPDATED, snapshot)
        return snapshot

    def close_position(self, *, exit_price: float) -> TradeLifecycleV1Snapshot:
        with self._lock:
            self._position_result = self._position_engine.close(exit_price=exit_price, reason=PositionExitReason.MANUAL_DRY_RUN)
            self._position_close_count += 1
            self._record(TradeLifecycleStage.POSITION_CLOSED, TradeLifecycleOutcome.POSITION_CLOSED, self._position_result.message)
            snapshot = self._finish(TradeLifecycleStage.POSITION_CLOSED, TradeLifecycleOutcome.POSITION_CLOSED, TradeLifecycleChange.POSITION_CLOSED, TradeLifecycleBlockSource.NONE)
        self._event_bus.publish(TRADE_LIFECYCLE_POSITION_CLOSED, snapshot)
        self._event_bus.publish(TRADE_LIFECYCLE_V1_UPDATED, snapshot)
        return snapshot

    def snapshot(self) -> TradeLifecycleV1Snapshot:
        return TradeLifecycleV1Snapshot(
            instrument=self.instrument,
            timestamp=self._now(),
            lifecycle_status=self._status,
            stage=self._stage,
            outcome=self._outcome,
            change=self._change,
            block_source=self._block_source,
            market_context=self._market_context,
            ai_reasoning=self._ai_reasoning,
            strategy_decision=self._strategy_decision,
            risk_decision=self._risk_decision,
            execution_result=self._execution_result,
            position_result=self._position_result,
            execution_snapshot=self._execution_runtime.snapshot(),
            position_snapshot=self._position_engine.snapshot(),
            stage_records=self._stage_records,
            processing_count=self._processing_count,
            waiting_count=self._waiting_count,
            blocked_count=self._blocked_count,
            rejected_count=self._rejected_count,
            execution_count=self._execution_count,
            position_open_count=self._position_open_count,
            position_close_count=self._position_close_count,
            running=self._status is TradeLifecycleStatus.RUNNING,
            ready=self._status in {TradeLifecycleStatus.READY, TradeLifecycleStatus.RUNNING},
            last_started_at=self._last_started_at,
            last_stopped_at=self._last_stopped_at,
            last_processed_at=self._last_processed_at,
            last_error=self._last_error,
        )

    def history(self) -> tuple[TradeLifecycleV1Snapshot, ...]:
        return self._history

    def clear(self) -> TradeLifecycleV1Snapshot:
        with self._lock:
            if self._status is not TradeLifecycleStatus.STOPPED:
                raise RuntimeError("trade lifecycle coordinator must be stopped before clear")
            if self._execution_runtime.snapshot().open_intent_count or self._position_engine.snapshot().has_open_position:
                raise RuntimeError("cannot clear active execution or position state")
            self._status = TradeLifecycleStatus.CLEARED
            self._stage = TradeLifecycleStage.IDLE
            self._outcome = TradeLifecycleOutcome.IN_PROGRESS
            self._change = TradeLifecycleChange.RESET
            self._block_source = TradeLifecycleBlockSource.NONE
            self._stage_records = ()
            self._history = ()
            self._processing_count = self._waiting_count = self._blocked_count = self._rejected_count = 0
            self._execution_count = self._position_open_count = self._position_close_count = 0
            self._last_error = None
            snapshot = self.snapshot()
        self._event_bus.publish(TRADE_LIFECYCLE_V1_UPDATED, snapshot)
        return snapshot

    def _strategy_gate(self):
        action = self._strategy_decision.action
        if action is StrategyAction.WAIT and self._configuration.stop_on_strategy_wait:
            self._waiting_count += 1
            return TradeLifecycleStage.WAITING, TradeLifecycleOutcome.WAITING, TradeLifecycleChange.BECAME_WAITING, TradeLifecycleBlockSource.STRATEGY
        if action is StrategyAction.NO_TRADE and self._configuration.stop_on_strategy_no_trade:
            self._blocked_count += 1
            return TradeLifecycleStage.BLOCKED, TradeLifecycleOutcome.BLOCKED, TradeLifecycleChange.BECAME_BLOCKED, TradeLifecycleBlockSource.STRATEGY
        if action is StrategyAction.INSUFFICIENT_DATA:
            self._blocked_count += 1
            return TradeLifecycleStage.INSUFFICIENT_DATA, TradeLifecycleOutcome.INSUFFICIENT_DATA, TradeLifecycleChange.BECAME_BLOCKED, TradeLifecycleBlockSource.DATA
        return None

    def _risk_gate(self):
        decision = self._risk_decision.decision
        if decision is RiskDecision.WAIT and self._configuration.stop_on_risk_wait:
            self._waiting_count += 1
            return TradeLifecycleStage.WAITING, TradeLifecycleOutcome.WAITING, TradeLifecycleChange.BECAME_WAITING, TradeLifecycleBlockSource.RISK
        if decision is RiskDecision.REJECTED and self._configuration.stop_on_risk_rejection:
            self._rejected_count += 1
            return TradeLifecycleStage.REJECTED, TradeLifecycleOutcome.REJECTED, TradeLifecycleChange.BECAME_REJECTED, TradeLifecycleBlockSource.RISK
        if decision is RiskDecision.INSUFFICIENT_DATA:
            self._blocked_count += 1
            return TradeLifecycleStage.INSUFFICIENT_DATA, TradeLifecycleOutcome.INSUFFICIENT_DATA, TradeLifecycleChange.BECAME_BLOCKED, TradeLifecycleBlockSource.DATA
        return None

    def _should_open_position(self, result) -> bool:
        return (
            self._configuration.auto_open_position_on_fill
            and result.filled_quantity > 0
            and result.average_fill_price is not None
            and (self._configuration.allow_partial_fill_position_open or result.remaining_quantity == 0)
        )

    def _record_execution_stages(self):
        self._record(TradeLifecycleStage.EXECUTION_SUBMITTED, TradeLifecycleOutcome.IN_PROGRESS, "Execution Runtime V1 dry-run submission completed.")
        status = self._execution_result.intent.status if self._execution_result.intent else None
        if status is ExecutionIntentStatus.ACKNOWLEDGED:
            self._record(TradeLifecycleStage.EXECUTION_ACKNOWLEDGED, TradeLifecycleOutcome.IN_PROGRESS, "Dry-run execution acknowledged.")
        elif status is ExecutionIntentStatus.PARTIALLY_FILLED:
            self._record(TradeLifecycleStage.EXECUTION_PARTIALLY_FILLED, TradeLifecycleOutcome.EXECUTED_DRY_RUN, "Dry-run execution partially filled.")
        elif status is ExecutionIntentStatus.FILLED:
            self._record(TradeLifecycleStage.EXECUTION_FILLED, TradeLifecycleOutcome.EXECUTED_DRY_RUN, "Dry-run execution filled.")

    def _position_mapping(self, result):
        if result.decision is PositionDecision.PARTIAL_EXIT:
            return TradeLifecycleStage.POSITION_PARTIALLY_CLOSED, TradeLifecycleOutcome.POSITION_ACTIVE, TradeLifecycleChange.POSITION_UPDATED
        if result.decision is PositionDecision.FULL_EXIT:
            return TradeLifecycleStage.POSITION_CLOSED, TradeLifecycleOutcome.POSITION_CLOSED, TradeLifecycleChange.POSITION_CLOSED
        if result.change is PositionChange.OBJECTIVE_REACHED:
            return TradeLifecycleStage.POSITION_OPEN, TradeLifecycleOutcome.POSITION_ACTIVE, TradeLifecycleChange.POSITION_UPDATED
        return TradeLifecycleStage.POSITION_OPEN, TradeLifecycleOutcome.POSITION_ACTIVE, TradeLifecycleChange.POSITION_UPDATED

    def _record(self, stage, outcome, message):
        record = TradeLifecycleStageRecord(len(self._stage_records) + 1, self._now(), stage, outcome, message)
        self._stage_records = self._stage_records + (record,)
        self._stage = stage
        self._outcome = outcome

    def _finish_request(self, request, stage, outcome, change, block_source):
        snapshot = self._finish(stage, outcome, change, block_source)
        self._last_request = request
        self._last_request_snapshot = snapshot
        return snapshot

    def _finish(self, stage, outcome, change, block_source, *, replace_latest=False):
        self._stage = stage
        self._outcome = outcome
        self._change = change
        self._block_source = block_source
        self._last_processed_at = self._now()
        snapshot = self._store_snapshot(replace_latest=replace_latest)
        return snapshot

    def _store_snapshot(self, *, replace_latest=False):
        snapshot = self.snapshot()
        history = self._history[:-1] + (snapshot,) if replace_latest and self._history else self._history + (snapshot,)
        if len(history) > self._configuration.history_limit:
            history = history[-self._configuration.history_limit:]
        self._history = history
        return snapshot

    def _publish_position(self, snapshot):
        if snapshot.stage is TradeLifecycleStage.POSITION_CLOSED:
            self._event_bus.publish(TRADE_LIFECYCLE_POSITION_CLOSED, snapshot)
        elif snapshot.position_result is not None:
            self._event_bus.publish(TRADE_LIFECYCLE_POSITION_OPENED, snapshot)
        self._event_bus.publish(TRADE_LIFECYCLE_V1_UPDATED, snapshot)

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("token", "[redacted]").replace("credential", "[redacted]")
