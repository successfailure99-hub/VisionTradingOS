"""
Stateful Position Management Engine V1.
"""

from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock

from application.execution_runtime_v1.models import ExecutionResult
from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import (
    POSITION_CLOSED_DRY_RUN,
    POSITION_INVALIDATED_DRY_RUN,
    POSITION_MANAGEMENT_V1_UPDATED,
    POSITION_OBJECTIVE_REACHED,
    POSITION_OPENED_DRY_RUN,
    POSITION_PARTIALLY_CLOSED_DRY_RUN,
    POSITION_PRICE_UPDATED,
)
from engines.position_management_v1.calculator import PositionManagementCalculator
from engines.position_management_v1.configuration import PositionManagementV1Configuration
from engines.position_management_v1.enums import (
    PositionChange,
    PositionDecision,
    PositionExitReason,
    PositionStatus,
)
from engines.position_management_v1.models import (
    PositionExitRequest,
    PositionManagementResult,
    PositionManagementV1Snapshot,
    PositionPriceUpdate,
)
from engines.risk_management_v2.models import SUPPORTED_INSTRUMENTS
from engines.position_management_v1.validator import PositionSourceValidator


class PositionManagementV1Engine(BaseEngine):
    def __init__(
        self,
        *,
        instrument: Instrument,
        configuration: PositionManagementV1Configuration | None = None,
        validator: PositionSourceValidator | None = None,
        calculator: PositionManagementCalculator | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ):
        if instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        super().__init__(event_bus or EventBus())
        self.instrument = instrument
        self._configuration = configuration or PositionManagementV1Configuration()
        self._validator = validator or PositionSourceValidator()
        self._calculator = calculator or PositionManagementCalculator(self._validator)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._active_position = None
        self._last_result: PositionManagementResult | None = None
        self._history: tuple[PositionManagementResult, ...] = ()
        self._open_cache: dict[ExecutionResult, PositionManagementResult] = {}
        self._last_update: PositionPriceUpdate | None = None
        self._opened_count = 0
        self._partial_exit_count = 0
        self._closed_count = 0
        self._invalidation_exit_count = 0
        self._objective_reached_count = 0
        self._realized_pnl_total = 0.0
        self._last_error: str | None = None

    def open_from_execution(self, result: ExecutionResult) -> PositionManagementResult:
        if not isinstance(result, ExecutionResult):
            raise TypeError("result must be ExecutionResult")
        with self._lock:
            cached = self._open_cache.get(result)
            if cached is not None:
                return cached
            if result.intent is None or result.intent.instrument is not self.instrument:
                raise ValueError("execution result instrument mismatch")
            if self._active_position is not None:
                raise RuntimeError("active position already exists")
            position = self._calculator.open_from_execution(result, self._configuration, timestamp=self._now())
            managed = PositionManagementResult(PositionDecision.HOLD, position, PositionChange.OPENED, "Dry-run position opened.")
            self._active_position = position
            self._last_result = managed
            self._opened_count += 1
            self._open_cache[result] = managed
            self._append_history(managed)
            self._data = position
            snapshot = self.snapshot()
        self._event_bus.publish(POSITION_OPENED_DRY_RUN, managed)
        self._event_bus.publish(POSITION_MANAGEMENT_V1_UPDATED, snapshot)
        return managed

    def update_price(self, update: PositionPriceUpdate) -> PositionManagementResult:
        if not isinstance(update, PositionPriceUpdate):
            raise TypeError("update must be PositionPriceUpdate")
        if update.instrument is not self.instrument:
            raise ValueError("position update instrument mismatch")
        with self._lock:
            if self._active_position is None:
                result = PositionManagementResult(PositionDecision.NO_POSITION, None, PositionChange.UNCHANGED, "No active position.")
                self._last_result = result
                return result
            if self._last_update is not None:
                if update.timestamp < self._last_update.timestamp:
                    raise ValueError("stale position price update")
                if update == self._last_update:
                    return self._last_result
            same_timestamp = self._last_update is not None and update.timestamp == self._last_update.timestamp
            position = self._calculator.update_price(self._active_position, update)
            change = PositionChange.PRICE_UPDATED if position != self._active_position else PositionChange.UNCHANGED
            decision = PositionDecision.HOLD
            event_name = POSITION_PRICE_UPDATED
            if self._calculator.invalidation_reached(position, update.market_price):
                if self._configuration.auto_exit_on_invalidation:
                    position = self._calculator.apply_exit(
                        position,
                        PositionExitRequest(update.timestamp, position.open_quantity, update.market_price, PositionExitReason.INVALIDATION),
                    )
                    change = PositionChange.INVALIDATED
                    decision = PositionDecision.FULL_EXIT
                    self._invalidation_exit_count += 1
                    self._closed_count += 1
                    event_name = POSITION_INVALIDATED_DRY_RUN
            elif self._calculator.objective_reached(position, update.market_price):
                self._objective_reached_count += 1
                if self._configuration.auto_full_exit_on_objective:
                    position = self._calculator.apply_exit(
                        position,
                        PositionExitRequest(update.timestamp, position.open_quantity, update.market_price, PositionExitReason.OBJECTIVE),
                    )
                    change = PositionChange.CLOSED
                    decision = PositionDecision.FULL_EXIT
                    self._closed_count += 1
                    event_name = POSITION_CLOSED_DRY_RUN
                elif self._configuration.auto_partial_exit_on_objective:
                    quantity = self._calculator.objective_partial_quantity(position, self._configuration)
                    if quantity > 0:
                        position = self._calculator.apply_exit(
                            position,
                            PositionExitRequest(update.timestamp, quantity, update.market_price, PositionExitReason.OBJECTIVE),
                        )
                        change = PositionChange.PARTIALLY_CLOSED
                        decision = PositionDecision.PARTIAL_EXIT
                        self._partial_exit_count += 1
                        event_name = POSITION_PARTIALLY_CLOSED_DRY_RUN
                    else:
                        position = _mark_objective(position, update.timestamp)
                        change = PositionChange.OBJECTIVE_REACHED
                        event_name = POSITION_OBJECTIVE_REACHED
                else:
                    position = _mark_objective(position, update.timestamp)
                    change = PositionChange.OBJECTIVE_REACHED
                    event_name = POSITION_OBJECTIVE_REACHED
            result = PositionManagementResult(decision, position, change, _message(change))
            self._last_update = update
            self._active_position = None if position.status in {PositionStatus.CLOSED, PositionStatus.INVALIDATED} else position
            self._realized_pnl_total = position.realized_pnl
            self._last_result = result
            if same_timestamp and self._history:
                self._history = self._history[:-1] + (result,)
            else:
                self._append_history(result)
            self._data = self._active_position
            snapshot = self.snapshot()
        self._event_bus.publish(event_name, result)
        self._event_bus.publish(POSITION_MANAGEMENT_V1_UPDATED, snapshot)
        return result

    def partial_exit(
        self,
        *,
        quantity: int,
        exit_price: float,
        reason: PositionExitReason = PositionExitReason.MANUAL_DRY_RUN,
    ) -> PositionManagementResult:
        with self._lock:
            if not self._configuration.allow_partial_exit:
                raise RuntimeError("partial exits are disabled")
            if self._active_position is None:
                raise RuntimeError("no active position")
            if quantity >= self._active_position.open_quantity:
                raise ValueError("partial exit quantity must be below open quantity")
            position = self._calculator.apply_exit(
                self._active_position,
                PositionExitRequest(self._position_timestamp(), quantity, exit_price, reason),
            )
            result = PositionManagementResult(PositionDecision.PARTIAL_EXIT, position, PositionChange.PARTIALLY_CLOSED, "Dry-run position partially closed.")
            self._active_position = position
            self._last_result = result
            self._partial_exit_count += 1
            self._realized_pnl_total = position.realized_pnl
            self._append_history(result)
            self._data = position
            snapshot = self.snapshot()
        self._event_bus.publish(POSITION_PARTIALLY_CLOSED_DRY_RUN, result)
        self._event_bus.publish(POSITION_MANAGEMENT_V1_UPDATED, snapshot)
        return result

    def close(
        self,
        *,
        exit_price: float,
        reason: PositionExitReason = PositionExitReason.MANUAL_DRY_RUN,
    ) -> PositionManagementResult:
        with self._lock:
            if self._active_position is None:
                raise RuntimeError("no active position")
            position = self._calculator.apply_exit(
                self._active_position,
                PositionExitRequest(self._position_timestamp(), self._active_position.open_quantity, exit_price, reason),
            )
            change = PositionChange.INVALIDATED if reason is PositionExitReason.INVALIDATION else PositionChange.CLOSED
            result = PositionManagementResult(PositionDecision.FULL_EXIT, position, change, "Dry-run position fully closed.")
            self._active_position = None
            self._last_result = result
            self._closed_count += 1
            if reason is PositionExitReason.INVALIDATION:
                self._invalidation_exit_count += 1
            self._realized_pnl_total = position.realized_pnl
            self._append_history(result)
            self._data = None
            snapshot = self.snapshot()
        self._event_bus.publish(POSITION_INVALIDATED_DRY_RUN if reason is PositionExitReason.INVALIDATION else POSITION_CLOSED_DRY_RUN, result)
        self._event_bus.publish(POSITION_MANAGEMENT_V1_UPDATED, snapshot)
        return result

    def snapshot(self) -> PositionManagementV1Snapshot:
        return PositionManagementV1Snapshot(
            instrument=self.instrument,
            timestamp=self._now(),
            active_position=self._active_position,
            last_result=self._last_result,
            opened_count=self._opened_count,
            partial_exit_count=self._partial_exit_count,
            closed_count=self._closed_count,
            invalidation_exit_count=self._invalidation_exit_count,
            objective_reached_count=self._objective_reached_count,
            realized_pnl_total=self._realized_pnl_total,
            unrealized_pnl_total=self._active_position.unrealized_pnl if self._active_position else 0.0,
            has_open_position=self._active_position is not None,
            history_size=len(self._history),
            last_error=self._last_error,
        )

    def history(self) -> tuple[PositionManagementResult, ...]:
        return self._history

    def clear(self) -> PositionManagementV1Snapshot:
        with self._lock:
            if self._active_position is not None:
                raise RuntimeError("cannot clear while a position is open")
            self._last_result = None
            self._history = ()
            self._open_cache = {}
            self._last_update = None
            self._opened_count = 0
            self._partial_exit_count = 0
            self._closed_count = 0
            self._invalidation_exit_count = 0
            self._objective_reached_count = 0
            self._realized_pnl_total = 0.0
            self._last_error = None
            self._data = None
            snapshot = self.snapshot()
        self._event_bus.publish(POSITION_MANAGEMENT_V1_UPDATED, snapshot)
        return snapshot

    def _append_history(self, result: PositionManagementResult) -> None:
        history = self._history + (result,)
        if len(history) > self._configuration.history_limit:
            history = history[-self._configuration.history_limit:]
        self._history = history

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value

    def _position_timestamp(self) -> datetime:
        value = self._now()
        if self._active_position is not None and value < self._active_position.updated_at:
            return self._active_position.updated_at
        return value


def _mark_objective(position, timestamp):
    return replace(position, updated_at=timestamp, status=PositionStatus.OBJECTIVE_REACHED, exit_reason=PositionExitReason.NONE)


def _message(change: PositionChange) -> str:
    return {
        PositionChange.PRICE_UPDATED: "Dry-run position price updated.",
        PositionChange.INVALIDATED: "Dry-run position invalidated and fully closed.",
        PositionChange.OBJECTIVE_REACHED: "Dry-run position objective reached.",
        PositionChange.PARTIALLY_CLOSED: "Dry-run position partially closed.",
        PositionChange.CLOSED: "Dry-run position fully closed.",
    }.get(change, "Dry-run position unchanged.")
