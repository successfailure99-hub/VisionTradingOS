"""
Tests for Option Chain Engine V1.
"""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone

from core.event_bus import EventBus
from core.events import OPTION_CHAIN_READY, OPTION_CHAIN_UPDATED
from engines.option_chain import (
    OptionChainCalculator,
    OptionChainEngine,
    OptionChainSnapshot,
    OptionChainState,
    OptionLeg,
    OptionStrike,
    OptionType,
    PositioningBias,
    PressureType,
    StrikeMetric,
)


EXPIRY = date(2026, 7, 30)
TS = datetime(2026, 7, 10, 9, 15)


def call(oi=100, change=10, volume=1000, last_price=50, bid_price=None, ask_price=None):
    return OptionLeg(
        option_type=OptionType.CALL,
        last_price=last_price,
        open_interest=oi,
        change_in_open_interest=change,
        volume=volume,
        bid_price=bid_price,
        ask_price=ask_price,
    )


def put(oi=100, change=10, volume=1000, last_price=50, bid_price=None, ask_price=None):
    return OptionLeg(
        option_type=OptionType.PUT,
        last_price=last_price,
        open_interest=oi,
        change_in_open_interest=change,
        volume=volume,
        bid_price=bid_price,
        ask_price=ask_price,
    )


def strike(price, call_leg=None, put_leg=None):
    return OptionStrike(price, call_leg, put_leg)


def snapshot(
    strikes=None,
    symbol="NIFTY",
    exchange="NFO",
    expiry=EXPIRY,
    timestamp=TS,
    underlying_price=100,
):
    return OptionChainSnapshot(
        symbol=symbol,
        exchange=exchange,
        expiry_date=expiry,
        timestamp=timestamp,
        underlying_price=underlying_price,
        strikes=strikes
        if strikes is not None
        else (
            strike(90, call(100, -5), put(300, 15)),
            strike(100, call(500, 25), put(450, 5)),
            strike(110, call(350, 20), put(120, -10)),
        ),
    )


def engine(symbol=" nifty ", exchange=" nfo ", expiry=EXPIRY):
    return OptionChainEngine(EventBus(), symbol, exchange, expiry)


def feed(oc_engine, oc_snapshot=None):
    return oc_engine.update(oc_snapshot or snapshot())


def assert_raises(expected_error, callback):
    try:
        callback()
    except expected_error:
        return
    raise AssertionError(f"Expected {expected_error}")


def assert_rejected_preserves_state(oc_engine, bad_snapshot, expected_error=ValueError):
    old_snapshot = oc_engine.snapshot
    old_state = oc_engine.state
    old_data = oc_engine.data
    old_ready = oc_engine.is_ready()
    events = []
    oc_engine._event_bus.subscribe(OPTION_CHAIN_UPDATED, events.append)
    oc_engine._event_bus.subscribe(OPTION_CHAIN_READY, events.append)

    assert_raises(expected_error, lambda: oc_engine.update(bad_snapshot))

    assert oc_engine.snapshot == old_snapshot
    assert oc_engine.state == old_state
    assert oc_engine.data == old_data
    assert oc_engine.is_ready() == old_ready
    assert events == []


def invalid_leg(base_leg, **changes):
    values = {
        "option_type": base_leg.option_type,
        "last_price": base_leg.last_price,
        "open_interest": base_leg.open_interest,
        "change_in_open_interest": base_leg.change_in_open_interest,
        "volume": base_leg.volume,
        "bid_price": base_leg.bid_price,
        "ask_price": base_leg.ask_price,
    }
    values.update(changes)
    return OptionLeg(**values)


