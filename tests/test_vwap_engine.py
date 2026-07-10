"""
====================================================
Vision Trading OS
Test - VWAP Engine
====================================================
"""

from dataclasses import replace
from datetime import datetime

from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import NEW_TICK, VWAP_UPDATED
from core.models.tick import Tick
from engines.market_data.market_data_engine import MarketDataEngine
from engines.vwap.levels import VWAPLevels
from engines.vwap.vwap_engine import VWAPEngine


def make_tick(
    timestamp: datetime = datetime(2026, 7, 10, 9, 15, 1),
    price: float = 100.0,
    volume: int = 10,
    instrument: Instrument = Instrument.NIFTY,
) -> Tick:
    return Tick(
        symbol=instrument,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=volume,
        bid_price=max(price - 1, 0),
        ask_price=price + 1,
        open_interest=1000,
    )


def assert_close(actual: float, expected: float) -> None:
    assert abs(actual - expected) < 0.0000001


def assert_raises(expected_error, callback) -> None:
    try:
        callback()
    except expected_error:
        return

    raise AssertionError(f"Expected {expected_error.__name__}")


def test_first_positive_volume_tick_creates_vwap():
    engine = VWAPEngine(EventBus())
    tick = make_tick(price=100, volume=10)

    result = engine.on_tick(tick)

    assert isinstance(result, VWAPLevels)
    assert result.symbol is Instrument.NIFTY
    assert result.trading_date == tick.timestamp.date()
    assert result.timestamp == tick.timestamp
    assert_close(result.vwap, 100.0)
    assert result.cumulative_volume == 10
    assert_close(result.cumulative_price_volume, 1000.0)
    assert engine.get_latest(Instrument.NIFTY) == result
    assert engine.data == result
    assert engine.is_ready()


def test_vwap_formula_is_correct_after_multiple_ticks():
    engine = VWAPEngine(EventBus())

    engine.on_tick(make_tick(price=100, volume=10))
    result = engine.on_tick(
        make_tick(
            timestamp=datetime(2026, 7, 10, 9, 15, 2),
            price=110,
            volume=30,
        )
    )

    assert_close(result.vwap, 107.5)


def test_cumulative_volume_is_correct():
    engine = VWAPEngine(EventBus())

    engine.on_tick(make_tick(volume=10))
    result = engine.on_tick(
        make_tick(
            timestamp=datetime(2026, 7, 10, 9, 15, 2),
            volume=15,
        )
    )

    assert result.cumulative_volume == 25


def test_cumulative_price_volume_is_correct():
    engine = VWAPEngine(EventBus())

    engine.on_tick(make_tick(price=100, volume=10))
    result = engine.on_tick(
        make_tick(
            timestamp=datetime(2026, 7, 10, 9, 15, 2),
            price=120,
            volume=5,
        )
    )

    assert_close(result.cumulative_price_volume, 1600.0)


def test_vwap_updated_is_published_with_immutable_result():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(VWAP_UPDATED, received.append)
    engine = VWAPEngine(event_bus)

    result = engine.on_tick(make_tick())

    assert received == [result]
    assert isinstance(received[0], VWAPLevels)
    assert_raises(Exception, lambda: setattr(received[0], "vwap", 1))


def test_state_is_updated_before_vwap_updated_subscribers_run():
    event_bus = EventBus()
    observed = []
    engine = VWAPEngine(event_bus)

    def on_vwap_updated(result):
        observed.append((result, engine.get_latest(result.symbol)))

    event_bus.subscribe(VWAP_UPDATED, on_vwap_updated)

    result = engine.on_tick(make_tick())

    assert observed == [(result, result)]


def test_multiple_instruments_maintain_independent_vwap_state():
    engine = VWAPEngine(EventBus())
    nifty = make_tick(instrument=Instrument.NIFTY, price=100, volume=10)
    banknifty = make_tick(
        instrument=Instrument.BANKNIFTY,
        price=200,
        volume=20,
    )

    nifty_result = engine.on_tick(nifty)
    banknifty_result = engine.on_tick(banknifty)

    assert engine.get_latest(Instrument.NIFTY) == nifty_result
    assert engine.get_latest(Instrument.BANKNIFTY) == banknifty_result
    assert_close(nifty_result.vwap, 100.0)
    assert_close(banknifty_result.vwap, 200.0)


