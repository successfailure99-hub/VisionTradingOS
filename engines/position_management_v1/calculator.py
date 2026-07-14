"""
Pure calculator for Position Management Engine V1.
"""

from dataclasses import replace
from datetime import datetime
from math import floor

from application.execution_runtime_v1.enums import ExecutionSide
from application.execution_runtime_v1.models import ExecutionResult
from engines.position_management_v1.configuration import PositionManagementV1Configuration
from engines.position_management_v1.enums import (
    PositionExitReason,
    PositionPnlState,
    PositionSide,
    PositionStatus,
)
from engines.position_management_v1.models import (
    ManagedPosition,
    PositionExitRequest,
    PositionPriceUpdate,
    PositionSource,
    build_position_id,
)
from engines.position_management_v1.validator import PositionSourceValidator


class PositionManagementCalculator:
    def __init__(self, validator: PositionSourceValidator | None = None) -> None:
        self._validator = validator or PositionSourceValidator()

    def open_from_execution(
        self,
        result: ExecutionResult,
        configuration: PositionManagementV1Configuration,
        *,
        timestamp: datetime,
    ) -> ManagedPosition:
        valid, messages = self._validator.validate(result, configuration)
        if not valid:
            raise ValueError(messages[0])
        intent = result.intent
        source = PositionSource(
            execution_result=result,
            execution_intent=intent,
            risk_snapshot=intent.risk_snapshot,
            strategy_snapshot=intent.risk_snapshot.strategy,
        )
        side = PositionSide.LONG if intent.side is ExecutionSide.BUY else PositionSide.SHORT
        entry = result.average_fill_price
        quantity = result.filled_quantity
        return ManagedPosition(
            position_id=build_position_id(source),
            instrument=intent.instrument,
            side=side,
            opened_at=timestamp,
            updated_at=timestamp,
            closed_at=None,
            initial_quantity=quantity,
            open_quantity=quantity,
            closed_quantity=0,
            average_entry_price=entry,
            current_price=entry,
            average_exit_price=None,
            invalidation_price=intent.invalidation_price,
            objective_price=intent.objective_price,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            total_pnl=0.0,
            pnl_state=PositionPnlState.FLAT,
            status=PositionStatus.OPEN,
            exit_reason=PositionExitReason.NONE,
            source=source,
            dry_run=True,
            analysis_only=True,
        )

    def update_price(
        self,
        position: ManagedPosition,
        update: PositionPriceUpdate,
    ) -> ManagedPosition:
        if update.instrument is not position.instrument:
            raise ValueError("price update instrument mismatch")
        if update.timestamp < position.updated_at:
            raise ValueError("stale position price update")
        unrealized = _unrealized(position.side, position.average_entry_price, update.market_price, position.open_quantity)
        total = position.realized_pnl + unrealized
        return replace(
            position,
            updated_at=update.timestamp,
            current_price=update.market_price,
            unrealized_pnl=unrealized,
            total_pnl=total,
            pnl_state=_pnl_state(total),
        )

    def apply_exit(
        self,
        position: ManagedPosition,
        request: PositionExitRequest,
    ) -> ManagedPosition:
        if position.status in {PositionStatus.CLOSED, PositionStatus.INVALIDATED}:
            raise ValueError("cannot exit a closed position")
        if request.timestamp < position.updated_at:
            raise ValueError("stale position exit request")
        if request.quantity > position.open_quantity:
            raise ValueError("exit quantity cannot exceed open quantity")
        new_closed = position.closed_quantity + request.quantity
        new_open = position.open_quantity - request.quantity
        realized_delta = _realized(position.side, position.average_entry_price, request.exit_price, request.quantity)
        average_exit = request.exit_price
        if position.closed_quantity:
            average_exit = (
                position.average_exit_price * position.closed_quantity
                + request.exit_price * request.quantity
            ) / new_closed
        unrealized = _unrealized(position.side, position.average_entry_price, request.exit_price, new_open)
        realized = position.realized_pnl + realized_delta
        status = PositionStatus.PARTIALLY_CLOSED if new_open > 0 else PositionStatus.CLOSED
        if request.reason is PositionExitReason.INVALIDATION:
            status = PositionStatus.INVALIDATED
        return replace(
            position,
            updated_at=request.timestamp,
            closed_at=request.timestamp if new_open == 0 else position.closed_at,
            open_quantity=new_open,
            closed_quantity=new_closed,
            current_price=request.exit_price,
            average_exit_price=average_exit,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_pnl=realized + unrealized,
            pnl_state=_pnl_state(realized + unrealized),
            status=status,
            exit_reason=request.reason,
        )

    def invalidation_reached(self, position: ManagedPosition, price: float) -> bool:
        if position.side is PositionSide.LONG:
            return price <= position.invalidation_price
        return price >= position.invalidation_price

    def objective_reached(self, position: ManagedPosition, price: float) -> bool:
        if position.objective_price is None:
            return False
        if position.side is PositionSide.LONG:
            return price >= position.objective_price
        return price <= position.objective_price

    def objective_partial_quantity(
        self,
        position: ManagedPosition,
        configuration: PositionManagementV1Configuration,
    ) -> int:
        quantity = floor(position.open_quantity * configuration.partial_exit_fraction)
        remaining = position.open_quantity - quantity
        if remaining < configuration.minimum_remaining_quantity:
            quantity = position.open_quantity - configuration.minimum_remaining_quantity
        return max(0, quantity)


def _unrealized(side: PositionSide, entry: float, price: float, quantity: int) -> float:
    if side is PositionSide.LONG:
        return (price - entry) * quantity
    return (entry - price) * quantity


def _realized(side: PositionSide, entry: float, exit_price: float, quantity: int) -> float:
    if side is PositionSide.LONG:
        return (exit_price - entry) * quantity
    return (entry - exit_price) * quantity


def _pnl_state(value: float) -> PositionPnlState:
    if value > 0:
        return PositionPnlState.PROFIT
    if value < 0:
        return PositionPnlState.LOSS
    return PositionPnlState.FLAT