def test_enum_values_match_contracts():
    assert OptionType.CALL.value == "call"
    assert OptionType.PUT.value == "put"
    assert PositioningBias.BULLISH.value == "bullish"
    assert PositioningBias.BEARISH.value == "bearish"
    assert PositioningBias.NEUTRAL.value == "neutral"
    assert PositioningBias.MIXED.value == "mixed"
    assert PositioningBias.UNKNOWN.value == "unknown"
    assert PressureType.CALL_WRITING.value == "call_writing"
    assert PressureType.CALL_UNWINDING.value == "call_unwinding"
    assert PressureType.PUT_WRITING.value == "put_writing"
    assert PressureType.PUT_UNWINDING.value == "put_unwinding"
    assert PressureType.BALANCED.value == "balanced"
    assert PressureType.UNKNOWN.value == "unknown"


def test_models_are_immutable_and_slotted():
    leg = call()
    row = strike(100, leg, put())
    snap = snapshot((row,))
    metric = StrikeMetric(100, 10)
    state = OptionChainCalculator.calculate(snap)

    assert_raises(FrozenInstanceError, lambda: setattr(leg, "volume", 1))
    assert_raises(FrozenInstanceError, lambda: setattr(row, "strike_price", 1))
    assert_raises(FrozenInstanceError, lambda: setattr(snap, "symbol", "BANKNIFTY"))
    assert_raises(FrozenInstanceError, lambda: setattr(metric, "value", 1))
    assert_raises(FrozenInstanceError, lambda: setattr(state, "atm_strike", 1))
    assert_raises((FrozenInstanceError, TypeError), lambda: setattr(leg, "extra", 1))
    assert_raises((FrozenInstanceError, TypeError), lambda: setattr(row, "extra", 1))
    assert_raises((FrozenInstanceError, TypeError), lambda: setattr(state, "extra", 1))


def test_public_package_exports_match_specification():
    from engines.option_chain import __all__

    assert __all__ == [
        "OptionChainEngine",
        "OptionChainCalculator",
        "OptionChainSnapshot",
        "OptionChainState",
        "OptionStrike",
        "OptionLeg",
        "StrikeMetric",
        "OptionType",
        "PositioningBias",
        "PressureType",
    ]


def test_constructor_normalizes_context_and_initial_state_is_empty():
    oc_engine = engine()

    assert oc_engine.symbol == "NIFTY"
    assert oc_engine.exchange == "NFO"
    assert oc_engine.expiry_date == EXPIRY
    assert oc_engine.snapshot is None
    assert oc_engine.state is None
    assert oc_engine.data is None
    assert not oc_engine.is_ready()


def test_constructor_rejects_invalid_context_values():
    assert_raises(ValueError, lambda: OptionChainEngine(EventBus(), "", "NFO", EXPIRY))
    assert_raises(ValueError, lambda: OptionChainEngine(EventBus(), "   ", "NFO", EXPIRY))
    assert_raises(ValueError, lambda: OptionChainEngine(EventBus(), 1, "NFO", EXPIRY))
    assert_raises(ValueError, lambda: OptionChainEngine(EventBus(), "NIFTY", "", EXPIRY))
    assert_raises(ValueError, lambda: OptionChainEngine(EventBus(), "NIFTY", "   ", EXPIRY))
    assert_raises(ValueError, lambda: OptionChainEngine(EventBus(), "NIFTY", 1, EXPIRY))
    assert_raises(ValueError, lambda: OptionChainEngine(EventBus(), "NIFTY", "NFO", datetime(2026, 7, 30)))
    assert_raises(ValueError, lambda: OptionChainEngine(EventBus(), "NIFTY", "NFO", "2026-07-30"))


def test_snapshot_context_validation_and_type_rejections_are_atomic():
    oc_engine = engine()
    first = feed(oc_engine)

    assert_rejected_preserves_state(oc_engine, object(), TypeError)
    assert_rejected_preserves_state(oc_engine, snapshot(symbol="BANKNIFTY"))
    assert_rejected_preserves_state(oc_engine, snapshot(exchange="BFO"))
    assert_rejected_preserves_state(oc_engine, snapshot(expiry=date(2026, 8, 6)))
    assert oc_engine.state == first


