from datetime import UTC, date, datetime, timedelta

import pytest

from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import MARKET_CONTEXT_V2_READY, MARKET_CONTEXT_V2_UPDATED
from core.models.candle import Candle
from engines.market_context_v2 import (
    MarketContextV2Configuration,
    MarketContextV2Engine,
    MarketContextV2Input,
)
from engines.price_action.enums import BreakType, StructureType, SwingType, Trend
from engines.price_action.models import PriceActionState, StructureBreak, SwingPoint


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def price_action(ts=NOW):
    return PriceActionState(
        "NIFTY",
        "1m",
        10,
        Candle("NIFTY", "1m", ts, ts, 99.0, 101.0, 98.0, 100.0, 1000),
        Trend.BULLISH,
        SwingPoint("NIFTY", "1m", SwingType.HIGH, StructureType.HIGHER_HIGH, 101.0, ts, ts, 1),
        SwingPoint("NIFTY", "1m", SwingType.LOW, StructureType.HIGHER_LOW, 99.0, ts, ts, 1),
        None,
        None,
        StructureBreak(BreakType.BULLISH_BOS, 100.0, 101.0, ts, ts),
    )


def input_at(ts):
    return MarketContextV2Input(
        instrument=Instrument.NIFTY,
        timestamp=ts,
        current_price=100.0,
        price_action=price_action(ts),
        option_chain_analytics=None,
        camarilla=None,
        cpr=None,
        vwap=None,
    )


def test_constructor_initial_state_and_events():
    events = []
    bus = EventBus()
    bus.subscribe(MARKET_CONTEXT_V2_UPDATED, lambda payload: events.append(("updated", payload)))
    bus.subscribe(MARKET_CONTEXT_V2_READY, lambda payload: events.append(("ready", payload)))
    engine = MarketContextV2Engine(instrument=Instrument.NIFTY, event_bus=bus)
    assert engine.snapshot is None
    assert engine.previous_snapshot is None
    assert engine.is_ready is False
    result = engine.process(input_at(NOW))
    assert engine.snapshot is result
    assert engine.is_ready is True
    assert [name for name, _ in events] == ["updated", "ready"]


def test_duplicate_correction_stale_history_reset_and_clear():
    engine = MarketContextV2Engine(
        instrument=Instrument.NIFTY,
        configuration=MarketContextV2Configuration(history_limit=2),
    )
    first = engine.process(input_at(NOW))
    assert engine.update(input_at(NOW)) is first
    corrected_input = MarketContextV2Input(
        instrument=Instrument.NIFTY,
        timestamp=NOW,
        current_price=101.0,
        price_action=price_action(NOW),
        option_chain_analytics=None,
        camarilla=None,
        cpr=None,
        vwap=None,
    )
    corrected = engine.process(corrected_input)
    assert corrected is not first
    assert len(engine.history()) == 1
    second = engine.process(input_at(NOW + timedelta(minutes=1)))
    assert engine.previous_snapshot is corrected
    engine.process(input_at(NOW + timedelta(minutes=2)))
    assert len(engine.history()) == 2
    with pytest.raises(ValueError):
        engine.process(input_at(NOW - timedelta(minutes=1)))
    assert engine.snapshot is not None
    engine.reset()
    assert engine.snapshot is None
    assert engine.history() == ()
    engine.process(input_at(NOW))
    engine.clear()
    assert engine.is_ready is False


def test_wrong_instrument_and_independent_instances():
    with pytest.raises(ValueError):
        MarketContextV2Engine(instrument=Instrument.SBI)
    left = MarketContextV2Engine(instrument=Instrument.NIFTY)
    right = MarketContextV2Engine(instrument=Instrument.BANKNIFTY)
    left.process(input_at(NOW))
    assert right.snapshot is None
    with pytest.raises(ValueError):
        right.process(input_at(NOW))
