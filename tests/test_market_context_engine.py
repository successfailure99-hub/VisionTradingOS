"""
Tests for Market Context Engine V1.
"""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone

from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import MARKET_CONTEXT_UPDATED
from core.models.candle import Candle
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context import (
    AgreementState,
    CamarillaZone,
    ContextEvidence,
    ContextStrength,
    CPRPosition,
    EvidenceDirection,
    MarketBias,
    MarketContextEngine,
    MarketContextSnapshot,
    MarketContextState,
    MarketPhase,
    VWAPPosition,
)
from engines.option_chain.enums import PositioningBias, PressureType
from engines.option_chain.models import OptionChainState
from engines.price_action.enums import BreakType, Trend
from engines.price_action.models import PriceActionState, StructureBreak
from engines.vwap.levels import VWAPLevels


DAY = date(2026, 7, 10)
TS = datetime(2026, 7, 10, 10, 0)


def assert_raises(expected_error, callback):
    try:
        callback()
    except expected_error:
        return
    raise AssertionError(f"Expected {expected_error}")


def candle(close=100, symbol="NIFTY", timeframe="1m", start=None, end=None):
    start = start or TS - timedelta(minutes=1)
    end = end or TS
    return Candle(symbol, timeframe, start, end, close, close, close, close, 100)


def price_action(trend=Trend.BULLISH, symbol="NIFTY", timeframe="1m", break_type=None, break_current=True):
    last = candle(symbol=symbol, timeframe=timeframe)
    latest_break = None
    if break_type is not None:
        if break_current:
            start, end = last.start_time, last.end_time
        else:
            start, end = last.start_time - timedelta(minutes=1), last.end_time - timedelta(minutes=1)
        latest_break = StructureBreak(break_type, 99, 101, start, end)
    return PriceActionState(symbol, timeframe, 1, last, trend, None, None, None, None, latest_break)


def option_chain(bias=PositioningBias.BULLISH, symbol="NIFTY", timestamp=TS):
    return OptionChainState(
        symbol=symbol,
        exchange="NFO",
        expiry_date=date(2026, 7, 30),
        timestamp=timestamp,
        underlying_price=100,
        atm_strike=100,
        strike_count=1,
        total_call_oi=100,
        total_put_oi=100,
        total_call_change_oi=0,
        total_put_change_oi=0,
        oi_pcr=1,
        change_oi_pcr=None,
        max_call_oi=None,
        max_put_oi=None,
        max_call_change_oi=None,
        max_put_change_oi=None,
        resistance_strike=None,
        support_strike=None,
        max_pain_strike=100,
        call_pressure=PressureType.BALANCED,
        put_pressure=PressureType.BALANCED,
        positioning_bias=bias,
        strikes=(),
    )


def vwap(value=99, symbol=Instrument.NIFTY, trading_date=DAY, timestamp=TS):
    return VWAPLevels(symbol, trading_date, timestamp, value, 100, value * 100)


def cpr(bc=95, tc=98, trading_date=DAY):
    return CPRLevels(trading_date, 110, 90, 100, 100, bc, tc, tc - bc, 3)


def camarilla(trading_date=DAY, **overrides):
    values = {
        "trading_date": trading_date,
        "previous_high": 120,
        "previous_low": 80,
        "previous_close": 100,
        "pivot": 100,
        "h3": 104,
        "h4": 108,
        "h5": 112,
        "h6": 116,
        "l3": 96,
        "l4": 92,
        "l5": 88,
        "l6": 84,
    }
    values.update(overrides)
    return CamarillaLevels(**values)


def snapshot(
    timestamp=TS,
    current_price=100,
    session_high=105,
    session_low=95,
    symbol="NIFTY",
    timeframe="1m",
    pa=None,
    oc=None,
    vw=None,
    cp=None,
    cam=None,
):
    return MarketContextSnapshot(
        symbol,
        timeframe,
        timestamp,
        current_price,
        session_high,
        session_low,
        pa,
        oc,
        vw,
        cp,
        cam,
    )


def engine(symbol=" nifty ", timeframe=" 1m "):
    return MarketContextEngine(EventBus(), symbol, timeframe)


def feed(mc_engine, mc_snapshot=None):
    return mc_engine.update(mc_snapshot or snapshot(pa=price_action(), oc=option_chain()))


