import pytest

from engines.position_management_v1 import (
    PositionExitReason,
    PositionExitRequest,
    PositionManagementCalculator,
    PositionManagementV1Configuration,
    PositionPnlState,
    PositionPriceUpdate,
    PositionSide,
    PositionStatus,
)
from tests.test_position_management_v1_models import filled_execution, position


def test_open_long_short_and_initial_pnl():
    long = position("bullish")
    short = position("bearish")

    assert long.side is PositionSide.LONG
    assert short.side is PositionSide.SHORT
    assert long.unrealized_pnl == 0.0
    assert short.unrealized_pnl == 0.0


def test_unrealized_profit_loss_for_long_and_short():
    calc = PositionManagementCalculator()
    long = position("bullish")
    short = position("bearish")
    long_profit = calc.update_price(long, PositionPriceUpdate(long.instrument, long.updated_at, long.average_entry_price + 10))
    short_profit = calc.update_price(short, PositionPriceUpdate(short.instrument, short.updated_at, short.average_entry_price - 10))
    long_loss = calc.update_price(long, PositionPriceUpdate(long.instrument, long.updated_at, long.average_entry_price - 10))

    assert long_profit.pnl_state is PositionPnlState.PROFIT
    assert short_profit.unrealized_pnl > 0
    assert long_loss.pnl_state is PositionPnlState.LOSS


def test_partial_full_exit_weighted_average_realized_and_total_pnl():
    calc = PositionManagementCalculator()
    pos = position()
    partial = calc.apply_exit(pos, PositionExitRequest(pos.updated_at, 1, pos.average_entry_price + 10, PositionExitReason.MANUAL_DRY_RUN))
    final = calc.apply_exit(partial, PositionExitRequest(partial.updated_at, partial.open_quantity, pos.average_entry_price + 20, PositionExitReason.MANUAL_DRY_RUN))

    assert partial.status is PositionStatus.PARTIALLY_CLOSED
    assert final.status is PositionStatus.CLOSED
    assert final.open_quantity == 0
    assert final.average_exit_price > partial.average_exit_price
    assert final.total_pnl == final.realized_pnl + final.unrealized_pnl


def test_invalidation_objective_partial_quantity_no_rounding_and_input_immutability():
    calc = PositionManagementCalculator()
    pos = position()
    before = pos
    assert calc.invalidation_reached(pos, pos.invalidation_price) is True
    assert calc.objective_reached(pos, pos.objective_price) is True
    quantity = calc.objective_partial_quantity(pos, PositionManagementV1Configuration(partial_exit_fraction=0.5))
    assert quantity <= pos.open_quantity // 2
    assert pos == before
    with pytest.raises(ValueError):
        calc.update_price(pos, PositionPriceUpdate(pos.instrument, pos.opened_at.replace(year=2025), pos.current_price))
