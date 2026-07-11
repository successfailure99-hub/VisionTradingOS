"""
Stateless Position Management Engine V1 calculator.
"""

from dataclasses import replace
from datetime import datetime

from engines.order_management.enums import OrderSide
from engines.position.enums import PositionSide, PositionStatus, PositionUpdateType
from engines.position.models import PositionFill, PositionMark, PositionState


class PositionCalculator:
    """
    Deterministic position transition calculator.

    V1 assumes one price point times one unit equals one monetary unit. It
    intentionally excludes brokerage, taxes, fees, slippage, currency
    conversion, contract multipliers, margin, and corporate actions.
    """

    @staticmethod
    def apply_fill(
        current: PositionState | None,
        fill: PositionFill,
    ) -> PositionState:
        if current is None:
            return PositionCalculator._open_new(fill, 0, 0, 0.0, None, 1)

        if current.net_quantity == 0:
            return PositionCalculator._open_new(
                fill,
                current.total_buy_quantity,
                current.total_sell_quantity,
                current.realized_pnl,
                current.mark_price,
                current.version + 1,
            )

        if current.net_quantity > 0:
            if fill.side is OrderSide.BUY:
                return PositionCalculator._add_long(current, fill)
            return PositionCalculator._reduce_long(current, fill)

        if fill.side is OrderSide.SELL:
            return PositionCalculator._add_short(current, fill)
        return PositionCalculator._reduce_short(current, fill)

    @staticmethod
    def apply_mark(
        current: PositionState,
        mark: PositionMark,
    ) -> PositionState:
        unrealized = PositionCalculator._unrealized(
            current.net_quantity,
            current.average_entry_price,
            mark.mark_price,
        )
        return replace(
            current,
            updated_at=mark.timestamp,
            mark_price=mark.mark_price,
            unrealized_pnl=unrealized,
            total_pnl=round(current.realized_pnl + unrealized, 2),
            last_update_type=PositionUpdateType.MARK,
            version=current.version + 1,
        )

    @staticmethod
    def _open_new(
        fill: PositionFill,
        total_buy_quantity: int,
        total_sell_quantity: int,
        realized_pnl: float,
        mark_price: float | None,
        version: int,
    ) -> PositionState:
        net_quantity = fill.quantity if fill.side is OrderSide.BUY else -fill.quantity
        totals = PositionCalculator._fill_totals(total_buy_quantity, total_sell_quantity, fill)
        side = PositionSide.LONG if net_quantity > 0 else PositionSide.SHORT
        unrealized = PositionCalculator._unrealized(net_quantity, fill.price, mark_price)
        return PositionState(
            symbol=fill.symbol,
            exchange=fill.exchange,
            timeframe=fill.timeframe,
            side=side,
            status=PositionStatus.OPEN,
            opened_at=fill.timestamp,
            updated_at=fill.timestamp,
            closed_at=None,
            net_quantity=net_quantity,
            absolute_quantity=abs(net_quantity),
            average_entry_price=fill.price,
            mark_price=mark_price,
            realized_pnl=round(realized_pnl, 2),
            unrealized_pnl=unrealized,
            total_pnl=round(realized_pnl + unrealized, 2),
            total_buy_quantity=totals[0],
            total_sell_quantity=totals[1],
            last_fill_execution_id=fill.execution_id,
            last_fill_price=fill.price,
            last_fill_quantity=fill.quantity,
            last_update_type=PositionUpdateType.OPEN,
            version=version,
        )

    @staticmethod
    def _add_long(current: PositionState, fill: PositionFill) -> PositionState:
        new_quantity = current.net_quantity + fill.quantity
        average = round(
            ((current.average_entry_price * current.net_quantity) + (fill.price * fill.quantity)) / new_quantity,
            4,
        )
        return PositionCalculator._open_update(current, fill, new_quantity, average, current.realized_pnl, PositionUpdateType.ADD)

    @staticmethod
    def _add_short(current: PositionState, fill: PositionFill) -> PositionState:
        current_absolute = abs(current.net_quantity)
        new_absolute = current_absolute + fill.quantity
        average = round(
            ((current.average_entry_price * current_absolute) + (fill.price * fill.quantity)) / new_absolute,
            4,
        )
        return PositionCalculator._open_update(current, fill, -new_absolute, average, current.realized_pnl, PositionUpdateType.ADD)

    @staticmethod
    def _reduce_long(current: PositionState, fill: PositionFill) -> PositionState:
        matched = min(current.net_quantity, fill.quantity)
        realized = round(current.realized_pnl + ((fill.price - current.average_entry_price) * matched), 2)
        remaining = current.net_quantity - fill.quantity
        if remaining > 0:
            return PositionCalculator._open_update(current, fill, remaining, current.average_entry_price, realized, PositionUpdateType.REDUCE)
        if remaining == 0:
            return PositionCalculator._flat_update(current, fill, realized)
        return PositionCalculator._open_update(current, fill, remaining, fill.price, realized, PositionUpdateType.REVERSE, fill.timestamp)

    @staticmethod
    def _reduce_short(current: PositionState, fill: PositionFill) -> PositionState:
        current_absolute = abs(current.net_quantity)
        matched = min(current_absolute, fill.quantity)
        realized = round(current.realized_pnl + ((current.average_entry_price - fill.price) * matched), 2)
        remaining_absolute = current_absolute - fill.quantity
        if remaining_absolute > 0:
            return PositionCalculator._open_update(current, fill, -remaining_absolute, current.average_entry_price, realized, PositionUpdateType.REDUCE)
        if remaining_absolute == 0:
            return PositionCalculator._flat_update(current, fill, realized)
        return PositionCalculator._open_update(current, fill, abs(remaining_absolute), fill.price, realized, PositionUpdateType.REVERSE, fill.timestamp)

    @staticmethod
    def _open_update(
        current: PositionState,
        fill: PositionFill,
        net_quantity: int,
        average_entry_price: float,
        realized_pnl: float,
        update_type: PositionUpdateType,
        opened_at: datetime | None = None,
    ) -> PositionState:
        total_buy_quantity, total_sell_quantity = PositionCalculator._fill_totals(
            current.total_buy_quantity,
            current.total_sell_quantity,
            fill,
        )
        side = PositionSide.LONG if net_quantity > 0 else PositionSide.SHORT
        unrealized = PositionCalculator._unrealized(net_quantity, average_entry_price, current.mark_price)
        return replace(
            current,
            side=side,
            status=PositionStatus.OPEN,
            opened_at=opened_at if opened_at is not None else current.opened_at,
            updated_at=fill.timestamp,
            closed_at=None,
            net_quantity=net_quantity,
            absolute_quantity=abs(net_quantity),
            average_entry_price=average_entry_price,
            realized_pnl=round(realized_pnl, 2),
            unrealized_pnl=unrealized,
            total_pnl=round(realized_pnl + unrealized, 2),
            total_buy_quantity=total_buy_quantity,
            total_sell_quantity=total_sell_quantity,
            last_fill_execution_id=fill.execution_id,
            last_fill_price=fill.price,
            last_fill_quantity=fill.quantity,
            last_update_type=update_type,
            version=current.version + 1,
        )

    @staticmethod
    def _flat_update(current: PositionState, fill: PositionFill, realized_pnl: float) -> PositionState:
        total_buy_quantity, total_sell_quantity = PositionCalculator._fill_totals(
            current.total_buy_quantity,
            current.total_sell_quantity,
            fill,
        )
        return replace(
            current,
            side=PositionSide.FLAT,
            status=PositionStatus.CLOSED,
            updated_at=fill.timestamp,
            closed_at=fill.timestamp,
            net_quantity=0,
            absolute_quantity=0,
            average_entry_price=None,
            realized_pnl=round(realized_pnl, 2),
            unrealized_pnl=0.0,
            total_pnl=round(realized_pnl, 2),
            total_buy_quantity=total_buy_quantity,
            total_sell_quantity=total_sell_quantity,
            last_fill_execution_id=fill.execution_id,
            last_fill_price=fill.price,
            last_fill_quantity=fill.quantity,
            last_update_type=PositionUpdateType.CLOSE,
            version=current.version + 1,
        )

    @staticmethod
    def _fill_totals(total_buy_quantity: int, total_sell_quantity: int, fill: PositionFill) -> tuple[int, int]:
        if fill.side is OrderSide.BUY:
            return total_buy_quantity + fill.quantity, total_sell_quantity
        return total_buy_quantity, total_sell_quantity + fill.quantity

    @staticmethod
    def _unrealized(net_quantity: int, average_entry_price: float | None, mark_price: float | None) -> float:
        if net_quantity == 0 or average_entry_price is None or mark_price is None:
            return 0.0
        absolute_quantity = abs(net_quantity)
        if net_quantity > 0:
            return round((mark_price - average_entry_price) * absolute_quantity, 2)
        return round((average_entry_price - mark_price) * absolute_quantity, 2)
