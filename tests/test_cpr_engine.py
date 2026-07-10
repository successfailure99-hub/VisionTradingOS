"""
====================================================
Vision Trading OS
Test - CPR Engine
====================================================
"""

from dataclasses import FrozenInstanceError
from datetime import date

from core.event_bus import EventBus
from core.events import CPR_UPDATED
from core.models.daily_ohlc import DailyOHLC
from engines.cpr.calculator import CPRCalculator
from engines.cpr.cpr_engine import CPREngine
from engines.cpr.levels import CPRLevels


def make_daily_ohlc(
    trading_date: date = date(2026, 7, 10),
    open: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 105.0,
) -> DailyOHLC:
    return DailyOHLC(
        trading_date=trading_date,
        open=open,
        high=high,
        low=low,
        close=close,
    )


def assert_close(actual: float, expected: float) -> None:
    assert abs(actual - expected) < 0.0000001


def assert_raises(expected_error, callback) -> None:
    try:
        callback()
    except expected_error:
        return

    raise AssertionError(f"Expected {expected_error.__name__}")


def test_cpr_calculator_standard_formula_produces_pivot_bc_tc():
    levels = CPRCalculator.calculate(make_daily_ohlc())

    assert_close(levels.pivot, 101.67)
    assert_close(levels.bc, 100.0)
    assert_close(levels.tc, 103.33)


def test_cpr_calculator_normalizes_bc_below_tc():
    levels = CPRCalculator.calculate(
        make_daily_ohlc(high=25260, low=25010, close=25120)
    )

    assert levels.bc <= levels.tc
    assert_close(levels.bc, 25125.0)
    assert_close(levels.tc, 25135.0)


def test_cpr_calculator_width_is_tc_minus_bc():
    levels = CPRCalculator.calculate(make_daily_ohlc())

    assert_close(levels.width, levels.tc - levels.bc)


def test_cpr_calculator_width_percentage_is_correct():
    levels = CPRCalculator.calculate(make_daily_ohlc())

    assert_close(levels.width_percentage, 3.2787)


def test_cpr_calculator_rounding_contract():
    levels = CPRCalculator.calculate(
        make_daily_ohlc(high=25260, low=25010, close=25120)
    )

    assert levels.pivot == 25130.00
    assert levels.bc == 25125.00
    assert levels.tc == 25135.00
    assert levels.width == 10.00
    assert levels.width_percentage == 0.0398


def test_cpr_calculator_invalid_high_low_range_raises_value_error():
    assert_raises(
        ValueError,
        lambda: CPRCalculator.calculate(make_daily_ohlc(high=90, low=110)),
    )


def test_cpr_engine_initial_state_has_no_input_levels_or_readiness():
    engine = CPREngine(EventBus())

    assert engine.daily_ohlc is None
    assert engine.levels is None
    assert engine.data is None
    assert not engine.is_ready()


def test_cpr_engine_first_valid_daily_ohlc_produces_and_caches_levels():
    engine = CPREngine(EventBus())
    daily_ohlc = make_daily_ohlc()

    levels = engine.calculate(daily_ohlc)

    assert isinstance(levels, CPRLevels)
    assert engine.daily_ohlc == daily_ohlc
    assert engine.levels == levels
    assert engine.data == levels
    assert engine.is_ready()


def test_cpr_engine_uses_cpr_calculator_for_calculation():
    engine = CPREngine(EventBus())
    daily_ohlc = make_daily_ohlc()
    original_calculate = CPRCalculator.calculate
    calls = []
    expected = CPRLevels(
        trading_date=daily_ohlc.trading_date,
        previous_high=daily_ohlc.high,
        previous_low=daily_ohlc.low,
        previous_close=daily_ohlc.close,
        pivot=1.0,
        bc=2.0,
        tc=3.0,
        width=1.0,
        width_percentage=1.0,
    )

    def fake_calculate(received):
        calls.append(received)
        return expected

    CPRCalculator.calculate = staticmethod(fake_calculate)
    try:
        result = engine.calculate(daily_ohlc)
    finally:
        CPRCalculator.calculate = original_calculate

    assert calls == [daily_ohlc]
    assert result == expected
    assert engine.levels == expected


def test_cpr_updated_is_published_with_immutable_levels():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CPR_UPDATED, received.append)
    engine = CPREngine(event_bus)

    levels = engine.calculate(make_daily_ohlc())

    assert received == [levels]
    assert_raises(FrozenInstanceError, lambda: setattr(received[0], "pivot", 1))


def test_cpr_state_is_updated_before_subscriber_executes():
    event_bus = EventBus()
    observed = []
    engine = CPREngine(event_bus)

    def on_cpr_updated(levels):
        observed.append((levels, engine.levels, engine.daily_ohlc, engine.data))

    event_bus.subscribe(CPR_UPDATED, on_cpr_updated)
    daily_ohlc = make_daily_ohlc()

    levels = engine.calculate(daily_ohlc)

    assert observed == [(levels, levels, daily_ohlc, levels)]


def test_exact_duplicate_returns_cached_levels_and_publishes_no_second_event():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CPR_UPDATED, received.append)
    engine = CPREngine(event_bus)
    daily_ohlc = make_daily_ohlc()

    first = engine.calculate(daily_ohlc)
    duplicate = engine.calculate(daily_ohlc)

    assert duplicate is first
    assert engine.levels is first
    assert received == [first]


