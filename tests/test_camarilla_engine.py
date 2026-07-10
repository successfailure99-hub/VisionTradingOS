"""
====================================================
Vision Trading OS
Test - Camarilla Engine
====================================================
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime

from core.event_bus import EventBus
from core.events import CAMARILLA_UPDATED
from core.models.daily_ohlc import DailyOHLC
from engines.camarilla.calculator import CamarillaCalculator
from engines.camarilla.camarilla_engine import CamarillaEngine
from engines.camarilla.levels import CamarillaLevels


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


def test_camarilla_calculator_standard_formula_produces_pivot():
    levels = CamarillaCalculator.calculate(make_daily_ohlc())

    assert_close(levels.pivot, 101.67)


def test_camarilla_calculator_standard_formula_produces_h3_h4():
    levels = CamarillaCalculator.calculate(make_daily_ohlc())

    assert_close(levels.h3, 110.50)
    assert_close(levels.h4, 116.00)


def test_camarilla_calculator_standard_formula_produces_l3_l4():
    levels = CamarillaCalculator.calculate(make_daily_ohlc())

    assert_close(levels.l3, 99.50)
    assert_close(levels.l4, 94.00)


def test_camarilla_calculator_h5_formula_is_correct():
    levels = CamarillaCalculator.calculate(make_daily_ohlc())

    assert_close(levels.h5, 128.33)


def test_camarilla_calculator_l5_mirrors_h5_around_close():
    levels = CamarillaCalculator.calculate(make_daily_ohlc())

    assert_close(levels.l5, 81.67)


def test_camarilla_calculator_h6_formula_is_correct():
    levels = CamarillaCalculator.calculate(make_daily_ohlc())

    assert_close(levels.h6, 140.67)


def test_camarilla_calculator_l6_formula_is_correct():
    levels = CamarillaCalculator.calculate(make_daily_ohlc())

    assert_close(levels.l6, 69.33)


def test_camarilla_calculator_rounds_all_published_levels_to_two_decimals():
    levels = CamarillaCalculator.calculate(
        make_daily_ohlc(high=25260, low=25010, close=25120)
    )

    for value in (
        levels.pivot,
        levels.h3,
        levels.h4,
        levels.h5,
        levels.h6,
        levels.l3,
        levels.l4,
        levels.l5,
        levels.l6,
    ):
        assert value == round(value, 2)

    assert levels.pivot == 25130.00
    assert levels.h3 == 25188.75
    assert levels.h4 == 25257.50
    assert levels.h5 == 25371.10
    assert levels.h6 == 25484.70
    assert levels.l3 == 25051.25
    assert levels.l4 == 24982.50
    assert levels.l5 == 24868.90
    assert levels.l6 == 24755.30


def test_camarilla_calculator_invalid_high_low_range_raises_value_error():
    assert_raises(
        ValueError,
        lambda: CamarillaCalculator.calculate(make_daily_ohlc(high=90, low=110)),
    )


def test_camarilla_calculator_preserves_input_context_fields():
    daily_ohlc = make_daily_ohlc(
        trading_date=date(2026, 7, 9),
        high=25260,
        low=25010,
        close=25120,
    )

    levels = CamarillaCalculator.calculate(daily_ohlc)

    assert levels.trading_date == daily_ohlc.trading_date
    assert levels.previous_high == daily_ohlc.high
    assert levels.previous_low == daily_ohlc.low
    assert levels.previous_close == daily_ohlc.close


def test_camarilla_levels_uses_expected_fields():
    assert [field.name for field in fields(CamarillaLevels)] == [
        "trading_date",
        "previous_high",
        "previous_low",
        "previous_close",
        "pivot",
        "h3",
        "h4",
        "h5",
        "h6",
        "l3",
        "l4",
        "l5",
        "l6",
    ]


def test_camarilla_levels_is_immutable():
    levels = CamarillaCalculator.calculate(make_daily_ohlc())

    assert_raises(FrozenInstanceError, lambda: setattr(levels, "h3", 1))


def test_camarilla_levels_slots_prevent_new_attributes():
    levels = CamarillaCalculator.calculate(make_daily_ohlc())

    assert_raises(TypeError, lambda: setattr(levels, "extra", 1))


def test_camarilla_engine_initial_state_is_empty_and_not_ready():
    engine = CamarillaEngine(EventBus())

    assert engine.daily_ohlc is None
    assert engine.levels is None
    assert engine.data is None
    assert not engine.is_ready()


def test_first_valid_input_returns_levels_and_caches_state():
    engine = CamarillaEngine(EventBus())
    daily_ohlc = make_daily_ohlc()

    levels = engine.calculate(daily_ohlc)

    assert isinstance(levels, CamarillaLevels)
    assert engine.daily_ohlc == daily_ohlc
    assert engine.levels == levels
    assert engine.data == levels
    assert engine.is_ready()


def test_camarilla_engine_uses_calculator_for_calculation():
    engine = CamarillaEngine(EventBus())
    daily_ohlc = make_daily_ohlc()
    original_calculate = CamarillaCalculator.calculate
    calls = []
    expected = CamarillaLevels(
        trading_date=daily_ohlc.trading_date,
        previous_high=daily_ohlc.high,
        previous_low=daily_ohlc.low,
        previous_close=daily_ohlc.close,
        pivot=1.0,
        h3=2.0,
        h4=3.0,
        h5=4.0,
        h6=5.0,
        l3=6.0,
        l4=7.0,
        l5=8.0,
        l6=9.0,
    )

    def fake_calculate(received):
        calls.append(received)
        return expected

    CamarillaCalculator.calculate = staticmethod(fake_calculate)
    try:
        result = engine.calculate(daily_ohlc)
    finally:
        CamarillaCalculator.calculate = original_calculate

    assert calls == [daily_ohlc]
    assert result == expected
    assert engine.levels == expected


def test_first_accepted_calculation_publishes_updated_event_with_payload():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CAMARILLA_UPDATED, received.append)
    engine = CamarillaEngine(event_bus)

    levels = engine.calculate(make_daily_ohlc())

    assert received == [levels]
    assert received[0] is levels


def test_camarilla_state_is_updated_before_subscriber_executes():
    event_bus = EventBus()
    observed = []
    engine = CamarillaEngine(event_bus)

    def on_camarilla_updated(levels):
        observed.append(
            (
                levels,
                engine.daily_ohlc,
                engine.levels,
                engine.data,
                engine.is_ready(),
            )
        )

    event_bus.subscribe(CAMARILLA_UPDATED, on_camarilla_updated)
    daily_ohlc = make_daily_ohlc()

    levels = engine.calculate(daily_ohlc)

    assert observed == [(levels, daily_ohlc, levels, levels, True)]


def test_published_camarilla_levels_are_immutable():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CAMARILLA_UPDATED, received.append)
    engine = CamarillaEngine(event_bus)

    engine.calculate(make_daily_ohlc())

    assert_raises(FrozenInstanceError, lambda: setattr(received[0], "h4", 1))


def test_one_accepted_calculation_produces_exactly_one_event():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CAMARILLA_UPDATED, received.append)
    engine = CamarillaEngine(event_bus)

    engine.calculate(make_daily_ohlc())

    assert len(received) == 1


def test_exact_duplicate_returns_same_cached_object():
    engine = CamarillaEngine(EventBus())
    daily_ohlc = make_daily_ohlc()

    first = engine.calculate(daily_ohlc)
    duplicate = engine.calculate(daily_ohlc)

    assert duplicate is first
    assert engine.levels is first


def test_exact_duplicate_does_not_call_calculator_twice():
    engine = CamarillaEngine(EventBus())
    daily_ohlc = make_daily_ohlc()
    original_calculate = CamarillaCalculator.calculate
    calls = []

    def counting_calculate(received):
        calls.append(received)
        return original_calculate(received)

    CamarillaCalculator.calculate = staticmethod(counting_calculate)
    try:
        engine.calculate(daily_ohlc)
        engine.calculate(daily_ohlc)
    finally:
        CamarillaCalculator.calculate = original_calculate

    assert calls == [daily_ohlc]


def test_exact_duplicate_publishes_no_second_event():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CAMARILLA_UPDATED, received.append)
    engine = CamarillaEngine(event_bus)
    daily_ohlc = make_daily_ohlc()

    first = engine.calculate(daily_ohlc)
    engine.calculate(daily_ohlc)

    assert received == [first]


def test_same_date_corrected_ohlc_recalculates_and_replaces_state():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CAMARILLA_UPDATED, received.append)
    engine = CamarillaEngine(event_bus)
    first_daily = make_daily_ohlc()
    corrected_daily = make_daily_ohlc(close=100)

    first = engine.calculate(first_daily)
    corrected = engine.calculate(corrected_daily)

    assert corrected is not first
    assert corrected.pivot != first.pivot
    assert engine.daily_ohlc == corrected_daily
    assert engine.levels == corrected
    assert engine.data == corrected
    assert received == [first, corrected]


def test_newer_date_replaces_current_state():
    engine = CamarillaEngine(EventBus())
    first = engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10)))
    newer_daily = make_daily_ohlc(trading_date=date(2026, 7, 11), close=100)

    newer = engine.calculate(newer_daily)

    assert newer is not first
    assert engine.daily_ohlc == newer_daily
    assert engine.levels == newer
    assert engine.data == newer


def test_older_date_raises_value_error_and_identifies_stale_dates():
    engine = CamarillaEngine(EventBus())
    engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 11)))

    try:
        engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10)))
    except ValueError as error:
        message = str(error)
        assert "Stale" in message
        assert "2026-07-10" in message
        assert "2026-07-11" in message
        return

    raise AssertionError("Expected stale Camarilla input to raise ValueError")


def test_stale_rejection_preserves_state_and_publishes_no_event():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CAMARILLA_UPDATED, received.append)
    engine = CamarillaEngine(event_bus)
    accepted_daily = make_daily_ohlc(trading_date=date(2026, 7, 11))
    accepted = engine.calculate(accepted_daily)

    assert_raises(
        ValueError,
        lambda: engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10))),
    )

    assert engine.daily_ohlc == accepted_daily
    assert engine.levels == accepted
    assert engine.data == accepted
    assert engine.is_ready()
    assert received == [accepted]


def test_update_alias_behaves_like_calculate():
    engine = CamarillaEngine(EventBus())
    daily_ohlc = make_daily_ohlc()

    levels = engine.update(daily_ohlc)

    assert levels == engine.calculate(daily_ohlc)
    assert engine.daily_ohlc == daily_ohlc


def test_reset_clears_state_readiness_and_publishes_no_event():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CAMARILLA_UPDATED, received.append)
    engine = CamarillaEngine(event_bus)
    engine.calculate(make_daily_ohlc())

    engine.reset()

    assert engine.daily_ohlc is None
    assert engine.levels is None
    assert engine.data is None
    assert not engine.is_ready()
    assert len(received) == 1


def test_clear_has_same_observable_result_as_reset():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CAMARILLA_UPDATED, received.append)
    engine = CamarillaEngine(event_bus)
    engine.calculate(make_daily_ohlc())

    engine.clear()

    assert engine.daily_ohlc is None
    assert engine.levels is None
    assert engine.data is None
    assert not engine.is_ready()
    assert len(received) == 1


def test_engine_accepts_fresh_calculation_after_reset():
    engine = CamarillaEngine(EventBus())
    engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 11)))

    engine.reset()
    fresh = engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10)))

    assert fresh.trading_date == date(2026, 7, 10)
    assert engine.is_ready()


def test_engine_accepts_earlier_date_after_reset_clears_stale_state():
    engine = CamarillaEngine(EventBus())
    engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 12)))

    engine.reset()
    result = engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10)))

    assert result.trading_date == date(2026, 7, 10)


def test_non_daily_ohlc_input_raises_type_error():
    engine = CamarillaEngine(EventBus())

    assert_raises(TypeError, lambda: engine.calculate(object()))


def test_invalid_trading_date_raises_value_error():
    engine = CamarillaEngine(EventBus())
    daily_ohlc = make_daily_ohlc()
    object.__setattr__(daily_ohlc, "trading_date", "2026-07-10")

    assert_raises(ValueError, lambda: engine.calculate(daily_ohlc))


def test_datetime_trading_date_is_rejected():
    engine = CamarillaEngine(EventBus())
    daily_ohlc = make_daily_ohlc()
    object.__setattr__(daily_ohlc, "trading_date", datetime(2026, 7, 10, 9, 15))

    assert_raises(ValueError, lambda: engine.calculate(daily_ohlc))


def test_non_numeric_ohlc_values_raise_value_error():
    engine = CamarillaEngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open="100")))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(high=None)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(low="90")))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=None)))


def test_boolean_ohlc_values_are_rejected():
    engine = CamarillaEngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=True)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(high=True)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(low=True)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=True)))


def test_nan_ohlc_values_are_rejected():
    engine = CamarillaEngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=float("nan"))))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(high=float("nan"))))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(low=float("nan"))))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=float("nan"))))


def test_infinite_ohlc_values_are_rejected():
    engine = CamarillaEngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=float("inf"))))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(high=float("-inf"))))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(low=float("inf"))))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=float("-inf"))))


def test_zero_ohlc_values_are_rejected():
    engine = CamarillaEngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=0)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(high=0)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(low=0)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=0)))


def test_negative_ohlc_values_are_rejected():
    engine = CamarillaEngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=-1)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(high=-1)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(low=-1)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=-1)))


def test_invalid_ohlc_relationships_are_rejected():
    engine = CamarillaEngine(EventBus())

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(high=90, low=90)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(high=89, low=90)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=89)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(open=111)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=89)))
    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=111)))


def test_invalid_input_after_valid_calculation_preserves_state_and_events():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(CAMARILLA_UPDATED, received.append)
    engine = CamarillaEngine(event_bus)
    accepted_daily = make_daily_ohlc()
    accepted = engine.calculate(accepted_daily)

    assert_raises(ValueError, lambda: engine.calculate(make_daily_ohlc(close=0)))

    assert engine.daily_ohlc == accepted_daily
    assert engine.levels == accepted
    assert engine.data == accepted
    assert engine.is_ready()
    assert received == [accepted]


def test_camarilla_engine_stores_only_latest_accepted_input_and_result():
    engine = CamarillaEngine(EventBus())
    first = engine.calculate(make_daily_ohlc(trading_date=date(2026, 7, 10)))
    second_daily = make_daily_ohlc(trading_date=date(2026, 7, 11), close=100)

    second = engine.calculate(second_daily)

    assert first is not second
    assert engine.daily_ohlc == second_daily
    assert engine.levels == second
    assert engine.data == second
    assert not hasattr(engine, "_history")
    assert not hasattr(engine, "_levels_by_date")


def test_two_engine_instances_maintain_independent_state():
    first_engine = CamarillaEngine(EventBus())
    second_engine = CamarillaEngine(EventBus())

    first_levels = first_engine.calculate(make_daily_ohlc(close=105))
    second_levels = second_engine.calculate(make_daily_ohlc(close=100))

    assert first_engine.levels == first_levels
    assert second_engine.levels == second_levels
    assert first_engine.levels != second_engine.levels


def test_resetting_one_engine_does_not_affect_another_engine():
    first_engine = CamarillaEngine(EventBus())
    second_engine = CamarillaEngine(EventBus())
    first_engine.calculate(make_daily_ohlc(close=105))
    second_levels = second_engine.calculate(make_daily_ohlc(close=100))

    first_engine.reset()

    assert first_engine.levels is None
    assert not first_engine.is_ready()
    assert second_engine.levels == second_levels
    assert second_engine.is_ready()
