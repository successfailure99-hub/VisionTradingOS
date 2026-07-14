from datetime import timedelta
from threading import RLock

import pytest

from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import POSITION_OPENED_DRY_RUN, POSITION_PRICE_UPDATED
from engines.position_management_v1 import (
    PositionChange,
    PositionExitReason,
    PositionManagementV1Configuration,
    PositionManagementV1Engine,
    PositionPriceUpdate,
    PositionStatus,
)
from tests.test_position_management_v1_models import filled_execution


def test_constructor_empty_open_duplicate_second_position_events_and_rlock():
    events = []
    bus = EventBus()
    bus.subscribe(POSITION_OPENED_DRY_RUN, lambda payload: events.append("opened"))
    engine = PositionManagementV1Engine(instrument=Instrument.NIFTY, event_bus=bus)
    result = filled_execution()

    assert engine.snapshot().has_open_position is False
    opened = engine.open_from_execution(result)
    assert opened.change is PositionChange.OPENED
    assert engine.open_from_execution(result) is opened
    with pytest.raises(RuntimeError):
        engine.open_from_execution(filled_execution())
    assert engine.snapshot().opened_count == 1
    assert events == ["opened"]
    assert isinstance(engine._lock, RLock().__class__)


def test_price_duplicate_correction_stale_objective_partial_close_clear_and_isolation():
    events = []
    bus = EventBus()
    bus.subscribe(POSITION_PRICE_UPDATED, lambda payload: events.append("price"))
    engine = PositionManagementV1Engine(instrument=Instrument.NIFTY, event_bus=bus)
    opened = engine.open_from_execution(filled_execution())
    pos = opened.position
    update = PositionPriceUpdate(Instrument.NIFTY, pos.updated_at + timedelta(minutes=1), pos.average_entry_price + 1)
    first = engine.update_price(update)

    assert engine.update_price(update) is first
    corrected = engine.update_price(PositionPriceUpdate(Instrument.NIFTY, update.timestamp, pos.average_entry_price + 2))
    assert corrected is not first
    with pytest.raises(ValueError):
        engine.update_price(PositionPriceUpdate(Instrument.NIFTY, pos.updated_at - timedelta(minutes=1), pos.average_entry_price))

    partial = engine.partial_exit(quantity=1, exit_price=pos.average_entry_price + 3)
    assert partial.change is PositionChange.PARTIALLY_CLOSED
    closed = engine.close(exit_price=pos.average_entry_price + 4)
    assert closed.position.status is PositionStatus.CLOSED
    assert engine.snapshot().has_open_position is False
    assert engine.history()
    engine.clear()
    assert engine.history() == ()
    assert PositionManagementV1Engine(instrument=Instrument.BANKNIFTY).snapshot().has_open_position is False
    with pytest.raises(ValueError):
        PositionManagementV1Engine(instrument=Instrument.SBI)


def test_invalidation_auto_exit_and_objective_reached_default_behavior():
    invalidation_engine = PositionManagementV1Engine(instrument=Instrument.NIFTY)
    pos = invalidation_engine.open_from_execution(filled_execution()).position
    invalidated = invalidation_engine.update_price(PositionPriceUpdate(Instrument.NIFTY, pos.updated_at + timedelta(minutes=1), pos.invalidation_price))
    assert invalidated.change is PositionChange.INVALIDATED
    assert invalidation_engine.snapshot().invalidation_exit_count == 1

    objective_engine = PositionManagementV1Engine(instrument=Instrument.NIFTY)
    pos = objective_engine.open_from_execution(filled_execution()).position
    objective = objective_engine.update_price(PositionPriceUpdate(Instrument.NIFTY, pos.updated_at + timedelta(minutes=1), pos.objective_price))
    assert objective.change is PositionChange.OBJECTIVE_REACHED
    assert objective_engine.snapshot().has_open_position is True
