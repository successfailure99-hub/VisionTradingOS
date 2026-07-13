"""
Tests for ApplicationOrchestrator historical warm-up APIs.
"""

from datetime import UTC, datetime, timedelta

import pytest

from application import ApplicationOrchestrator, RuntimeSnapshot
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import MARKET_UPDATED, NEW_TICK
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick


TS = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


def candle(offset=0):
    start = TS + timedelta(minutes=offset)
    return Candle("NIFTY", "1m", start, start + timedelta(minutes=1), 100.0, 102.0, 99.0, 101.0, 10)


def tick(at):
    return Tick(Instrument.NIFTY, Exchange.NSE, at, 105.0, 1, 104.0, 106.0, 0)


def test_requires_running_rejects_unsupported_and_delegates_without_market_events():
    bus = EventBus()
    market_events = []
    bus.subscribe(NEW_TICK, market_events.append)
    bus.subscribe(MARKET_UPDATED, market_events.append)
    orchestrator = ApplicationOrchestrator(bus)
    with pytest.raises(RuntimeError):
        orchestrator.warm_up_candles("NIFTY", (candle(),))
    orchestrator.start()
    accepted, snapshot = orchestrator.warm_up_candles("nifty", (candle(0), candle(1)))
    assert accepted == (candle(0), candle(1))
    assert isinstance(snapshot, RuntimeSnapshot)
    assert snapshot.vwap is None
    assert orchestrator.get_candle_history("NIFTY") == accepted
    assert market_events == []
    with pytest.raises(ValueError):
        orchestrator.warm_up_candles("BANKNIFTY", (candle(),))
    later = orchestrator.process_tick(tick(TS + timedelta(minutes=2, seconds=1)))
    assert later.latest_tick is not None
    assert later.vwap is not None


def test_existing_daily_ohlc_behavior_unchanged():
    orchestrator = ApplicationOrchestrator(EventBus())
    orchestrator.start()
    cpr, camarilla = orchestrator.process_daily_ohlc("NIFTY", DailyOHLC(TS.date(), 100.0, 110.0, 90.0, 105.0))
    assert cpr is not None
    assert camarilla is not None