def test_new_trading_date_resets_only_affected_instrument():
    engine = VWAPEngine(EventBus())
    nifty_day_one = make_tick(
        instrument=Instrument.NIFTY,
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=100,
        volume=10,
    )
    banknifty_day_one = make_tick(
        instrument=Instrument.BANKNIFTY,
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=200,
        volume=20,
    )
    nifty_day_two = make_tick(
        instrument=Instrument.NIFTY,
        timestamp=datetime(2026, 7, 11, 9, 15, 1),
        price=120,
        volume=5,
    )

    engine.on_tick(nifty_day_one)
    banknifty_result = engine.on_tick(banknifty_day_one)
    nifty_result = engine.on_tick(nifty_day_two)

    assert nifty_result.trading_date == nifty_day_two.timestamp.date()
    assert nifty_result.cumulative_volume == 5
    assert_close(nifty_result.vwap, 120.0)
    assert engine.get_latest(Instrument.BANKNIFTY) == banknifty_result


def test_older_date_tick_is_rejected_without_changing_state():
    event_bus = EventBus()
    events = []
    event_bus.subscribe(VWAP_UPDATED, events.append)
    engine = VWAPEngine(event_bus)
    latest = make_tick(timestamp=datetime(2026, 7, 11, 9, 15, 1))
    older = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=120,
        volume=5,
    )

    result = engine.on_tick(latest)

    assert_raises(ValueError, lambda: engine.on_tick(older))
    assert engine.get_latest(Instrument.NIFTY) == result
    assert events == [result]


def test_older_timestamp_in_same_session_is_rejected():
    engine = VWAPEngine(EventBus())
    latest = make_tick(timestamp=datetime(2026, 7, 10, 9, 15, 2))
    older = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=120,
        volume=5,
    )

    result = engine.on_tick(latest)

    assert_raises(ValueError, lambda: engine.on_tick(older))
    assert engine.get_latest(Instrument.NIFTY) == result


def test_exact_duplicate_is_ignored_and_publishes_no_event():
    event_bus = EventBus()
    events = []
    event_bus.subscribe(VWAP_UPDATED, events.append)
    engine = VWAPEngine(event_bus)
    tick = make_tick()

    result = engine.on_tick(tick)
    duplicate_result = engine.on_tick(tick)

    assert duplicate_result is None
    assert engine.get_latest(Instrument.NIFTY) == result
    assert events == [result]


def test_equal_timestamp_non_identical_ticks_are_accepted_in_arrival_order():
    engine = VWAPEngine(EventBus())
    first = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=100,
        volume=10,
    )
    second = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 1),
        price=120,
        volume=10,
    )

    engine.on_tick(first)
    result = engine.on_tick(second)

    assert result.cumulative_volume == 20
    assert_close(result.vwap, 110.0)


def test_zero_volume_first_tick_does_not_create_valid_vwap_result():
    event_bus = EventBus()
    events = []
    event_bus.subscribe(VWAP_UPDATED, events.append)
    engine = VWAPEngine(event_bus)

    result = engine.on_tick(make_tick(volume=0))

    assert result is None
    assert engine.get_latest(Instrument.NIFTY) is None
    assert not engine.is_ready()
    assert events == []


def test_zero_volume_tick_after_valid_state_does_not_alter_vwap():
    event_bus = EventBus()
    events = []
    event_bus.subscribe(VWAP_UPDATED, events.append)
    engine = VWAPEngine(event_bus)
    first = make_tick(price=100, volume=10)
    zero = make_tick(
        timestamp=datetime(2026, 7, 10, 9, 15, 2),
        price=500,
        volume=0,
    )

    result = engine.on_tick(first)
    zero_result = engine.on_tick(zero)

    assert zero_result is None
    assert engine.get_latest(Instrument.NIFTY) == result
    assert result.cumulative_volume == 10
    assert_close(result.cumulative_price_volume, 1000.0)
    assert events == [result]


def test_invalid_input_type_is_rejected():
    engine = VWAPEngine(EventBus())

    assert_raises(TypeError, lambda: engine.on_tick(object()))


