"""
====================================================
Vision Trading OS
Test - Candle Engine
====================================================
"""

from datetime import datetime

from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import (
    CANDLE_CLOSED,
    CANDLE_OPENED,
    CANDLE_UPDATED,
)
from core.models.candle import Candle
from core.models.tick import Tick
from engines.candle.candle_engine import CandleEngine


def make_tick(
    timestamp: datetime,
    price: float,
    volume: int = 10,
    instrument: Instrument = Instrument.NIFTY,
) -> Tick:
    return Tick(
        symbol=instrument,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=volume,
        bid_price=price - 1,
        ask_price=price + 1,
        open_interest=1000,
    )


def test_opens_and_updates_one_minute_candle():
    event_bus = EventBus()
    opened = []
    updated = []

    event_bus.subscribe(CANDLE_OPENED, opened.append)
    event_bus.subscribe(CANDLE_UPDATED, updated.append)

    engine = CandleEngine(event_bus)

    first = make_tick(
        datetime(2026, 7, 10, 9, 15, 12),
        25200,
        100,
    )
    second = make_tick(
        datetime(2026, 7, 10, 9, 15, 45),
        25220,
        50,
    )

    engine.on_tick(first)
    candle = engine.on_tick(second)

    assert candle.start_time == datetime(2026, 7, 10, 9, 15)
    assert candle.end_time == datetime(2026, 7, 10, 9, 16)
    assert candle.open == 25200
    assert candle.high == 25220
    assert candle.low == 25200
    assert candle.close == 25220
    assert candle.volume == 150
    assert engine.get_current(Instrument.NIFTY) is candle
    assert len(opened) == 1
    assert len(updated) == 1


def test_closes_completed_candle_and_opens_next():
    event_bus = EventBus()
    closed = []
    opened = []

    event_bus.subscribe(CANDLE_CLOSED, closed.append)
    event_bus.subscribe(CANDLE_OPENED, opened.append)

    engine = CandleEngine(event_bus)

    engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 1), 25200, 100)
    )
    engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 30), 25190, 25)
    )
    current = engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 16, 0), 25210, 75)
    )

    history = engine.get_history(Instrument.NIFTY)

    assert len(history) == 1
    assert len(closed) == 1
    assert len(opened) == 2
    assert isinstance(closed[0], Candle)
    assert history[0] == closed[0]
    assert history[0].start_time == datetime(2026, 7, 10, 9, 15)
    assert history[0].end_time == datetime(2026, 7, 10, 9, 16)
    assert history[0].open == 25200
    assert history[0].high == 25200
    assert history[0].low == 25190
    assert history[0].close == 25190
    assert history[0].volume == 125
    assert current.start_time == datetime(2026, 7, 10, 9, 16)
    assert current.open == 25210


def test_clear_removes_candle_state():
    engine = CandleEngine(EventBus())

    engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 1), 25200)
    )
    engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 16, 1), 25210)
    )

    assert engine.is_ready()
    assert engine.get_current(Instrument.NIFTY) is not None
    assert engine.get_history(Instrument.NIFTY)

    engine.clear()

    assert not engine.is_ready()
    assert engine.get_current(Instrument.NIFTY) is None
    assert engine.get_history(Instrument.NIFTY) == []


def test_multiple_instruments_maintain_independent_candles_and_history():
    engine = CandleEngine(EventBus())

    engine.on_tick(
        make_tick(
            datetime(2026, 7, 10, 9, 15, 5),
            25200,
            100,
            Instrument.NIFTY,
        )
    )
    engine.on_tick(
        make_tick(
            datetime(2026, 7, 10, 9, 15, 10),
            56200,
            200,
            Instrument.BANKNIFTY,
        )
    )
    engine.on_tick(
        make_tick(
            datetime(2026, 7, 10, 9, 16, 1),
            25210,
            50,
            Instrument.NIFTY,
        )
    )

    nifty_history = engine.get_history(Instrument.NIFTY)
    banknifty_history = engine.get_history(Instrument.BANKNIFTY)

    assert len(nifty_history) == 1
    assert len(banknifty_history) == 0
    assert nifty_history[0].symbol == Instrument.NIFTY.value
    assert engine.get_current(Instrument.NIFTY).open == 25210
    assert engine.get_current(Instrument.BANKNIFTY).open == 56200


def test_duplicate_ticks_are_applied_as_normal_updates():
    event_bus = EventBus()
    updated = []
    event_bus.subscribe(CANDLE_UPDATED, updated.append)

    engine = CandleEngine(event_bus)
    tick = make_tick(datetime(2026, 7, 10, 9, 15, 12), 25200, 100)

    engine.on_tick(tick)
    candle = engine.on_tick(tick)

    assert candle.open == 25200
    assert candle.high == 25200
    assert candle.low == 25200
    assert candle.close == 25200
    assert candle.volume == 200
    assert len(updated) == 1


def test_out_of_order_tick_preserves_current_serialized_behavior():
    engine = CandleEngine(EventBus())

    engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 50), 25220, 100)
    )
    candle = engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 10), 25200, 50)
    )

    assert candle.start_time == datetime(2026, 7, 10, 9, 15)
    assert candle.open == 25220
    assert candle.high == 25220
    assert candle.low == 25200
    assert candle.close == 25200
    assert candle.volume == 150


def test_tick_exactly_on_minute_boundary_opens_next_candle():
    event_bus = EventBus()
    opened = []
    closed = []

    event_bus.subscribe(CANDLE_OPENED, opened.append)
    event_bus.subscribe(CANDLE_CLOSED, closed.append)

    engine = CandleEngine(event_bus)

    engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 59), 25200, 100)
    )
    current = engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 16, 0), 25210, 50)
    )

    assert len(closed) == 1
    assert len(opened) == 2
    assert closed[0].start_time == datetime(2026, 7, 10, 9, 15)
    assert closed[0].end_time == datetime(2026, 7, 10, 9, 16)
    assert current.start_time == datetime(2026, 7, 10, 9, 16)
    assert current.open == 25210


def test_large_price_movement_updates_high_and_low():
    engine = CandleEngine(EventBus())

    engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 1), 25200, 100)
    )
    engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 20), 26000, 25)
    )
    candle = engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 40), 24000, 25)
    )

    assert candle.open == 25200
    assert candle.high == 26000
    assert candle.low == 24000
    assert candle.close == 24000
    assert candle.volume == 150


def test_zero_volume_tick_updates_price_without_adding_volume():
    event_bus = EventBus()
    updated = []
    event_bus.subscribe(CANDLE_UPDATED, updated.append)

    engine = CandleEngine(event_bus)

    engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 1), 25200, 100)
    )
    candle = engine.on_tick(
        make_tick(datetime(2026, 7, 10, 9, 15, 30), 25225, 0)
    )

    assert candle.high == 25225
    assert candle.close == 25225
    assert candle.volume == 100
    assert len(updated) == 1