def assert_rejected_preserves_state(mc_engine, bad_snapshot, expected_error=ValueError):
    old_snapshot = mc_engine.snapshot
    old_state = mc_engine.state
    old_data = mc_engine.data
    old_ready = mc_engine.is_ready()
    events = []
    mc_engine._event_bus.subscribe(MARKET_CONTEXT_UPDATED, events.append)

    assert_raises(expected_error, lambda: mc_engine.update(bad_snapshot))

    assert mc_engine.snapshot == old_snapshot
    assert mc_engine.state == old_state
    assert mc_engine.data == old_data
    assert mc_engine.is_ready() == old_ready
    assert events == []


def test_enum_values_models_and_exports():
    assert MarketBias.BULLISH.value == "bullish"
    assert MarketPhase.BREAKOUT_UP.value == "breakout_up"
    assert AgreementState.CONFLICTED.value == "conflicted"
    assert ContextStrength.INSUFFICIENT.value == "insufficient"
    assert VWAPPosition.AT.value == "at"
    assert CPRPosition.INSIDE.value == "inside"
    assert CamarillaZone.L3_TO_H3.value == "l3_to_h3"
    assert EvidenceDirection.MIXED.value == "mixed"

    evidence = ContextEvidence("price_action", EvidenceDirection.BULLISH, "detail")
    snap = snapshot()
    state = feed(engine())
    assert_raises(FrozenInstanceError, lambda: setattr(evidence, "detail", "x"))
    assert_raises(FrozenInstanceError, lambda: setattr(snap, "symbol", "BANKNIFTY"))
    assert_raises(FrozenInstanceError, lambda: setattr(state, "market_bias", MarketBias.BEARISH))
    assert_raises((FrozenInstanceError, TypeError), lambda: setattr(state, "extra", 1))

    from engines.market_context import __all__
    assert __all__ == [
        "MarketContextEngine",
        "MarketContextCalculator",
        "MarketContextSnapshot",
        "MarketContextState",
        "ContextEvidence",
        "MarketBias",
        "MarketPhase",
        "AgreementState",
        "ContextStrength",
        "VWAPPosition",
        "CPRPosition",
        "CamarillaZone",
        "EvidenceDirection",
    ]


def test_constructor_initial_state_and_invalid_context():
    mc = engine()
    assert mc.symbol == "NIFTY"
    assert mc.timeframe == "1m"
    assert mc.snapshot is None
    assert mc.state is None
    assert mc.data is None
    assert not mc.is_ready()
    assert_raises(ValueError, lambda: MarketContextEngine(EventBus(), "", "1m"))
    assert_raises(ValueError, lambda: MarketContextEngine(EventBus(), 1, "1m"))
    assert_raises(ValueError, lambda: MarketContextEngine(EventBus(), "NIFTY", ""))
    assert_raises(ValueError, lambda: MarketContextEngine(EventBus(), "NIFTY", 1))


def test_snapshot_validation_and_atomic_rejection():
    mc = engine()
    feed(mc)
    assert_rejected_preserves_state(mc, object(), TypeError)
    assert_rejected_preserves_state(mc, snapshot(symbol="BANKNIFTY"))
    assert_rejected_preserves_state(mc, snapshot(timeframe="5m"))
    assert_rejected_preserves_state(mc, snapshot(timestamp="bad"))
    assert_rejected_preserves_state(mc, snapshot(timestamp=TS.replace(tzinfo=timezone.utc)))
    for kwargs in (
        {"current_price": 0}, {"session_high": -1}, {"session_low": True},
        {"current_price": float("nan")}, {"session_high": float("inf")},
        {"session_high": 90, "session_low": 95}, {"current_price": 110},
        {"current_price": 90},
    ):
        assert_rejected_preserves_state(mc, snapshot(timestamp=TS + timedelta(minutes=1), **kwargs))

    zero = feed(engine(), snapshot(current_price=100, session_high=100, session_low=100))
    assert zero.current_price == 100