def test_snapshot_timestamp_and_timezone_validation():
    oc_engine = engine()
    feed(oc_engine, snapshot(timestamp=TS.replace(tzinfo=timezone.utc)))

    assert_rejected_preserves_state(oc_engine, snapshot(timestamp="bad"))
    assert_rejected_preserves_state(oc_engine, snapshot(timestamp=TS + timedelta(minutes=1)))


def test_snapshot_underlying_price_validation():
    oc_engine = engine()
    feed(oc_engine)

    for value in (0, -1, True, "100", float("nan"), float("inf")):
        assert_rejected_preserves_state(oc_engine, snapshot(timestamp=TS + timedelta(minutes=1), underlying_price=value))


def test_strike_container_and_strike_price_validation():
    oc_engine = engine()
    feed(oc_engine)

    assert_rejected_preserves_state(oc_engine, snapshot(timestamp=TS + timedelta(minutes=1), strikes=[]))
    assert_rejected_preserves_state(oc_engine, snapshot(timestamp=TS + timedelta(minutes=1), strikes=()))
    assert_rejected_preserves_state(oc_engine, snapshot(timestamp=TS + timedelta(minutes=1), strikes=(object(),)))
    assert_rejected_preserves_state(oc_engine, snapshot(timestamp=TS + timedelta(minutes=1), strikes=(strike(0, call()),)))
    assert_rejected_preserves_state(oc_engine, snapshot(timestamp=TS + timedelta(minutes=1), strikes=(strike(-1, call()),)))
    assert_rejected_preserves_state(oc_engine, snapshot(timestamp=TS + timedelta(minutes=1), strikes=(strike(float("nan"), call()),)))
    assert_rejected_preserves_state(oc_engine, snapshot(timestamp=TS + timedelta(minutes=1), strikes=(strike(100, call()), strike(100, put()))))


def test_unsorted_strikes_are_accepted_and_canonicalized():
    oc_engine = engine()
    state = feed(oc_engine, snapshot(strikes=(strike(110, call()), strike(90, None, put()), strike(100, call(), put()))))

    assert [row.strike_price for row in oc_engine.snapshot.strikes] == [90, 100, 110]
    assert [row.strike_price for row in state.strikes] == [90, 100, 110]


def test_strike_and_leg_validation_rules():
    oc_engine = engine()
    feed(oc_engine)
    next_ts = TS + timedelta(minutes=1)

    bad_cases = [
        snapshot(timestamp=next_ts, strikes=(strike(100, None, None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, put(), None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, None, call()),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, invalid_leg(call(), last_price=-1), None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, invalid_leg(call(), open_interest=-1), None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, invalid_leg(call(), open_interest=1.5), None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, invalid_leg(call(), open_interest=True), None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, invalid_leg(call(), change_in_open_interest=1.5), None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, invalid_leg(call(), volume=-1), None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, invalid_leg(call(), volume=1.5), None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, invalid_leg(call(), bid_price=-1), None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, invalid_leg(call(), ask_price=-1), None),)),
        snapshot(timestamp=next_ts, strikes=(strike(100, invalid_leg(call(), bid_price=11, ask_price=10), None),)),
    ]

    for bad in bad_cases:
        assert_rejected_preserves_state(oc_engine, bad)


def test_signed_change_oi_and_optional_bid_ask_are_accepted():
    oc_engine = engine()
    state = feed(
        oc_engine,
        snapshot(strikes=(strike(100, call(change=-5, bid_price=0, ask_price=0), put(change=5, bid_price=9, ask_price=10)),)),
    )

    assert state.total_call_change_oi == -5
    assert state.total_put_change_oi == 5


def test_atm_selection_uses_nearest_available_strike_and_lower_tie():
    oc_engine = engine()

    exact = feed(oc_engine, snapshot(underlying_price=100)).atm_strike
    nearest = oc_engine.update(snapshot(timestamp=TS + timedelta(minutes=1), underlying_price=107)).atm_strike
    tie = oc_engine.update(snapshot(timestamp=TS + timedelta(minutes=2), underlying_price=105)).atm_strike
    no_interval_guess = oc_engine.update(
        snapshot(
            timestamp=TS + timedelta(minutes=3),
            underlying_price=102,
            strikes=(strike(99, call()), strike(106, None, put())),
        )
    ).atm_strike

    assert exact == 100
    assert nearest == 110
    assert tie == 100
    assert no_interval_guess == 99


