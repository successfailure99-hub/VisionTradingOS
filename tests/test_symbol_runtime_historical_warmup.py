"""
Tests for SymbolRuntime historical warm-up.
"""

from datetime import UTC, datetime, timedelta

import pytest

from application import RuntimeConfiguration, RuntimeInstrument, RuntimeStatus, SymbolRuntime
from core.event_bus import EventBus
from core.models.candle import Candle


TS = datetime(2026, 7, 10, 9, 15, tzinfo=UTC)


def candle(offset=0, *, symbol="NIFTY", timeframe="1m"):
    start = TS + timedelta(minutes=offset)
    return Candle(symbol, timeframe, start, start + timedelta(minutes=1), 100.0, 102.0, 99.0, 101.0 + offset, 10)


def runtime():
    item = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    item.start()
    return item


def test_requires_running_symbol_and_one_minute():
    item = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    with pytest.raises(RuntimeError):
        item.warm_up_candles((candle(),))
    item.start()
    with pytest.raises(ValueError):
        item.warm_up_candles((candle(symbol="BANKNIFTY"),))
    with pytest.raises(ValueError):
        item.warm_up_candles((candle(timeframe="5m"),))


def test_seeds_price_action_idempotently_and_leaves_live_state_untouched():
    item = runtime()
    accepted = item.warm_up_candles((candle(0), candle(1)))
    snapshot = item.snapshot()
    assert accepted == (candle(0), candle(1))
    assert item.get_candle_history() == accepted
    assert snapshot.status is RuntimeStatus.RUNNING
    assert snapshot.latest_tick is None
    assert snapshot.updated_at == candle(1).end_time
    assert snapshot.price_action is not None
    assert snapshot.vwap is None
    assert snapshot.market_context is None
    assert snapshot.ai_reasoning is None
    assert snapshot.strategy is None
    assert snapshot.risk is None
    assert snapshot.latest_order is None
    assert item.warm_up_candles((candle(0), candle(1))) == ()
    with pytest.raises(AttributeError):
        item.get_candle_history()[0] = candle(9)
