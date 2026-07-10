"""
====================================================
Vision Trading OS
Test - Market Data Engine
====================================================
"""

from dataclasses import replace
from datetime import datetime

from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import MARKET_UPDATED, NEW_TICK
from core.models.tick import Tick
from engines.candle.candle_engine import CandleEngine
from engines.market_data.market_data_engine import MarketDataEngine


def make_tick(
    timestamp: datetime = datetime(2026, 7, 10, 9, 15, 1),
    price: float = 25200,
    volume: int = 100,
    instrument: Instrument = Instrument.NIFTY,
    exchange: Exchange = Exchange.NSE,
    bid_price: float = 25199,
    ask_price: float = 25201,
    open_interest: int = 1000,
) -> Tick:
    return Tick(
        symbol=instrument,
        exchange=exchange,
        timestamp=timestamp,
        last_price=price,
        volume=volume,
        bid_price=bid_price,
        ask_price=ask_price,
        open_interest=open_interest,
    )


def assert_raises(expected_error, callback):
    try:
        callback()
    except expected_error:
        return

    raise AssertionError(f"Expected {expected_error.__name__}")


def test_first_valid_tick_is_accepted_and_cached():
    engine = MarketDataEngine(EventBus())
    tick = make_tick()

    result = engine.on_tick(tick)

    assert result == tick
    assert engine.get_latest(Instrument.NIFTY) == tick
    assert engine.data == tick
    assert engine.is_ready()


def test_new_tick_is_published_for_accepted_tick():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(NEW_TICK, received.append)
    engine = MarketDataEngine(event_bus)
    tick = make_tick()

    engine.on_tick(tick)

    assert received == [tick]


def test_market_updated_is_published_after_state_update():
    event_bus = EventBus()
    observed_latest = []
    engine = MarketDataEngine(event_bus)
    tick = make_tick()

    def on_market_updated(received_tick):
        observed_latest.append(
            (received_tick, engine.get_latest(received_tick.symbol))
        )

    event_bus.subscribe(MARKET_UPDATED, on_market_updated)

    engine.on_tick(tick)

    assert observed_latest == [(tick, tick)]


def test_multiple_instruments_maintain_independent_latest_ticks():
    engine = MarketDataEngine(EventBus())
    nifty = make_tick(instrument=Instrument.NIFTY, price=25200)
    banknifty = make_tick(
        instrument=Instrument.BANKNIFTY,
        price=56200,
    )

    engine.on_tick(nifty)
    engine.on_tick(banknifty)

    assert engine.get_latest(Instrument.NIFTY) == nifty
    assert engine.get_latest(Instrument.BANKNIFTY) == banknifty


def test_newer_tick_replaces_latest_for_same_instrument():
    engine = MarketDataEngine(EventBus())
    first = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=25200,
    )
    second = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 2),
        price=25210,
    )

    engine.on_tick(first)
    engine.on_tick(second)

    assert engine.get_latest(Instrument.NIFTY) == second
    assert engine.data == second


def test_exact_duplicate_is_ignored_and_publishes_no_events():
    event_bus = EventBus()
    events = []
    event_bus.subscribe(NEW_TICK, lambda tick: events.append(NEW_TICK))
    event_bus.subscribe(
        MARKET_UPDATED,
        lambda tick: events.append(MARKET_UPDATED),
    )
    engine = MarketDataEngine(event_bus)
    tick = make_tick()

    first_result = engine.on_tick(tick)
    duplicate_result = engine.on_tick(tick)

    assert first_result == tick
    assert duplicate_result is None
    assert engine.get_latest(Instrument.NIFTY) == tick
    assert events == [NEW_TICK, MARKET_UPDATED]


def test_stale_tick_is_rejected_and_does_not_alter_state():
    event_bus = EventBus()
    events = []
    event_bus.subscribe(NEW_TICK, events.append)
    event_bus.subscribe(MARKET_UPDATED, events.append)
    engine = MarketDataEngine(event_bus)
    latest = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 2),
        price=25210,
    )
    stale = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=25200,
    )

    engine.on_tick(latest)

    assert_raises(ValueError, lambda: engine.on_tick(stale))
    assert engine.get_latest(Instrument.NIFTY) == latest
    assert events == [latest, latest]


