from datetime import timedelta

from application.trade_lifecycle_v1 import TradeLifecycleStage
from core.enums.instrument import Instrument
from engines.position_management_v1 import PositionPriceUpdate
from tests.test_trade_lifecycle_v1_coordinator import coordinator
from tests.test_trade_lifecycle_v1_models import request


def opened_coordinator():
    item = coordinator()
    item.start()
    item.process(request())
    item.confirm_execution_fill(fill_quantity=2, fill_price=108.0)
    return item


def test_position_update_objective_partial_and_full_close():
    item = opened_coordinator()
    pos = item.snapshot().position_result.position
    updated = item.update_position_price(PositionPriceUpdate(Instrument.NIFTY, pos.updated_at + timedelta(minutes=1), pos.average_entry_price + 10))
    assert updated.stage is TradeLifecycleStage.POSITION_OPEN
    partial = item.partial_exit_position(quantity=1, exit_price=pos.average_entry_price + 10)
    assert partial.stage is TradeLifecycleStage.POSITION_PARTIALLY_CLOSED or partial.stage is TradeLifecycleStage.POSITION_OPEN
    if item.snapshot().position_snapshot.has_open_position:
        closed = item.close_position(exit_price=pos.average_entry_price + 10)
        assert closed.stage is TradeLifecycleStage.POSITION_CLOSED


def test_invalidation_closes_position():
    item = opened_coordinator()
    pos = item.snapshot().position_result.position
    closed = item.update_position_price(PositionPriceUpdate(Instrument.NIFTY, pos.updated_at + timedelta(minutes=1), pos.invalidation_price))
    assert closed.stage is TradeLifecycleStage.POSITION_CLOSED