def test_non_positive_last_price_is_rejected():
    engine = VWAPEngine(EventBus())

    assert_raises(ValueError, lambda: engine.on_tick(make_tick(price=0)))


def test_negative_volume_is_rejected():
    engine = VWAPEngine(EventBus())

    assert_raises(ValueError, lambda: engine.on_tick(make_tick(volume=-1)))


def test_get_latest_returns_correct_result():
    engine = VWAPEngine(EventBus())
    result = engine.on_tick(make_tick())

    assert engine.get_latest(Instrument.NIFTY) == result


def test_get_all_latest_returns_defensive_copy():
    engine = VWAPEngine(EventBus())
    result = engine.on_tick(make_tick())

    latest = engine.get_all_latest()
    latest.clear()

    assert latest == {}
    assert engine.get_latest(Instrument.NIFTY) == result


def test_reset_symbol_clears_only_that_instrument():
    engine = VWAPEngine(EventBus())
    nifty = engine.on_tick(make_tick(instrument=Instrument.NIFTY))
    banknifty = engine.on_tick(
        make_tick(instrument=Instrument.BANKNIFTY, price=200)
    )

    engine.reset(Instrument.NIFTY)

    assert nifty is not None
    assert engine.get_latest(Instrument.NIFTY) is None
    assert engine.get_latest(Instrument.BANKNIFTY) == banknifty
    assert engine.is_ready()


def test_reset_last_remaining_symbol_resets_readiness():
    engine = VWAPEngine(EventBus())
    engine.on_tick(make_tick())

    engine.reset(Instrument.NIFTY)

    assert engine.get_latest(Instrument.NIFTY) is None
    assert not engine.is_ready()


def test_clear_clears_all_state_and_resets_readiness():
    engine = VWAPEngine(EventBus())
    engine.on_tick(make_tick(instrument=Instrument.NIFTY))
    engine.on_tick(make_tick(instrument=Instrument.BANKNIFTY, price=200))

    engine.clear()

    assert engine.get_all_latest() == {}
    assert engine.get_latest(Instrument.NIFTY) is None
    assert engine.get_latest(Instrument.BANKNIFTY) is None
    assert not engine.is_ready()


def test_update_tick_alias_behaves_like_on_tick():
    engine = VWAPEngine(EventBus())
    tick = make_tick()

    result = engine.update_tick(tick)

    assert result == engine.get_latest(Instrument.NIFTY)


def test_event_driven_market_data_integration_updates_vwap():
    event_bus = EventBus()
    market_engine = MarketDataEngine(event_bus)
    vwap_engine = VWAPEngine(event_bus)
    event_bus.subscribe(NEW_TICK, vwap_engine.on_tick)

    market_engine.on_tick(make_tick(price=100, volume=10))
    market_engine.on_tick(
        make_tick(
            timestamp=datetime(2026, 7, 10, 9, 15, 2),
            price=110,
            volume=30,
        )
    )

    result = vwap_engine.get_latest(Instrument.NIFTY)

    assert result.cumulative_volume == 40
    assert_close(result.vwap, 107.5)


def test_market_data_duplicate_filter_prevents_duplicate_vwap_volume():
    event_bus = EventBus()
    market_engine = MarketDataEngine(event_bus)
    vwap_engine = VWAPEngine(event_bus)
    event_bus.subscribe(NEW_TICK, vwap_engine.on_tick)
    tick = make_tick(price=100, volume=10)

    market_engine.on_tick(tick)
    market_engine.on_tick(tick)

    result = vwap_engine.get_latest(Instrument.NIFTY)

    assert result.cumulative_volume == 10
    assert_close(result.vwap, 100.0)


def test_date_reset_vwap_starts_fresh_from_first_positive_tick():
    engine = VWAPEngine(EventBus())
    engine.on_tick(
        make_tick(
            timestamp=datetime(2026, 7, 10, 9, 15, 1),
            price=100,
            volume=10,
        )
    )
    result = engine.on_tick(
        make_tick(
            timestamp=datetime(2026, 7, 11, 9, 15, 1),
            price=300,
            volume=20,
        )
    )

    assert result.trading_date == datetime(2026, 7, 11).date()
    assert result.cumulative_volume == 20
    assert_close(result.cumulative_price_volume, 6000.0)
    assert_close(result.vwap, 300.0)