def test_equal_timestamp_non_identical_ticks_are_accepted_in_arrival_order():
    engine = MarketDataEngine(EventBus())
    first = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=25200,
    )
    second = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=25205,
    )

    engine.on_tick(first)
    result = engine.on_tick(second)

    assert result == second
    assert engine.get_latest(Instrument.NIFTY) == second


def test_invalid_input_type_is_rejected():
    engine = MarketDataEngine(EventBus())

    assert_raises(TypeError, lambda: engine.on_tick(object()))


def test_non_positive_last_price_is_rejected():
    engine = MarketDataEngine(EventBus())
    tick = make_tick(price=0)

    assert_raises(ValueError, lambda: engine.on_tick(tick))


def test_negative_volume_is_rejected():
    engine = MarketDataEngine(EventBus())
    tick = make_tick(volume=-1)

    assert_raises(ValueError, lambda: engine.on_tick(tick))


def test_negative_open_interest_is_rejected():
    engine = MarketDataEngine(EventBus())
    tick = make_tick(open_interest=-1)

    assert_raises(ValueError, lambda: engine.on_tick(tick))


def test_invalid_bid_ask_relationship_is_rejected():
    engine = MarketDataEngine(EventBus())
    tick = make_tick(bid_price=25202, ask_price=25201)

    assert_raises(ValueError, lambda: engine.on_tick(tick))


def test_invalid_symbol_is_rejected():
    engine = MarketDataEngine(EventBus())
    tick = replace(make_tick(), symbol="NIFTY")

    assert_raises(ValueError, lambda: engine.on_tick(tick))


def test_invalid_exchange_is_rejected():
    engine = MarketDataEngine(EventBus())
    tick = replace(make_tick(), exchange="NSE")

    assert_raises(ValueError, lambda: engine.on_tick(tick))


def test_invalid_timestamp_is_rejected():
    engine = MarketDataEngine(EventBus())
    tick = replace(make_tick(), timestamp="2026-07-10T09:15:01")

    assert_raises(ValueError, lambda: engine.on_tick(tick))


def test_negative_bid_price_is_rejected():
    engine = MarketDataEngine(EventBus())
    tick = make_tick(bid_price=-1, ask_price=25201)

    assert_raises(ValueError, lambda: engine.on_tick(tick))


def test_negative_ask_price_is_rejected():
    engine = MarketDataEngine(EventBus())
    tick = make_tick(bid_price=0, ask_price=-1)

    assert_raises(ValueError, lambda: engine.on_tick(tick))


def test_get_all_latest_returns_defensive_copy():
    engine = MarketDataEngine(EventBus())
    tick = make_tick()

    engine.on_tick(tick)
    latest = engine.get_all_latest()
    latest.clear()

    assert latest == {}
    assert engine.get_latest(Instrument.NIFTY) == tick


def test_clear_removes_all_state_and_resets_readiness():
    engine = MarketDataEngine(EventBus())
    engine.on_tick(make_tick())

    engine.clear()

    assert engine.get_latest(Instrument.NIFTY) is None
    assert engine.get_all_latest() == {}
    assert not engine.is_ready()


def test_update_tick_alias_behaves_like_on_tick():
    engine = MarketDataEngine(EventBus())
    tick = make_tick()

    result = engine.update_tick(tick)

    assert result == tick
    assert engine.get_latest(Instrument.NIFTY) == tick


def test_event_driven_candle_engine_integration_uses_new_tick_only():
    event_bus = EventBus()
    market_engine = MarketDataEngine(event_bus)
    candle_engine = CandleEngine(event_bus)
    event_bus.subscribe(NEW_TICK, candle_engine.on_tick)

    first = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=25200,
        volume=100,
    )
    second = replace(
        first,
        timestamp=datetime(2026, 7, 10, 9, 15, 30),
        last_price=25210,
        volume=50,
    )

    market_engine.on_tick(first)
    market_engine.on_tick(second)
    market_engine.on_tick(second)

    candle = candle_engine.get_current(Instrument.NIFTY)

    assert candle.open == 25200
    assert candle.high == 25210
    assert candle.close == 25210
    assert candle.volume == 150