def test_same_date_corrected_daily_ohlc_recalculates_and_publishes_event():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CPR_UPDATED, received.append)
    engine = CPREngine(event_bus)

    first = engine.calculate(make_daily_ohlc())
    corrected = engine.calculate(make_daily_ohlc(close=100))

    assert corrected is not first
    assert corrected.pivot != first.pivot
    assert engine.levels == corrected
    assert received == [first, corrected]


def test_newer_trading_date_replaces_existing_state():
    engine = CPREngine(EventBus())

    first = engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10)))
    second_daily = make_daily_ohlc(trading_date=date(2026, 7, 11), close=100)
    second = engine.calculate(second_daily)

    assert second is not first
    assert engine.daily_ohlc == second_daily
    assert engine.levels == second
    assert engine.data == second


def test_older_trading_date_raises_value_error():
    engine = CPREngine(EventBus())
    engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 11)))

    assert_raises(
        ValueError,
        lambda: engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10))),
    )


def test_rejected_stale_input_leaves_previous_state_unchanged():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CPR_UPDATED, received.append)
    engine = CPREngine(event_bus)
    accepted_daily = make_daily_ohlc(trading_date=date(2026, 7, 11))
    accepted = engine.calculate(accepted_daily)

    assert_raises(
        ValueError,
        lambda: engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10))),
    )

    assert engine.daily_ohlc == accepted_daily
    assert engine.levels == accepted
    assert engine.data == accepted
    assert received == [accepted]


def test_update_alias_behaves_like_calculate():
    engine = CPREngine(EventBus())
    daily_ohlc = make_daily_ohlc()

    levels = engine.update(daily_ohlc)

    assert levels == engine.calculate(daily_ohlc)
    assert engine.daily_ohlc == daily_ohlc


def test_levels_property_returns_latest_result():
    engine = CPREngine(EventBus())
    levels = engine.calculate(make_daily_ohlc())

    assert engine.levels == levels


def test_daily_ohlc_property_returns_latest_accepted_input():
    engine = CPREngine(EventBus())
    daily_ohlc = make_daily_ohlc()

    engine.calculate(daily_ohlc)

    assert engine.daily_ohlc == daily_ohlc


def test_reset_clears_cpr_state_and_readiness():
    engine = CPREngine(EventBus())
    engine.calculate(make_daily_ohlc())

    engine.reset()

    assert engine.daily_ohlc is None
    assert engine.levels is None
    assert engine.data is None
    assert not engine.is_ready()


def test_clear_clears_cpr_state_and_readiness():
    engine = CPREngine(EventBus())
    engine.calculate(make_daily_ohlc())

    engine.clear()

    assert engine.daily_ohlc is None
    assert engine.levels is None
    assert engine.data is None
    assert not engine.is_ready()


def test_non_daily_ohlc_input_raises_type_error():
    engine = CPREngine(EventBus())

    assert_raises(TypeError, lambda: engine.calculate(object()))


def test_non_date_trading_date_raises_value_error():
    engine = CPREngine(EventBus())
    daily_ohlc = make_daily_ohlc()
    object.__setattr__(daily_ohlc, "trading_date", "2026-07-10")

    assert_raises(ValueError, lambda: engine.calculate(daily_ohlc))


def test_zero_or_negative_open_raises_value_error():
    engine = CPREngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=0)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=-1)))


def test_zero_or_negative_high_raises_value_error():
    engine = CPREngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(high=0)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(high=-1)))


def test_zero_or_negative_low_raises_value_error():
    engine = CPREngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(low=0)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(low=-1)))


def test_zero_or_negative_close_raises_value_error():
    engine = CPREngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=0)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=-1)))


def test_open_outside_high_low_range_raises_value_error():
    engine = CPREngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=89)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=111)))


def test_close_outside_high_low_range_raises_value_error():
    engine = CPREngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=89)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=111)))


def test_nan_ohlc_value_raises_value_error():
    engine = CPREngine(EventBus())

    assert_raises(
        ValueError,
        lambda: engine.calculate(make_daily_ohlc(close=float("nan"))),
    )


def test_infinite_ohlc_value_raises_value_error():
    engine = CPREngine(EventBus())

    assert_raises(
        ValueError,
        lambda: engine.calculate(make_daily_ohlc(close=float("inf"))),
    )
    assert_raises(
        ValueError,
        lambda: engine.calculate(make_daily_ohlc(close=float("-inf"))),
    )


def test_boolean_ohlc_value_raises_value_error():
    engine = CPREngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=True)))


def test_invalid_input_publishes_no_event():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CPR_UPDATED, received.append)
    engine = CPREngine(event_bus)

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=0)))

    assert received == []
    assert engine.levels is None
    assert not engine.is_ready()


def test_stale_input_publishes_no_event():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CPR_UPDATED, received.append)
    engine = CPREngine(event_bus)
    accepted = engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 11)))

    assert_raises(
        ValueError,
        lambda: engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10))),
    )

    assert received == [accepted]


def test_cpr_engine_memory_remains_latest_only():
    engine = CPREngine(EventBus())

    first = engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10)))
    second_daily = make_daily_ohlc(trading_date=date(2026, 7, 11), close=100)
    second = engine.calculate(second_daily)

    assert first is not second
    assert engine.daily_ohlc == second_daily
    assert engine.levels == second
    assert engine.data == second
    assert not hasattr(engine, "_history")