def test_aggregate_oi_and_missing_side_contributions():
    state = feed(
        engine(),
        snapshot(
            strikes=(
                strike(90, call(10, -2), None),
                strike(100, call(20, 5), put(40, -7)),
                strike(110, None, put(60, 8)),
            )
        ),
    )

    assert state.total_call_oi == 30
    assert state.total_put_oi == 100
    assert state.total_call_change_oi == 3
    assert state.total_put_change_oi == 1


def test_pcr_calculations_and_zero_denominators():
    state = feed(
        engine(),
        snapshot(strikes=(strike(90, call(3, -100), put(2, -50)), strike(100, call(3, 2), put(7, 5))))
    )
    assert state.oi_pcr == round(9 / 6, 4)
    assert state.change_oi_pcr == round(5 / 2, 4)

    zero_call_oi = feed(engine(), snapshot(strikes=(strike(100, call(0, 1), put(10, 1)),))).oi_pcr
    zero_positive_call_change = feed(engine(), snapshot(strikes=(strike(100, call(10, -1), put(10, 5)),))).change_oi_pcr

    assert zero_call_oi is None
    assert zero_positive_call_change is None


def test_max_oi_selection_ties_and_missing_sides():
    state = feed(
        engine(),
        snapshot(
            strikes=(
                strike(90, call(50), put(10)),
                strike(100, call(50), put(80)),
                strike(110, call(40), put(80)),
            )
        ),
    )

    assert state.max_call_oi == StrikeMetric(90, 50)
    assert state.max_put_oi == StrikeMetric(110, 80)

    zero_state = feed(engine(), snapshot(strikes=(strike(90, call(0), put(0)), strike(100, call(0), put(0)))))
    assert zero_state.max_call_oi == StrikeMetric(90, 0)
    assert zero_state.max_put_oi == StrikeMetric(100, 0)

    no_calls = feed(engine(), snapshot(strikes=(strike(100, None, put()),)))
    no_puts = feed(engine(), snapshot(strikes=(strike(100, call(), None),)))
    assert no_calls.max_call_oi is None
    assert no_puts.max_put_oi is None


def test_max_positive_change_oi_selection_ties_and_absence():
    state = feed(
        engine(),
        snapshot(
            strikes=(
                strike(90, call(change=30), put(change=10)),
                strike(100, call(change=30), put(change=40)),
                strike(110, call(change=-50), put(change=40)),
            )
        ),
    )

    assert state.max_call_change_oi == StrikeMetric(90, 30)
    assert state.max_put_change_oi == StrikeMetric(110, 40)

    no_positive = feed(engine(), snapshot(strikes=(strike(100, call(change=-1), put(change=0)),)))
    assert no_positive.max_call_change_oi is None
    assert no_positive.max_put_change_oi is None


def test_support_and_resistance_follow_max_oi_metrics():
    state = feed(engine())
    no_calls = feed(engine(), snapshot(strikes=(strike(100, None, put()),)))
    no_puts = feed(engine(), snapshot(strikes=(strike(100, call(), None),)))

    assert state.resistance_strike == state.max_call_oi.strike_price
    assert state.support_strike == state.max_put_oi.strike_price
    assert no_calls.resistance_strike is None
    assert no_puts.support_strike is None


def test_max_pain_standard_and_order_independent_cases():
    rows = (
        strike(90, call(10), put(70)),
        strike(100, call(50), put(50)),
        strike(110, call(70), put(10)),
    )
    state = feed(engine(), snapshot(strikes=rows, underlying_price=101))
    unsorted = feed(engine(), snapshot(strikes=tuple(reversed(rows)), underlying_price=101))

    assert state.max_pain_strike == 100
    assert unsorted.max_pain_strike == 100