def test_upstream_validation_rules():
    mc = engine()
    feed(mc)
    later = TS + timedelta(minutes=1)
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, pa=object()))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, pa=price_action(symbol="BANKNIFTY")))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, pa=price_action(timeframe="5m")))
    future_pa = price_action()
    future_pa = PriceActionState("NIFTY", "1m", 1, candle(end=later + timedelta(minutes=1)), Trend.BULLISH, None, None, None, None, None)
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, pa=future_pa))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, oc=object()))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, oc=option_chain(symbol="BANKNIFTY")))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, oc=option_chain(timestamp=later + timedelta(minutes=1))))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, vw=object()))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, vw=vwap(symbol=Instrument.BANKNIFTY)))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, vw=vwap(trading_date=DAY + timedelta(days=1))))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, vw=vwap(timestamp=later + timedelta(minutes=1))))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, cp=object()))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, cp=cpr(trading_date=DAY + timedelta(days=1))))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, cp=cpr(bc=100, tc=99)))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, cam=object()))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, cam=camarilla(trading_date=DAY + timedelta(days=1))))
    assert_rejected_preserves_state(mc, snapshot(timestamp=later, cam=camarilla(h4=103)))


def test_price_action_and_option_chain_direction_mapping():
    cases = [
        (Trend.BULLISH, EvidenceDirection.BULLISH),
        (Trend.BEARISH, EvidenceDirection.BEARISH),
        (Trend.RANGE, EvidenceDirection.NEUTRAL),
        (Trend.UNKNOWN, EvidenceDirection.UNKNOWN),
    ]
    for trend, expected in cases:
        assert feed(engine(), snapshot(pa=price_action(trend=trend))).price_action_direction is expected
    assert feed(engine(), snapshot()).price_action_direction is EvidenceDirection.UNKNOWN

    oc_cases = [
        (PositioningBias.BULLISH, EvidenceDirection.BULLISH),
        (PositioningBias.BEARISH, EvidenceDirection.BEARISH),
        (PositioningBias.NEUTRAL, EvidenceDirection.NEUTRAL),
        (PositioningBias.MIXED, EvidenceDirection.MIXED),
        (PositioningBias.UNKNOWN, EvidenceDirection.UNKNOWN),
    ]
    for bias, expected in oc_cases:
        assert feed(engine(), snapshot(oc=option_chain(bias=bias))).option_chain_direction is expected
    assert feed(engine(), snapshot()).option_chain_direction is EvidenceDirection.UNKNOWN


def test_vwap_cpr_virgin_cpr_and_camarilla_classification():
    assert feed(engine(), snapshot(current_price=101, vw=vwap(100))).vwap_position is VWAPPosition.ABOVE
    assert feed(engine(), snapshot(current_price=99, vw=vwap(100))).vwap_position is VWAPPosition.BELOW
    assert feed(engine(), snapshot(current_price=100, vw=vwap(100))).vwap_position is VWAPPosition.AT
    assert feed(engine(), snapshot()).vwap_position is VWAPPosition.UNAVAILABLE

    assert feed(engine(), snapshot(current_price=101, cp=cpr(95, 98))).cpr_position is CPRPosition.ABOVE
    assert feed(engine(), snapshot(current_price=94, session_low=90, cp=cpr(95, 98))).cpr_position is CPRPosition.BELOW
    assert feed(engine(), snapshot(current_price=96, cp=cpr(95, 98))).cpr_position is CPRPosition.INSIDE
    assert feed(engine(), snapshot(current_price=95, cp=cpr(95, 98))).cpr_position is CPRPosition.INSIDE
    assert feed(engine(), snapshot(current_price=98, cp=cpr(95, 98))).cpr_position is CPRPosition.INSIDE
    assert feed(engine(), snapshot()).cpr_position is CPRPosition.UNAVAILABLE
    assert feed(engine(), snapshot(current_price=105, session_low=103, session_high=110, cp=cpr(95, 98))).virgin_cpr is True
    assert feed(engine(), snapshot(current_price=90, session_low=85, session_high=94, cp=cpr(95, 98))).virgin_cpr is True
    assert feed(engine(), snapshot(current_price=100, session_low=94, session_high=105, cp=cpr(95, 98))).virgin_cpr is False
    assert feed(engine(), snapshot(current_price=100, session_low=95, session_high=105, cp=cpr(95, 98))).virgin_cpr is False
    assert feed(engine(), snapshot(current_price=98, session_low=90, session_high=98, cp=cpr(95, 98))).virgin_cpr is False
    assert feed(engine(), snapshot()).virgin_cpr is None

    zone_cases = [
        (117, CamarillaZone.ABOVE_H6), (116, CamarillaZone.H5_TO_H6),
        (112, CamarillaZone.H4_TO_H5), (108, CamarillaZone.H3_TO_H4),
        (104, CamarillaZone.L3_TO_H3), (96, CamarillaZone.L3_TO_H3),
        (95, CamarillaZone.L4_TO_L3), (91, CamarillaZone.L5_TO_L4),
        (87, CamarillaZone.L6_TO_L5), (83, CamarillaZone.BELOW_L6),
    ]
    for price, expected in zone_cases:
        assert feed(engine(), snapshot(current_price=price, session_low=80, session_high=120, cam=camarilla())).camarilla_zone is expected
    assert feed(engine(), snapshot()).camarilla_zone is CamarillaZone.UNAVAILABLE


