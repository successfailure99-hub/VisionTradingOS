"""
Tests for Price Action Engine V1.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from core.event_bus import EventBus
from core.events import PRICE_ACTION_READY
from core.models.candle import Candle
from engines.price_action import (
    BreakType,
    PriceActionEngine,
    PriceActionState,
    StructureBreak,
    StructureType,
    SwingPoint,
    SwingType,
    Trend,
)
from engines.price_action.swing_detector import SwingDetector


BASE = datetime(2026, 7, 10, 9, 15)


def make_candle(
    index: int = 0,
    symbol: str = "NIFTY",
    timeframe: str = "1m",
    open: float = 10.0,
    high: float = 12.0,
    low: float = 9.0,
    close: float = 11.0,
    volume: int = 100,
    start_time=None,
    end_time=None,
) -> Candle:
    start = start_time or BASE + timedelta(minutes=index)
    end = end_time or start + timedelta(minutes=1)
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        start_time=start,
        end_time=end,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def assert_raises(expected_error, callback) -> None:
    try:
        callback()
    except expected_error:
        return
    raise AssertionError(f"Expected {expected_error.__name__}")


def engine(left_bars: int = 2, right_bars: int = 2) -> PriceActionEngine:
    return PriceActionEngine(EventBus(), " nifty ", " 1m ", left_bars, right_bars)


def feed(engine, candles):
    state = None
    for candle in candles:
        state = engine.update(candle)
    return state


def swing_high_sequence():
    return [
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=11, low=6, open=7, close=8),
        make_candle(2, high=15, low=7, open=8, close=10),
        make_candle(3, high=12, low=6, open=7, close=8),
        make_candle(4, high=11, low=5, open=6, close=7),
    ]


def swing_low_sequence():
    return [
        make_candle(0, high=14, low=5, open=8, close=9),
        make_candle(1, high=13, low=4, open=8, close=9),
        make_candle(2, high=12, low=1, open=8, close=9),
        make_candle(3, high=13, low=4, open=8, close=9),
        make_candle(4, high=14, low=5, open=8, close=9),
    ]


def bullish_structure_sequence():
    return [
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=12, low=6, open=7, close=8),
        make_candle(2, high=11, low=5, open=6, close=7),
        make_candle(3, high=13, low=7, open=8, close=9),
        make_candle(4, high=12, low=6, open=7, close=8),
        make_candle(5, high=14, low=8, open=9, close=10),
    ]


def bearish_structure_sequence():
    return [
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=12, low=6, open=7, close=8),
        make_candle(2, high=11, low=4, open=6, close=7),
        make_candle(3, high=11.5, low=5, open=6, close=7),
        make_candle(4, high=10.5, low=3, open=5, close=6),
        make_candle(5, high=11, low=4, open=5, close=6),
    ]


def test_enum_values_match_contract():
    assert SwingType.HIGH.value == "high"
    assert SwingType.LOW.value == "low"
    assert StructureType.HIGHER_HIGH.value == "higher_high"
    assert StructureType.HIGHER_LOW.value == "higher_low"
    assert StructureType.LOWER_HIGH.value == "lower_high"
    assert StructureType.LOWER_LOW.value == "lower_low"
    assert StructureType.EQUAL_HIGH.value == "equal_high"
    assert StructureType.EQUAL_LOW.value == "equal_low"
    assert Trend.UNKNOWN.value == "unknown"
    assert Trend.RANGE.value == "range"
    assert Trend.BULLISH.value == "bullish"
    assert Trend.BEARISH.value == "bearish"
    assert BreakType.BULLISH_BOS.value == "bullish_bos"
    assert BreakType.BEARISH_BOS.value == "bearish_bos"
    assert BreakType.BULLISH_CHOCH.value == "bullish_choch"
    assert BreakType.BEARISH_CHOCH.value == "bearish_choch"


def test_models_are_immutable_and_slotted():
    candle = make_candle()
    swing = SwingPoint("NIFTY", "1m", SwingType.HIGH, None, 12, candle.start_time, candle.end_time, 0)
    break_ = StructureBreak(BreakType.BULLISH_BOS, 12, 13, candle.start_time, candle.end_time)
    state = PriceActionState("NIFTY", "1m", 1, candle, Trend.UNKNOWN, swing, None, None, None, break_)

    assert_raises(FrozenInstanceError, lambda: setattr(swing, "price", 1))
    assert_raises(FrozenInstanceError, lambda: setattr(break_, "break_price", 1))
    assert_raises(FrozenInstanceError, lambda: setattr(state, "trend", Trend.BULLISH))
    assert_raises(TypeError, lambda: setattr(swing, "extra", 1))
    assert_raises(TypeError, lambda: setattr(break_, "extra", 1))
    assert_raises(TypeError, lambda: setattr(state, "extra", 1))


def test_constructor_validation_and_normalization():
    pa = PriceActionEngine(EventBus(), " nifty ", " 1m ")
    state = pa.update(make_candle(symbol="nifty", timeframe="1m"))

    assert state.symbol == "NIFTY"
    assert state.timeframe == "1m"
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), "", "1m"))
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), "   ", "1m"))
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), 1, "1m"))
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), "NIFTY", ""))
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), "NIFTY", 1))
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), "NIFTY", "1m", 0, 2))
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), "NIFTY", "1m", -1, 2))
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), "NIFTY", "1m", True, 2))
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), "NIFTY", "1m", 2, 0))
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), "NIFTY", "1m", 2, -1))
    assert_raises(ValueError, lambda: PriceActionEngine(EventBus(), "NIFTY", "1m", 2, False))


def test_initial_state_is_empty():
    pa = engine()

    assert pa.state is None
    assert pa.data is None
    assert not pa.is_ready()
    assert pa.candle_count == 0
    assert pa.trend is Trend.UNKNOWN
    assert pa.latest_swing_high is None
    assert pa.latest_swing_low is None
    assert pa.latest_break is None


def test_candle_validation_rejects_invalid_inputs_and_accepts_zero_range_zero_volume():
    pa = engine()
    aware = datetime(2026, 7, 10, 9, 15, tzinfo=timezone.utc)

    assert_raises(TypeError, lambda: pa.update(object()))
    assert_raises(ValueError, lambda: pa.update(make_candle(symbol="BANKNIFTY")))
    assert_raises(ValueError, lambda: pa.update(make_candle(timeframe="5m")))
    assert_raises(ValueError, lambda: pa.update(make_candle(start_time="bad", end_time=BASE + timedelta(minutes=1))))
    assert_raises(ValueError, lambda: pa.update(make_candle(end_time="bad")))
    assert_raises(ValueError, lambda: pa.update(make_candle(end_time=BASE)))
    assert_raises(ValueError, lambda: pa.update(make_candle(start_time=aware, end_time=BASE + timedelta(minutes=1))))
    assert_raises(ValueError, lambda: pa.update(make_candle(open="10")))
    assert_raises(ValueError, lambda: pa.update(make_candle(high=True)))
    assert_raises(ValueError, lambda: pa.update(make_candle(low=float("nan"))))
    assert_raises(ValueError, lambda: pa.update(make_candle(close=float("inf"))))
    assert_raises(ValueError, lambda: pa.update(make_candle(open=0)))
    assert_raises(ValueError, lambda: pa.update(make_candle(low=-1)))
    assert_raises(ValueError, lambda: pa.update(make_candle(high=8, low=9, open=9, close=9)))
    assert_raises(ValueError, lambda: pa.update(make_candle(open=8)))
    assert_raises(ValueError, lambda: pa.update(make_candle(close=13)))
    assert_raises(ValueError, lambda: pa.update(make_candle(volume=-1)))
    assert_raises(ValueError, lambda: pa.update(make_candle(volume=True)))
    assert_raises(ValueError, lambda: pa.update(make_candle(volume=1.5)))

    zero_range = pa.update(make_candle(open=10, high=10, low=10, close=10, volume=0))
    assert zero_range.candle_count == 1


def test_first_candle_creates_ready_state_and_publishes_after_state_update():
    event_bus = EventBus()
    pa = PriceActionEngine(event_bus, "NIFTY", "1m")
    observed = []

    def on_ready(state):
        observed.append((state, pa.state, pa.data, pa.candle_count, pa.trend))

    event_bus.subscribe(PRICE_ACTION_READY, on_ready)
    candle = make_candle()

    state = pa.update(candle)

    assert state.last_candle == candle
    assert state.candle_count == 1
    assert state.trend is Trend.UNKNOWN
    assert pa.is_ready()
    assert pa.data == state
    assert observed == [(state, state, state, 1, Trend.UNKNOWN)]


def test_exact_duplicate_is_suppressed():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(PRICE_ACTION_READY, received.append)
    pa = PriceActionEngine(event_bus, "NIFTY", "1m")
    candle = make_candle()

    first = pa.update(candle)
    duplicate = pa.update(candle)

    assert duplicate is first
    assert pa.candle_count == 1
    assert received == [first]


def test_newer_adjacent_and_gap_candles_are_accepted():
    pa = engine()

    first = pa.update(make_candle(0))
    second = pa.update(make_candle(1))
    gap = pa.update(make_candle(3))

    assert first.candle_count == 1
    assert second.candle_count == 2
    assert gap.candle_count == 3


def test_stale_overlap_and_rejected_input_preserve_state_and_events():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(PRICE_ACTION_READY, received.append)
    pa = PriceActionEngine(event_bus, "NIFTY", "1m")
    first = pa.update(make_candle(0))
    second = pa.update(make_candle(1))

    assert_raises(ValueError, lambda: pa.update(make_candle(0, close=10)))
    assert pa.state == second
    assert pa.candle_count == 2
    assert received == [first, second]

    overlap = make_candle(2, start_time=BASE + timedelta(minutes=1, seconds=30))
    assert_raises(ValueError, lambda: pa.update(overlap))
    assert pa.state == second
    assert pa.candle_count == 2
    assert received == [first, second]

    assert_raises(ValueError, lambda: pa.update(make_candle(2, close=0)))
    assert pa.state == second
    assert received == [first, second]


def test_latest_correction_replays_state_and_suppresses_duplicate_afterward():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(PRICE_ACTION_READY, received.append)
    pa = PriceActionEngine(event_bus, "NIFTY", "1m", left_bars=1, right_bars=1)
    candles = [
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=12, low=6, open=7, close=8),
        make_candle(2, high=11, low=5, open=6, close=7),
    ]
    feed(pa, candles)
    before = pa.state
    assert before.latest_swing_high is not None

    correction = make_candle(2, high=12, low=5, open=6, close=7)
    corrected = pa.update(correction)
    duplicate = pa.update(correction)

    assert corrected is not before
    assert duplicate is corrected
    assert pa.candle_count == 3
    assert pa.latest_swing_high is None
    assert received[-1] is corrected
    assert len(received) == 4


def test_non_latest_correction_is_rejected_and_preserves_state():
    pa = engine(left_bars=1, right_bars=1)
    feed(pa, [make_candle(0), make_candle(1), make_candle(2)])
    state = pa.state

    assert_raises(ValueError, lambda: pa.update(make_candle(1, close=10)))

    assert pa.state == state
    assert pa.candle_count == 3


def test_default_swing_high_detection_confirms_after_right_bars():
    pa = engine()

    feed(pa, swing_high_sequence()[:4])
    assert pa.latest_swing_high is None

    feed(pa, swing_high_sequence()[4:])
    swing = pa.latest_swing_high

    assert swing.swing_type is SwingType.HIGH
    assert swing.structure_type is None
    assert swing.price == 15
    assert swing.candle_start_time == swing_high_sequence()[2].start_time
    assert swing.candle_end_time == swing_high_sequence()[2].end_time
    assert swing.candle_index == 2


def test_swing_high_strict_inequality_rules():
    equal = tuple([
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=11, low=6, open=7, close=8),
        make_candle(2, high=15, low=7, open=8, close=10),
        make_candle(3, high=15, low=6, open=7, close=8),
        make_candle(4, high=11, low=5, open=6, close=7),
    ])
    left_higher = tuple([
        make_candle(0, high=16, low=5, open=6, close=7),
        make_candle(1, high=11, low=6, open=7, close=8),
        make_candle(2, high=15, low=7, open=8, close=10),
        make_candle(3, high=12, low=6, open=7, close=8),
        make_candle(4, high=11, low=5, open=6, close=7),
    ])
    right_higher = tuple([
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=11, low=6, open=7, close=8),
        make_candle(2, high=15, low=7, open=8, close=10),
        make_candle(3, high=16, low=6, open=7, close=8),
        make_candle(4, high=11, low=5, open=6, close=7),
    ])

    assert SwingDetector.detect_confirmed_swing(equal, 2, 2) is None
    assert SwingDetector.detect_confirmed_swing(left_higher, 2, 2) is None
    assert SwingDetector.detect_confirmed_swing(right_higher, 2, 2) is None


def test_default_swing_low_detection_and_non_repaint():
    pa = engine()
    state = feed(pa, swing_low_sequence())
    swing = state.latest_swing_low

    assert swing.swing_type is SwingType.LOW
    assert swing.structure_type is None
    assert swing.price == 1
    assert swing.candle_index == 2

    next_state = pa.update(make_candle(5, high=13, low=6, open=8, close=9))
    assert next_state.latest_swing_low == swing


def test_swing_low_strict_inequality_rules():
    equal = tuple([
        make_candle(0, high=14, low=5, open=8, close=9),
        make_candle(1, high=13, low=4, open=8, close=9),
        make_candle(2, high=12, low=1, open=8, close=9),
        make_candle(3, high=13, low=1, open=8, close=9),
        make_candle(4, high=14, low=5, open=8, close=9),
    ])
    left_lower = tuple([
        make_candle(0, high=14, low=0.5, open=8, close=9),
        make_candle(1, high=13, low=4, open=8, close=9),
        make_candle(2, high=12, low=1, open=8, close=9),
        make_candle(3, high=13, low=4, open=8, close=9),
        make_candle(4, high=14, low=5, open=8, close=9),
    ])
    right_lower = tuple([
        make_candle(0, high=14, low=5, open=8, close=9),
        make_candle(1, high=13, low=4, open=8, close=9),
        make_candle(2, high=12, low=1, open=8, close=9),
        make_candle(3, high=13, low=0.5, open=8, close=9),
        make_candle(4, high=14, low=5, open=8, close=9),
    ])

    assert SwingDetector.detect_confirmed_swing(equal, 2, 2) is None
    assert SwingDetector.detect_confirmed_swing(left_lower, 2, 2) is None
    assert SwingDetector.detect_confirmed_swing(right_lower, 2, 2) is None


def test_ambiguous_outside_candle_produces_no_swing_and_preserves_structure():
    candles = tuple([
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=11, low=4, open=6, close=7),
        make_candle(2, high=20, low=1, open=6, close=7),
        make_candle(3, high=12, low=4, open=6, close=7),
        make_candle(4, high=10, low=5, open=6, close=7),
    ])

    assert SwingDetector.detect_confirmed_swing(candles, 2, 2) is None


def test_structure_classification_and_previous_latest_references():
    pa = engine(left_bars=1, right_bars=1)

    state = feed(pa, bullish_structure_sequence())

    assert state.previous_swing_high.price == 12
    assert state.latest_swing_high.price == 13
    assert state.latest_swing_high.structure_type is StructureType.HIGHER_HIGH
    assert state.previous_swing_low.price == 5
    assert state.latest_swing_low.price == 6
    assert state.latest_swing_low.structure_type is StructureType.HIGHER_LOW
    assert state.trend is Trend.BULLISH


def test_lower_and_equal_structure_classifications():
    bearish = engine(left_bars=1, right_bars=1)
    bearish_state = feed(bearish, bearish_structure_sequence())

    assert bearish_state.latest_swing_high.structure_type is StructureType.LOWER_HIGH
    assert bearish_state.latest_swing_low.structure_type is StructureType.LOWER_LOW
    assert bearish_state.trend is Trend.BEARISH

    equal_high = engine(left_bars=1, right_bars=1)
    equal_high_state = feed(equal_high, [
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=12, low=6, open=7, close=8),
        make_candle(2, high=11, low=5, open=6, close=7),
        make_candle(3, high=12, low=7, open=8, close=9),
        make_candle(4, high=11, low=6, open=7, close=8),
    ])
    assert equal_high_state.latest_swing_high.structure_type is StructureType.EQUAL_HIGH

    equal_low = engine(left_bars=1, right_bars=1)
    equal_low_state = feed(equal_low, [
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=12, low=6, open=7, close=8),
        make_candle(2, high=11, low=5, open=6, close=7),
        make_candle(3, high=13, low=7, open=8, close=9),
        make_candle(4, high=12, low=5, open=6, close=7),
        make_candle(5, high=14, low=8, open=9, close=10),
    ])
    assert equal_low_state.latest_swing_low.structure_type is StructureType.EQUAL_LOW


def test_range_trends_for_mixed_or_equal_structure():
    hh_ll = engine(left_bars=1, right_bars=1)
    state = feed(hh_ll, [
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=12, low=6, open=7, close=8),
        make_candle(2, high=11, low=5, open=6, close=7),
        make_candle(3, high=13, low=7, open=8, close=9),
        make_candle(4, high=12, low=4, open=6, close=7),
        make_candle(5, high=14, low=8, open=9, close=10),
    ])
    assert state.trend is Trend.RANGE

    lh_hl = engine(left_bars=1, right_bars=1)
    state = feed(lh_hl, [
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=12, low=6, open=7, close=8),
        make_candle(2, high=11, low=5, open=6, close=7),
        make_candle(3, high=11.5, low=7, open=8, close=9),
        make_candle(4, high=10.5, low=6, open=7, close=8),
        make_candle(5, high=14, low=8, open=9, close=10),
    ])
    assert state.trend is Trend.RANGE


def test_unknown_trend_until_both_sides_are_classified():
    pa = engine(left_bars=1, right_bars=1)

    feed(pa, swing_high_sequence()[:3])

    assert pa.trend is Trend.UNKNOWN


def test_bullish_breaks_use_close_and_do_not_repeat_same_level():
    pa = engine(left_bars=1, right_bars=1)
    feed(pa, bullish_structure_sequence())
    break_state = pa.update(make_candle(6, high=15, low=9, open=10, close=14))
    repeat_state = pa.update(make_candle(7, high=16, low=10, open=11, close=15))

    assert break_state.latest_break.break_type is BreakType.BULLISH_BOS
    assert break_state.latest_break.broken_price == 13
    assert break_state.latest_break.break_price == 14
    assert break_state.latest_break.candle_start_time == make_candle(6).start_time
    assert repeat_state.latest_break == break_state.latest_break


def test_wick_or_equal_close_above_high_does_not_break():
    pa = engine(left_bars=1, right_bars=1)
    feed(pa, bullish_structure_sequence())

    wick = pa.update(make_candle(6, high=15, low=8, open=10, close=13))

    assert wick.latest_break is None


def test_bearish_breaks_use_close_and_do_not_repeat_same_level():
    pa = engine(left_bars=1, right_bars=1)
    feed(pa, bearish_structure_sequence())
    break_state = pa.update(make_candle(6, high=5, low=2, open=4, close=2.5))
    repeat_state = pa.update(make_candle(7, high=4, low=1, open=3, close=2))

    assert break_state.latest_break.break_type is BreakType.BEARISH_BOS
    assert break_state.latest_break.broken_price == 3
    assert break_state.latest_break.break_price == 2.5
    assert repeat_state.latest_break == break_state.latest_break


def test_wick_or_equal_close_below_low_does_not_break():
    pa = engine(left_bars=1, right_bars=1)
    feed(pa, bearish_structure_sequence())

    wick = pa.update(make_candle(6, high=5, low=2, open=4, close=3))

    assert wick.latest_break is None


def test_choch_and_unknown_or_range_break_classification():
    bullish = engine(left_bars=1, right_bars=1)
    feed(bullish, bullish_structure_sequence())
    bearish_choch = bullish.update(make_candle(6, high=8, low=5, open=7, close=5.5))
    assert bearish_choch.latest_break.break_type is BreakType.BEARISH_CHOCH

    bearish = engine(left_bars=1, right_bars=1)
    feed(bearish, bearish_structure_sequence())
    bullish_choch = bearish.update(make_candle(6, high=13, low=8, open=9, close=12))
    assert bullish_choch.latest_break.break_type is BreakType.BULLISH_CHOCH

    unknown = engine(left_bars=1, right_bars=1)
    feed(unknown, [
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=12, low=6, open=7, close=8),
        make_candle(2, high=11, low=5, open=6, close=7),
    ])
    assert unknown.update(make_candle(3, high=13, low=7, open=8, close=12.5)).latest_break.break_type is BreakType.BULLISH_BOS

    range_engine = engine(left_bars=1, right_bars=1)
    feed(range_engine, [
        make_candle(0, high=10, low=5, open=6, close=7),
        make_candle(1, high=12, low=6, open=7, close=8),
        make_candle(2, high=11, low=5, open=6, close=7),
        make_candle(3, high=13, low=7, open=8, close=9),
        make_candle(4, high=12, low=4, open=6, close=7),
        make_candle(5, high=14, low=8, open=9, close=10),
    ])
    assert range_engine.trend is Trend.RANGE
    assert range_engine.update(make_candle(6, high=15, low=9, open=10, close=14)).latest_break.break_type is BreakType.BULLISH_BOS


def test_new_structural_level_can_later_trigger_new_break():
    pa = engine(left_bars=1, right_bars=1)
    feed(pa, bullish_structure_sequence())
    first_break = pa.update(make_candle(6, high=15, low=9, open=10, close=14))
    feed(pa, [
        make_candle(7, high=16, low=10, open=11, close=12),
        make_candle(8, high=15, low=9, open=10, close=11),
    ])
    second_break = pa.update(make_candle(9, high=18, low=12, open=13, close=17))

    assert first_break.latest_break.broken_price == 13
    assert second_break.latest_break.broken_price == 16
    assert second_break.latest_break != first_break.latest_break


def test_events_payloads_are_immutable_and_no_intermediate_replay_events():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(PRICE_ACTION_READY, received.append)
    pa = PriceActionEngine(event_bus, "NIFTY", "1m", left_bars=1, right_bars=1)
    feed(pa, [make_candle(0), make_candle(1), make_candle(2)])

    correction = make_candle(2, high=13, low=9, open=10, close=11)
    corrected = pa.update(correction)

    assert received[-1] is corrected
    assert len(received) == 4
    assert_raises(FrozenInstanceError, lambda: setattr(received[-1], "trend", Trend.BULLISH))


def test_process_alias_and_lifecycle_reset_clear():
    event_bus = EventBus()
    received = []
    event_bus.subscribe(PRICE_ACTION_READY, received.append)
    pa = PriceActionEngine(event_bus, "NIFTY", "1m")

    state = pa.process(make_candle(5))
    pa.reset()

    assert state.candle_count == 1
    assert pa.candle_count == 0
    assert pa.state is None
    assert pa.data is None
    assert pa.latest_swing_high is None
    assert pa.latest_swing_low is None
    assert pa.latest_break is None
    assert pa.trend is Trend.UNKNOWN
    assert not pa.is_ready()
    assert received == [state]

    fresh = pa.update(make_candle(0))
    assert fresh.candle_count == 1

    pa.clear()
    assert pa.state is None
    assert pa.candle_count == 0
    assert len(received) == 2


def test_resetting_one_engine_does_not_affect_another_and_contexts_are_independent():
    first = PriceActionEngine(EventBus(), "NIFTY", "1m", left_bars=1, right_bars=1)
    second = PriceActionEngine(EventBus(), "BANKNIFTY", "5m", left_bars=1, right_bars=1)
    first_state = first.update(make_candle(symbol="NIFTY", timeframe="1m"))
    second_state = second.update(make_candle(symbol="BANKNIFTY", timeframe="5m"))

    first.reset()

    assert first.state is None
    assert second.state == second_state
    assert second.state != first_state
    assert second.candle_count == 1
    assert_raises(ValueError, lambda: second.update(make_candle(1, symbol="NIFTY", timeframe="5m")))


def test_package_exports_public_api():
    from engines.price_action import __all__

    assert __all__ == [
        "PriceActionEngine",
        "PriceActionState",
        "SwingPoint",
        "StructureBreak",
        "SwingType",
        "StructureType",
        "Trend",
        "BreakType",
    ]