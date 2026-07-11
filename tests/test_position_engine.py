"""
Tests for Position Management Engine V1.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from math import inf, nan

import pytest

import engines.position as position_exports
from core.event_bus import EventBus
from core.events import POSITION_CLOSED, POSITION_OPENED, POSITION_UPDATED
from engines.order_management.enums import OrderSide
from engines.position import (
    PositionCalculator,
    PositionEngine,
    PositionFill,
    PositionMark,
    PositionSide,
    PositionState,
    PositionStatus,
    PositionUpdateType,
)


TS = datetime(2026, 7, 11, 9, 15)


class RecordingBus(EventBus):
    def __init__(self):
        super().__init__()
        self.events = []

    def publish(self, event_name, data=None):
        self.events.append((event_name, data))
        super().publish(event_name, data)


def engine(symbol="NIFTY", exchange="NSE", timeframe="1m"):
    bus = RecordingBus()
    return PositionEngine(bus, symbol, exchange, timeframe), bus


def fill(
    execution_id="exec-1",
    side=OrderSide.BUY,
    quantity=10,
    price=100.0,
    timestamp=TS,
    symbol="NIFTY",
    exchange="NSE",
    timeframe="1m",
    client_order_id="client-1",
    broker_order_id="broker-1",
):
    return PositionFill(
        execution_id=execution_id,
        client_order_id=client_order_id,
        broker_order_id=broker_order_id,
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        timestamp=timestamp,
        side=side,
        quantity=quantity,
        price=price,
    )


def mark(price=105.0, timestamp=TS, symbol="NIFTY", exchange="NSE", timeframe="1m"):
    return PositionMark(
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        timestamp=timestamp,
        mark_price=price,
    )


def test_enums_models_slots_frozen_exports_and_normalization():
    assert PositionSide.LONG.value == "long"
    assert PositionSide.SHORT.value == "short"
    assert PositionSide.FLAT.value == "flat"
    assert PositionStatus.OPEN.value == "open"
    assert PositionStatus.CLOSED.value == "closed"
    assert PositionUpdateType.REVERSE.value == "reverse"

    assert position_exports.__all__ == [
        "PositionEngine",
        "PositionCalculator",
        "PositionFill",
        "PositionMark",
        "PositionState",
        "PositionSide",
        "PositionStatus",
        "PositionUpdateType",
    ]
    assert PositionCalculator is position_exports.PositionCalculator

    position_fill = fill(symbol=" nifty ", exchange=" nse ", timeframe=" 1m ")
    position_mark = mark(symbol=" banknifty ", exchange=" nfo ", timeframe=" 5m ")
    assert position_fill.symbol == "NIFTY"
    assert position_fill.exchange == "NSE"
    assert position_fill.timeframe == "1m"
    assert position_mark.symbol == "BANKNIFTY"
    assert position_mark.exchange == "NFO"
    assert position_mark.timeframe == "5m"
    assert hasattr(position_fill, "__slots__")
    assert hasattr(position_mark, "__slots__")

    with pytest.raises(FrozenInstanceError):
        position_fill.quantity = 99


def test_constructor_normalization_initial_state_and_invalid_context():
    position_engine, _ = engine(" nifty ", " nse ", " 1m ")
    assert position_engine.symbol == "NIFTY"
    assert position_engine.exchange == "NSE"
    assert position_engine.timeframe == "1m"
    assert position_engine.state is None
    assert position_engine.data is None
    assert position_engine.latest_mark is None
    assert position_engine.processed_execution_count == 0
    assert position_engine.is_ready() is False

    for args in [("", "NSE", "1m"), ("NIFTY", "", "1m"), ("NIFTY", "NSE", "")]:
        with pytest.raises(ValueError):
            PositionEngine(RecordingBus(), *args)


def test_fill_validation_is_atomic_for_type_context_fields_numbers_side_and_timestamp():
    position_engine, bus = engine()
    before = (position_engine.state, position_engine.data, position_engine.processed_execution_count)

    invalid_cases = [
        lambda: position_engine.apply_fill(object()),
        lambda: position_engine.apply_fill(fill(symbol="BANKNIFTY")),
        lambda: position_engine.apply_fill(fill(exchange="NFO")),
        lambda: position_engine.apply_fill(fill(timeframe="5m")),
        lambda: position_engine.apply_fill(fill(execution_id="")),
        lambda: position_engine.apply_fill(fill(client_order_id="")),
        lambda: position_engine.apply_fill(fill(side="buy")),
        lambda: position_engine.apply_fill(fill(quantity=0)),
        lambda: position_engine.apply_fill(fill(quantity=-1)),
        lambda: position_engine.apply_fill(fill(quantity=True)),
        lambda: position_engine.apply_fill(fill(price=0.0)),
        lambda: position_engine.apply_fill(fill(price=nan)),
        lambda: position_engine.apply_fill(fill(price=inf)),
        lambda: position_engine.apply_fill(fill(timestamp="bad")),
    ]
    for invalid in invalid_cases:
        with pytest.raises((TypeError, ValueError)):
            invalid()
        assert (position_engine.state, position_engine.data, position_engine.processed_execution_count) == before
        assert bus.events == []

    aware = fill(execution_id="aware", timestamp=datetime(2026, 7, 11, 9, 15, tzinfo=timezone.utc))
    position_engine.apply_fill(aware)
    with pytest.raises(ValueError):
        position_engine.apply_fill(fill(execution_id="naive", timestamp=datetime(2026, 7, 11, 9, 16)))


def test_buy_opens_long_and_sell_opens_short_with_open_event_after_assignment():
    position_engine, bus = engine()
    state = position_engine.apply_fill(fill())
    assert state.side is PositionSide.LONG
    assert state.status is PositionStatus.OPEN
    assert state.opened_at == TS
    assert state.updated_at == TS
    assert state.closed_at is None
    assert state.net_quantity == 10
    assert state.absolute_quantity == 10
    assert state.average_entry_price == 100.0
    assert state.version == 1
    assert state.total_buy_quantity == 10
    assert state.total_sell_quantity == 0
    assert state.last_update_type is PositionUpdateType.OPEN
    assert position_engine.data is state
    assert position_engine.is_ready() is True
    assert bus.events == [(POSITION_OPENED, state)]
    assert bus.events[0][1] is position_engine.state

    short_engine, short_bus = engine()
    short_state = short_engine.apply_fill(fill(side=OrderSide.SELL))
    assert short_state.side is PositionSide.SHORT
    assert short_state.net_quantity == -10
    assert short_state.average_entry_price == 100.0
    assert short_state.total_buy_quantity == 0
    assert short_state.total_sell_quantity == 10
    assert short_bus.events == [(POSITION_OPENED, short_state)]


def test_adding_to_long_and_short_uses_weighted_average_and_updated_event():
    position_engine, bus = engine()
    first = position_engine.apply_fill(fill(quantity=3, price=100.0))
    second = position_engine.apply_fill(fill(execution_id="exec-2", quantity=7, price=101.0, timestamp=TS))
    assert first.realized_pnl == 0.0
    assert second.net_quantity == 10
    assert second.average_entry_price == 100.7
    assert second.realized_pnl == 0.0
    assert second.last_update_type is PositionUpdateType.ADD
    assert second.version == 2
    assert bus.events[-1] == (POSITION_UPDATED, second)

    short_engine, _ = engine()
    short_engine.apply_fill(fill(side=OrderSide.SELL, quantity=3, price=100.0))
    short = short_engine.apply_fill(fill(execution_id="exec-2", side=OrderSide.SELL, quantity=7, price=101.0))
    assert short.net_quantity == -10
    assert short.average_entry_price == 100.7
    assert short.last_update_type is PositionUpdateType.ADD


def test_reducing_long_partial_full_profit_loss_and_closed_event():
    position_engine, bus = engine()
    position_engine.apply_fill(fill(quantity=10, price=100.0))
    partial_profit = position_engine.apply_fill(fill("exec-2", OrderSide.SELL, 4, 110.0, TS))
    assert partial_profit.net_quantity == 6
    assert partial_profit.average_entry_price == 100.0
    assert partial_profit.realized_pnl == 40.0
    assert partial_profit.last_update_type is PositionUpdateType.REDUCE
    assert bus.events[-1] == (POSITION_UPDATED, partial_profit)

    partial_loss = position_engine.apply_fill(fill("exec-3", OrderSide.SELL, 1, 95.0, TS))
    assert partial_loss.net_quantity == 5
    assert partial_loss.realized_pnl == 35.0
    assert partial_loss.average_entry_price == 100.0

    closed = position_engine.apply_fill(fill("exec-4", OrderSide.SELL, 5, 101.0, TS))
    assert closed.side is PositionSide.FLAT
    assert closed.status is PositionStatus.CLOSED
    assert closed.net_quantity == 0
    assert closed.absolute_quantity == 0
    assert closed.average_entry_price is None
    assert closed.unrealized_pnl == 0.0
    assert closed.closed_at == TS
    assert closed.realized_pnl == 40.0
    assert closed.last_update_type is PositionUpdateType.CLOSE
    assert position_engine.is_ready() is True
    assert bus.events[-1] == (POSITION_CLOSED, closed)


def test_reducing_short_partial_full_profit_loss_and_closed_event():
    position_engine, bus = engine()
    position_engine.apply_fill(fill(side=OrderSide.SELL, quantity=10, price=100.0))
    partial_profit = position_engine.apply_fill(fill("exec-2", OrderSide.BUY, 4, 90.0, TS))
    assert partial_profit.net_quantity == -6
    assert partial_profit.average_entry_price == 100.0
    assert partial_profit.realized_pnl == 40.0
    assert bus.events[-1] == (POSITION_UPDATED, partial_profit)

    partial_loss = position_engine.apply_fill(fill("exec-3", OrderSide.BUY, 1, 105.0, TS))
    assert partial_loss.net_quantity == -5
    assert partial_loss.realized_pnl == 35.0
    assert partial_loss.average_entry_price == 100.0

    closed = position_engine.apply_fill(fill("exec-4", OrderSide.BUY, 5, 99.0, TS))
    assert closed.side is PositionSide.FLAT
    assert closed.status is PositionStatus.CLOSED
    assert closed.realized_pnl == 40.0
    assert closed.last_update_type is PositionUpdateType.CLOSE
    assert bus.events[-1] == (POSITION_CLOSED, closed)


def test_reversal_long_to_short_and_short_to_long_is_atomic_open_event():
    position_engine, bus = engine()
    position_engine.apply_fill(fill(quantity=50, price=100.0))
    reversed_state = position_engine.apply_fill(fill("exec-2", OrderSide.SELL, 80, 90.0, TS))
    assert reversed_state.side is PositionSide.SHORT
    assert reversed_state.net_quantity == -30
    assert reversed_state.absolute_quantity == 30
    assert reversed_state.realized_pnl == -500.0
    assert reversed_state.average_entry_price == 90.0
    assert reversed_state.opened_at == TS
    assert reversed_state.closed_at is None
    assert reversed_state.version == 2
    assert reversed_state.total_buy_quantity == 50
    assert reversed_state.total_sell_quantity == 80
    assert reversed_state.last_update_type is PositionUpdateType.REVERSE
    assert bus.events[-1] == (POSITION_OPENED, reversed_state)
    assert len(bus.events) == 2

    short_engine, _ = engine()
    short_engine.apply_fill(fill(side=OrderSide.SELL, quantity=50, price=100.0))
    long_state = short_engine.apply_fill(fill("exec-2", OrderSide.BUY, 80, 110.0, TS))
    assert long_state.side is PositionSide.LONG
    assert long_state.net_quantity == 30
    assert long_state.realized_pnl == -500.0
    assert long_state.average_entry_price == 110.0


def test_mark_to_market_for_long_short_flat_rounding_duplicate_and_event_behavior():
    position_engine, bus = engine()
    with pytest.raises(ValueError):
        position_engine.apply_mark(mark())

    position_engine.apply_fill(fill(quantity=3, price=100.3333))
    long_mark = position_engine.apply_mark(mark(price=101.7777))
    assert long_mark.unrealized_pnl == 4.33
    assert long_mark.total_pnl == 4.33
    assert long_mark.net_quantity == 3
    assert long_mark.realized_pnl == 0.0
    assert long_mark.last_update_type is PositionUpdateType.MARK
    assert position_engine.latest_mark == mark(price=101.7777)
    assert bus.events[-1] == (POSITION_UPDATED, long_mark)

    duplicate = position_engine.apply_mark(mark(price=101.7777))
    assert duplicate is long_mark
    assert len(bus.events) == 2

    same_timestamp_new_price = position_engine.apply_mark(mark(price=99.0))
    assert same_timestamp_new_price.version == 3
    assert same_timestamp_new_price.unrealized_pnl == -4.0

    position_engine.apply_fill(fill("exec-2", OrderSide.SELL, 3, 101.0, TS))
    flat_mark = position_engine.apply_mark(mark(price=80.0, timestamp=TS))
    assert flat_mark.side is PositionSide.FLAT
    assert flat_mark.mark_price == 80.0
    assert flat_mark.unrealized_pnl == 0.0

    short_engine, _ = engine()
    short_engine.apply_fill(fill(side=OrderSide.SELL, quantity=5, price=100.0))
    short_profit = short_engine.apply_mark(mark(price=90.0))
    short_loss = short_engine.apply_mark(mark(price=110.0, timestamp=TS))
    assert short_profit.unrealized_pnl == 50.0
    assert short_loss.unrealized_pnl == -50.0


def test_duplicate_execution_ids_are_suppressed_after_close_and_reusable_after_reset():
    position_engine, bus = engine()
    opened = position_engine.apply_fill(fill())
    duplicate = position_engine.apply_fill(fill(price=200.0))
    assert duplicate is opened
    assert duplicate.total_buy_quantity == 10
    assert position_engine.processed_execution_count == 1
    assert len(bus.events) == 1

    closed = position_engine.apply_fill(fill("exec-2", OrderSide.SELL, 10, 110.0))
    duplicate_after_close = position_engine.apply_fill(fill("exec-2", OrderSide.SELL, 10, 110.0))
    assert duplicate_after_close is closed
    assert len(bus.events) == 2

    position_engine.reset()
    reused = position_engine.apply_fill(fill("exec-1", OrderSide.SELL, 1, 50.0, datetime(2020, 1, 1)))
    assert reused.version == 1
    assert position_engine.processed_execution_count == 1


def test_timestamp_ordering_same_timestamp_acceptance_and_reset():
    position_engine, _ = engine()
    position_engine.apply_fill(fill(timestamp=datetime(2026, 7, 11, 9, 15)))
    with pytest.raises(ValueError):
        position_engine.apply_fill(fill("exec-2", timestamp=datetime(2026, 7, 11, 9, 14)))

    same_timestamp = position_engine.apply_fill(fill("exec-3", side=OrderSide.BUY, timestamp=datetime(2026, 7, 11, 9, 15)))
    assert same_timestamp.version == 2
    position_engine.apply_mark(mark(timestamp=datetime(2026, 7, 11, 9, 15)))
    with pytest.raises(ValueError):
        position_engine.apply_mark(mark(timestamp=datetime(2026, 7, 11, 9, 14)))

    position_engine.reset()
    earlier = position_engine.apply_fill(fill("exec-4", timestamp=datetime(2020, 1, 1)))
    assert earlier.version == 1


def test_state_consistency_data_identity_aliases_independence_and_clear_reset():
    position_engine, bus = engine()
    original_fill = fill(symbol=" nifty ", exchange=" nse ")
    state = position_engine.process_fill(original_fill)
    assert original_fill.symbol == "NIFTY"
    assert state.absolute_quantity == abs(state.net_quantity)
    assert state.side is PositionSide.LONG
    assert position_engine.data is position_engine.state

    marked = position_engine.process_mark(mark())
    assert marked is position_engine.state

    other_engine, other_bus = engine("BANKNIFTY", "NSE", "1m")
    other_state = other_engine.apply_fill(fill(symbol="BANKNIFTY", quantity=99))
    assert other_state.net_quantity == 99
    assert position_engine.state.net_quantity == 10
    assert other_bus.events == [(POSITION_OPENED, other_state)]

    event_count = len(bus.events)
    position_engine.clear()
    assert position_engine.state is None
    assert position_engine.data is None
    assert position_engine.latest_mark is None
    assert position_engine.processed_execution_count == 0
    assert position_engine.is_ready() is False
    assert len(bus.events) == event_count

    position_engine.apply_fill(fill(timestamp=datetime(2020, 1, 1)))
    position_engine.reset()
    assert position_engine.state is None
    assert len(bus.events) == event_count + 1


def test_no_broker_network_dependency_in_position_engine_source():
    import inspect

    import engines.position.position_engine as position_engine_module

    source = inspect.getsource(position_engine_module)
    forbidden = ("requests", "websocket", "kiteconnect", "socket", "http")
    assert all(token not in source.lower() for token in forbidden)