def test_max_pain_calls_only_puts_only_and_tie_rules():
    calls_only = feed(engine(), snapshot(strikes=(strike(90, call(10), None), strike(100, call(20), None))))
    puts_only = feed(engine(), snapshot(strikes=(strike(90, None, put(20)), strike(100, None, put(10)))))
    nearest_tie = feed(engine(), snapshot(strikes=(strike(90, call(0), put(0)), strike(100, call(0), put(0)), strike(110, call(0), put(0))), underlying_price=108))
    lower_tie = feed(engine(), snapshot(strikes=(strike(90, call(0), put(0)), strike(110, call(0), put(0))), underlying_price=100))

    assert calls_only.max_pain_strike == 90
    assert puts_only.max_pain_strike == 100
    assert nearest_tie.max_pain_strike == 110
    assert lower_tie.max_pain_strike == 90


def test_max_pain_uses_oi_not_volume_or_change_oi():
    state = feed(
        engine(),
        snapshot(
            strikes=(
                strike(90, call(oi=0, change=10000, volume=999999), put(oi=100, change=10000, volume=999999)),
                strike(100, call(oi=100, change=-10000, volume=1), put(oi=100, change=-10000, volume=1)),
            )
        ),
    )

    assert state.max_pain_strike == 100


def test_pressure_classification_for_calls_and_puts():
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=1), put(change=1)),))).call_pressure is PressureType.CALL_WRITING
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=-1), put(change=1)),))).call_pressure is PressureType.CALL_UNWINDING
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=0), put(change=1)),))).call_pressure is PressureType.BALANCED
    assert feed(engine(), snapshot(strikes=(strike(100, None, put(change=1)),))).call_pressure is PressureType.UNKNOWN
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=1), put(change=1)),))).put_pressure is PressureType.PUT_WRITING
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=1), put(change=-1)),))).put_pressure is PressureType.PUT_UNWINDING
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=1), put(change=0)),))).put_pressure is PressureType.BALANCED
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=1), None),))).put_pressure is PressureType.UNKNOWN


def test_positioning_bias_rules():
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=-1), put(change=1)),))).positioning_bias is PositioningBias.BULLISH
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=0), put(change=1)),))).positioning_bias is PositioningBias.BULLISH
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=1), put(change=-1)),))).positioning_bias is PositioningBias.BEARISH
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=1), put(change=0)),))).positioning_bias is PositioningBias.BEARISH
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=0), put(change=0)),))).positioning_bias is PositioningBias.NEUTRAL
    assert feed(engine(), snapshot(strikes=(strike(100, None, put(change=1)),))).positioning_bias is PositioningBias.UNKNOWN
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=1), put(change=1)),))).positioning_bias is PositioningBias.MIXED
    assert feed(engine(), snapshot(strikes=(strike(100, call(change=-1), put(change=-1)),))).positioning_bias is PositioningBias.MIXED


def test_first_snapshot_state_cache_data_readiness_and_event_order():
    event_bus = EventBus()
    oc_engine = OptionChainEngine(event_bus, "NIFTY", "NFO", EXPIRY)
    events = []

    def on_updated(state):
        events.append((OPTION_CHAIN_UPDATED, state, oc_engine.state, oc_engine.data, oc_engine.is_ready()))

    def on_ready(state):
        events.append((OPTION_CHAIN_READY, state, oc_engine.state, oc_engine.data, oc_engine.is_ready()))

    event_bus.subscribe(OPTION_CHAIN_UPDATED, on_updated)
    event_bus.subscribe(OPTION_CHAIN_READY, on_ready)
    state = oc_engine.update(snapshot())

    assert isinstance(state, OptionChainState)
    assert oc_engine.snapshot is not None
    assert oc_engine.state is state
    assert oc_engine.data is state
    assert oc_engine.is_ready()
    assert [event[0] for event in events] == [OPTION_CHAIN_UPDATED, OPTION_CHAIN_READY]
    assert events[0][1:] == (state, state, state, True)
    assert events[1][1:] == (state, state, state, True)
    assert_raises(FrozenInstanceError, lambda: setattr(events[0][1], "atm_strike", 1))


