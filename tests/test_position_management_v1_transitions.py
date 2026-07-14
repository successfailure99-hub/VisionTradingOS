from datetime import timedelta

from core.enums.instrument import Instrument
from engines.position_management_v1 import (
    PositionChange,
    PositionExitReason,
    PositionManagementV1Configuration,
    PositionManagementV1Engine,
    PositionPriceUpdate,
)
from tests.test_position_management_v1_models import filled_execution


def test_open_price_partial_closed_and_invalidation_transitions():
    engine = PositionManagementV1Engine(instrument=Instrument.NIFTY)
    opened = engine.open_from_execution(filled_execution())
    updated = engine.update_price(PositionPriceUpdate(Instrument.NIFTY, opened.position.updated_at + timedelta(minutes=1), opened.position.average_entry_price + 2))
    partial = engine.partial_exit(quantity=1, exit_price=updated.position.current_price)
    closed = engine.close(exit_price=partial.position.current_price + 1)

    assert opened.change is PositionChange.OPENED
    assert updated.change is PositionChange.PRICE_UPDATED
    assert partial.change is PositionChange.PARTIALLY_CLOSED
    assert closed.change is PositionChange.CLOSED

    invalidation_engine = PositionManagementV1Engine(instrument=Instrument.NIFTY)
    pos = invalidation_engine.open_from_execution(filled_execution()).position
    invalidated = invalidation_engine.update_price(PositionPriceUpdate(Instrument.NIFTY, pos.updated_at + timedelta(minutes=1), pos.invalidation_price))
    assert invalidated.change is PositionChange.INVALIDATED


def test_objective_reached_to_partial_and_full_objective_exit():
    objective = PositionManagementV1Engine(instrument=Instrument.NIFTY)
    pos = objective.open_from_execution(filled_execution()).position
    reached = objective.update_price(PositionPriceUpdate(Instrument.NIFTY, pos.updated_at + timedelta(minutes=1), pos.objective_price))
    assert reached.change is PositionChange.OBJECTIVE_REACHED
    partial = objective.partial_exit(quantity=1, exit_price=pos.objective_price, reason=PositionExitReason.OBJECTIVE)
    assert partial.change is PositionChange.PARTIALLY_CLOSED
    closed = objective.close(exit_price=pos.objective_price, reason=PositionExitReason.OBJECTIVE)
    assert closed.change is PositionChange.CLOSED

    full_auto = PositionManagementV1Engine(
        instrument=Instrument.NIFTY,
        configuration=PositionManagementV1Configuration(auto_full_exit_on_objective=True),
    )
    pos = full_auto.open_from_execution(filled_execution()).position
    result = full_auto.update_price(PositionPriceUpdate(Instrument.NIFTY, pos.updated_at + timedelta(minutes=1), pos.objective_price))
    assert result.change is PositionChange.CLOSED