def test_agreement_bias_and_secondary_rules():
    assert feed(engine(), snapshot(pa=price_action(Trend.BULLISH), oc=option_chain(PositioningBias.BULLISH))).agreement is AgreementState.ALIGNED
    assert feed(engine(), snapshot(pa=price_action(Trend.BEARISH), oc=option_chain(PositioningBias.BEARISH))).agreement is AgreementState.ALIGNED
    conflict = feed(engine(), snapshot(pa=price_action(Trend.BULLISH), oc=option_chain(PositioningBias.BEARISH), vw=vwap(90), cp=cpr(90, 95), cam=camarilla()))
    assert conflict.agreement is AgreementState.CONFLICTED
    assert conflict.market_bias is MarketBias.MIXED
    assert conflict.context_strength is ContextStrength.WEAK
    assert feed(engine(), snapshot(pa=price_action(Trend.BEARISH), oc=option_chain(PositioningBias.BULLISH))).agreement is AgreementState.CONFLICTED
    assert feed(engine(), snapshot(pa=price_action(Trend.BULLISH))).agreement is AgreementState.PARTIAL
    assert feed(engine(), snapshot(pa=price_action(Trend.RANGE), oc=option_chain(PositioningBias.NEUTRAL))).agreement is AgreementState.PARTIAL
    assert feed(engine(), snapshot()).agreement is AgreementState.INSUFFICIENT
    assert feed(engine(), snapshot(pa=price_action(Trend.BULLISH))).market_bias is MarketBias.BULLISH
    assert feed(engine(), snapshot(oc=option_chain(PositioningBias.BEARISH))).market_bias is MarketBias.BEARISH
    assert feed(engine(), snapshot(oc=option_chain(PositioningBias.MIXED))).market_bias is MarketBias.MIXED
    assert feed(engine(), snapshot(pa=price_action(Trend.RANGE), oc=option_chain(PositioningBias.NEUTRAL))).market_bias is MarketBias.NEUTRAL
    assert feed(engine(), snapshot(vw=vwap(90), cp=cpr(90, 95), cam=camarilla())).market_bias is MarketBias.UNKNOWN


def test_market_phase_rules():
    cases = [
        (BreakType.BULLISH_BOS, MarketPhase.BREAKOUT_UP),
        (BreakType.BEARISH_BOS, MarketPhase.BREAKOUT_DOWN),
        (BreakType.BULLISH_CHOCH, MarketPhase.REVERSAL_UP),
        (BreakType.BEARISH_CHOCH, MarketPhase.REVERSAL_DOWN),
    ]
    for break_type, expected in cases:
        assert feed(engine(), snapshot(pa=price_action(trend=Trend.BULLISH, break_type=break_type))).market_phase is expected
    assert feed(engine(), snapshot(pa=price_action(trend=Trend.BULLISH, break_type=BreakType.BULLISH_BOS, break_current=False))).market_phase is MarketPhase.TRENDING_UP
    assert feed(engine(), snapshot(pa=price_action(Trend.BULLISH))).market_phase is MarketPhase.TRENDING_UP
    assert feed(engine(), snapshot(pa=price_action(Trend.BEARISH))).market_phase is MarketPhase.TRENDING_DOWN
    assert feed(engine(), snapshot(pa=price_action(Trend.RANGE))).market_phase is MarketPhase.RANGE
    assert feed(engine(), snapshot()).market_phase is MarketPhase.UNKNOWN
    assert feed(engine(), snapshot(pa=price_action(Trend.UNKNOWN))).market_phase is MarketPhase.UNKNOWN


