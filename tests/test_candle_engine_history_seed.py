"""
Tests for Candle Engine historical seeding.
"""

from datetime import UTC, datetime, timedelta

import pytest

from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import CANDLE_CLOSED, CANDLE_OPENED, CANDLE_UPDATED
from core.models.candle import Candle
from core.models.tick import Tick
from engines.candle.candle_engine import CandleEngine


TS = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


def candle(offset=0, *, symbol=Instrument.NIFTY, timeframe="1m", close=101.0):
    start = TS + timedelta(minutes=offset)
    return Candle(symbol.value, timeframe, start, start + timedelta(minutes=1), 100.0, 102.0, 99.0, close, 10)


def tick(at):
    return Tick(Instrument.NIFTY, Exchange.NSE, at, 100.0, 1, 99.0, 101.0, 0)


def test_seed_empty_chronological_sort_duplicates_replace_and_events():
    bus = EventBus()
    events = []
    for name in (CANDLE_OPENED, CANDLE_UPDATED, CANDLE_CLOSED):
        bus.subscribe(name, events.append)
    engine = CandleEngine(bus)
    accepted = engine.seed_history(Instrument.NIFTY, (candle(1), candle(0), candle(0)))
    assert accepted == (candle(0), candle(1))
    assert engine.get_history(Instrument.NIFTY) == [candle(0), candle(1)]
    assert events == []
    assert engine.seed_history(Instrument.NIFTY, (candle(0),)) == ()
    assert engine.seed_history(Instrument.NIFTY, (candle(2),)) == (candle(2),)
    replacement = engine.seed_history(Instrument.NIFTY, (candle(4), candle(3)), replace=True)
    assert replacement == (candle(3), candle(4))
    assert engine.get_history(Instrument.NIFTY) == [candle(3), candle(4)]
    with pytest.raises(AttributeError):
        accepted[0] = candle(9)


def test_seed_rejects_invalid_conflicts_overlap_and_preserves_other_instruments():
    engine = CandleEngine(EventBus())
    engine.seed_history(Instrument.NIFTY, (candle(0),))
    bank = Candle("BANKNIFTY", "1m", TS, TS + timedelta(minutes=1), 1, 2, 1, 1, 1)
    engine.seed_history(Instrument.BANKNIFTY, (bank,))
    with pytest.raises(ValueError):
        engine.seed_history(Instrument.NIFTY, (candle(0, close=101.5),))
    with pytest.raises(ValueError):
        engine.seed_history(Instrument.NIFTY, (candle(2, symbol=Instrument.BANKNIFTY),))
    with pytest.raises(ValueError):
        engine.seed_history(Instrument.NIFTY, (candle(2, timeframe="5m"),))
    naive = Candle("NIFTY", "1m", datetime(2026, 7, 10, 9, 17), datetime(2026, 7, 10, 9, 18), 1, 2, 1, 1, 1)
    with pytest.raises(ValueError):
        engine.seed_history(Instrument.NIFTY, (naive,))
    invalid_duration = Candle("NIFTY", "1m", TS + timedelta(minutes=2), TS + timedelta(minutes=4), 1, 2, 1, 1, 1)
    with pytest.raises(ValueError):
        engine.seed_history(Instrument.NIFTY, (invalid_duration,))
    engine.on_tick(tick(TS + timedelta(minutes=3, seconds=1)))
    with pytest.raises(ValueError):
        engine.seed_history(Instrument.NIFTY, (candle(3),))
    assert engine.get_history(Instrument.BANKNIFTY) == [bank]


def test_replace_atomicity_and_live_tick_behavior_unchanged():
    engine = CandleEngine(EventBus())
    engine.seed_history(Instrument.NIFTY, (candle(0),))
    with pytest.raises(ValueError):
        engine.seed_history(Instrument.NIFTY, (candle(1), candle(1, close=100.5)), replace=True)
    assert engine.get_history(Instrument.NIFTY) == [candle(0)]
    engine.on_tick(tick(datetime(2026, 7, 10, 9, 20, 1)))
    current = engine.on_tick(tick(datetime(2026, 7, 10, 9, 20, 30)))
    assert current.volume == 2