def test_subsequent_duplicate_correction_and_newer_snapshot_events():
    event_bus = EventBus()
    events = []
    event_bus.subscribe(OPTION_CHAIN_UPDATED, lambda state: events.append((OPTION_CHAIN_UPDATED, state)))
    event_bus.subscribe(OPTION_CHAIN_READY, lambda state: events.append((OPTION_CHAIN_READY, state)))
    oc_engine = OptionChainEngine(event_bus, "NIFTY", "NFO", EXPIRY)

    first = oc_engine.update(snapshot())
    duplicate = oc_engine.update(snapshot(strikes=tuple(reversed(snapshot().strikes))))
    correction = oc_engine.update(snapshot(underlying_price=101))
    newer = oc_engine.update(snapshot(timestamp=TS + timedelta(minutes=1), underlying_price=102))

    assert duplicate is first
    assert correction is not first
    assert newer is oc_engine.state
    assert [event[0] for event in events] == [
        OPTION_CHAIN_UPDATED,
        OPTION_CHAIN_READY,
        OPTION_CHAIN_UPDATED,
        OPTION_CHAIN_UPDATED,
    ]


def test_older_snapshot_rejection_preserves_state_and_publishes_no_event():
    oc_engine = engine()
    feed(oc_engine, snapshot(timestamp=TS + timedelta(minutes=1)))

    assert_rejected_preserves_state(oc_engine, snapshot(timestamp=TS))


def test_process_reset_clear_and_ready_republication():
    event_bus = EventBus()
    events = []
    event_bus.subscribe(OPTION_CHAIN_UPDATED, lambda state: events.append(OPTION_CHAIN_UPDATED))
    event_bus.subscribe(OPTION_CHAIN_READY, lambda state: events.append(OPTION_CHAIN_READY))
    oc_engine = OptionChainEngine(event_bus, "NIFTY", "NFO", EXPIRY)

    first = oc_engine.process(snapshot(timestamp=TS + timedelta(minutes=3)))
    oc_engine.reset()

    assert first is not None
    assert oc_engine.snapshot is None
    assert oc_engine.state is None
    assert oc_engine.data is None
    assert not oc_engine.is_ready()
    assert events == [OPTION_CHAIN_UPDATED, OPTION_CHAIN_READY]

    second = oc_engine.update(snapshot(timestamp=TS))
    assert second is oc_engine.state
    assert events == [OPTION_CHAIN_UPDATED, OPTION_CHAIN_READY, OPTION_CHAIN_UPDATED, OPTION_CHAIN_READY]

    oc_engine.clear()
    assert oc_engine.snapshot is None
    assert oc_engine.state is None
    assert oc_engine.data is None
    assert not oc_engine.is_ready()
    assert events == [OPTION_CHAIN_UPDATED, OPTION_CHAIN_READY, OPTION_CHAIN_UPDATED, OPTION_CHAIN_READY]


def test_two_engines_and_expiry_contexts_are_independent():
    first = OptionChainEngine(EventBus(), "NIFTY", "NFO", EXPIRY)
    second_expiry = date(2026, 8, 6)
    second = OptionChainEngine(EventBus(), "NIFTY", "NFO", second_expiry)
    bank = OptionChainEngine(EventBus(), "BANKNIFTY", "NFO", EXPIRY)

    first_state = first.update(snapshot())
    second_state = second.update(snapshot(expiry=second_expiry))
    bank_state = bank.update(snapshot(symbol="BANKNIFTY"))

    first.reset()

    assert first.state is None
    assert second.state == second_state
    assert bank.state == bank_state
    assert second.state != first_state
    assert_raises(ValueError, lambda: second.update(snapshot(expiry=EXPIRY)))
    assert_raises(ValueError, lambda: bank.update(snapshot(symbol="NIFTY")))