def test_evidence_counts_missing_sources_and_strength():
    state = feed(engine(), snapshot(pa=price_action(Trend.BULLISH), oc=option_chain(PositioningBias.BULLISH), vw=vwap(99), cp=cpr(95, 98), cam=camarilla()))
    assert tuple(item.source for item in state.evidence) == ("price_action", "option_chain", "vwap", "cpr", "camarilla")
    assert state.bullish_evidence_count == 4
    assert state.bearish_evidence_count == 0
    assert state.neutral_evidence_count == 1
    assert state.mixed_evidence_count == 0
    assert state.available_source_count == 5
    assert state.missing_sources == ()
    assert state.context_strength is ContextStrength.STRONG

    unknown_present = feed(engine(), snapshot(pa=price_action(Trend.UNKNOWN)))
    assert unknown_present.missing_sources == ("option_chain", "vwap", "cpr", "camarilla")
    assert unknown_present.available_source_count == 0

    moderate_aligned = feed(engine(), snapshot(pa=price_action(Trend.BULLISH), oc=option_chain(PositioningBias.BULLISH), vw=vwap(101)))
    assert moderate_aligned.context_strength is ContextStrength.MODERATE
    moderate_partial = feed(engine(), snapshot(pa=price_action(Trend.BULLISH), vw=vwap(99), cp=cpr(95, 98)))
    assert moderate_partial.context_strength is ContextStrength.MODERATE
    weak_partial = feed(engine(), snapshot(pa=price_action(Trend.BULLISH), vw=vwap(101)))
    assert weak_partial.context_strength is ContextStrength.WEAK
    insufficient = feed(engine(), snapshot(vw=vwap(99), cp=cpr(95, 98)))
    assert insufficient.context_strength is ContextStrength.INSUFFICIENT
    virgin_only = feed(engine(), snapshot(pa=price_action(Trend.BULLISH), session_low=103, session_high=110, current_price=105, cp=cpr(95, 98)))
    assert virgin_only.context_strength is ContextStrength.WEAK


def test_engine_lifecycle_events_duplicates_and_independence():
    bus = EventBus()
    events = []
    mc = MarketContextEngine(bus, "NIFTY", "1m")
    bus.subscribe(MARKET_CONTEXT_UPDATED, lambda state: events.append((state, mc.state, mc.data, mc.is_ready())))

    first_snapshot = snapshot(pa=price_action(), oc=option_chain())
    first = mc.update(first_snapshot)
    duplicate = mc.update(first_snapshot)
    correction = mc.update(snapshot(pa=price_action(Trend.BEARISH), oc=option_chain(PositioningBias.BEARISH)))
    newer = mc.update(snapshot(timestamp=TS + timedelta(minutes=1), pa=price_action(Trend.BEARISH), oc=option_chain(PositioningBias.BEARISH)))

    assert isinstance(first, MarketContextState)
    assert mc.state is first or mc.state is newer
    assert mc.data is mc.state
    assert mc.is_ready()
    assert events[0] == (first, first, first, True)
    assert_raises(FrozenInstanceError, lambda: setattr(events[0][0], "market_bias", MarketBias.BEARISH))
    assert duplicate is first
    assert correction is not first
    assert newer is mc.state
    assert len(events) == 3
    assert_rejected_preserves_state(mc, snapshot(timestamp=TS - timedelta(minutes=1)))

    processed = mc.process(snapshot(timestamp=TS + timedelta(minutes=2)))
    assert processed is mc.state
    assert len(events) == 4
    mc.reset()
    assert mc.snapshot is None and mc.state is None and mc.data is None and not mc.is_ready()
    assert len(events) == 4
    early = mc.update(snapshot(timestamp=TS - timedelta(minutes=5)))
    assert early is mc.state
    mc.clear()
    assert mc.snapshot is None and mc.state is None and mc.data is None and not mc.is_ready()

    first_engine = MarketContextEngine(EventBus(), "NIFTY", "1m")
    second_engine = MarketContextEngine(EventBus(), "BANKNIFTY", "1m")
    first_state = first_engine.update(snapshot())
    second_state = second_engine.update(snapshot(symbol="BANKNIFTY"))
    first_engine.reset()
    assert first_engine.state is None
    assert second_engine.state == second_state
    assert second_engine.state != first_state