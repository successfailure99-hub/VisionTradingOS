from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone

import pytest

from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from application.orchestrator import ApplicationOrchestrator
from core.event_bus import EventBus
from core.events import (
    TRADINGVIEW_EVIDENCE_FAILED,
    TRADINGVIEW_EVIDENCE_INVALID,
    TRADINGVIEW_EVIDENCE_MAPPED,
    TRADINGVIEW_EVIDENCE_PARTIAL,
    TRADINGVIEW_EVIDENCE_STATE_UPDATED,
)
from core.models.candle import Candle
from core.models.tick import Tick
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context.enums import (
    AgreementState,
    CPRPosition,
    CamarillaZone,
    ContextStrength,
    EvidenceDirection,
    MarketBias,
    MarketPhase,
    VWAPPosition,
)
from engines.market_context.models import MarketContextState
from engines.option_chain.enums import PositioningBias, PressureType
from engines.option_chain.models import OptionChainState
from engines.price_action.enums import MarketStructure, Trend
from engines.price_action.models import PriceActionState
from engines.tradingview_evidence import (
    CPRRegion,
    CamarillaRegion,
    EvidenceAvailability,
    EvidenceStatus,
    LevelDistance,
    MovingAverageObservation,
    PriceLocation,
    TradingViewEvidenceEngineSnapshot,
    TradingViewEvidenceLifecycle,
    TradingViewEvidenceMappingEngine,
    TradingViewEvidenceRequest,
    TradingViewEvidenceSnapshot,
)
from engines.vwap.levels import VWAPLevels


NOW = datetime(2026, 7, 21, 9, 30, tzinfo=timezone.utc)


def candle(*, end_time=NOW, close=100.0) -> Candle:
    return Candle(
        symbol="NIFTY",
        timeframe="1m",
        start_time=end_time - timedelta(minutes=1),
        end_time=end_time,
        open=99.0,
        high=101.0,
        low=98.0,
        close=close,
        volume=1000,
    )


def camarilla() -> CamarillaLevels:
    return CamarillaLevels(
        trading_date=NOW.date(),
        previous_high=110.0,
        previous_low=90.0,
        previous_close=100.0,
        pivot=100.0,
        h3=103.0,
        h4=104.0,
        h5=105.0,
        h6=106.0,
        l3=97.0,
        l4=96.0,
        l5=95.0,
        l6=94.0,
    )


def cpr(*, bc=99.0, tc=101.0) -> CPRLevels:
    return CPRLevels(
        trading_date=NOW.date(),
        previous_high=110.0,
        previous_low=90.0,
        previous_close=100.0,
        pivot=100.0,
        bc=bc,
        tc=tc,
        width=abs(tc - bc),
        width_percentage=2.0,
    )


def vwap(*, timestamp=NOW, value=100.0) -> VWAPLevels:
    return VWAPLevels(
        symbol=Instrument.NIFTY,
        trading_date=timestamp.date(),
        timestamp=timestamp,
        vwap=value,
        cumulative_volume=1000,
        cumulative_price_volume=value * 1000,
    )


def price_action() -> PriceActionState:
    last = candle()
    return PriceActionState(
        symbol="NIFTY",
        timeframe="1m",
        candle_count=1,
        last_candle=last,
        trend=Trend.RANGE,
        latest_swing_high=None,
        latest_swing_low=None,
        previous_swing_high=None,
        previous_swing_low=None,
        latest_break=None,
        market_structure=MarketStructure.RANGE,
        updated_at=last.end_time,
    )


def market_context() -> MarketContextState:
    return MarketContextState(
        symbol="NIFTY",
        timeframe="1m",
        timestamp=NOW,
        current_price=100.0,
        session_high=102.0,
        session_low=98.0,
        market_bias=MarketBias.NEUTRAL,
        market_phase=MarketPhase.RANGE,
        agreement=AgreementState.PARTIAL,
        context_strength=ContextStrength.WEAK,
        price_action_direction=EvidenceDirection.NEUTRAL,
        option_chain_direction=EvidenceDirection.UNKNOWN,
        vwap_position=VWAPPosition.AT,
        cpr_position=CPRPosition.INSIDE,
        virgin_cpr=None,
        camarilla_zone=CamarillaZone.L3_TO_H3,
        bullish_evidence_count=0,
        bearish_evidence_count=0,
        neutral_evidence_count=1,
        mixed_evidence_count=0,
        available_source_count=4,
        evidence=(),
        missing_sources=(),
    )


def option_chain() -> OptionChainState:
    return OptionChainState(
        symbol="NIFTY",
        exchange="NSE",
        expiry_date=date(2026, 7, 30),
        timestamp=NOW,
        underlying_price=100.0,
        atm_strike=100.0,
        strike_count=0,
        total_call_oi=0,
        total_put_oi=0,
        total_call_change_oi=0,
        total_put_change_oi=0,
        oi_pcr=None,
        change_oi_pcr=None,
        max_call_oi=None,
        max_put_oi=None,
        max_call_change_oi=None,
        max_put_change_oi=None,
        resistance_strike=None,
        support_strike=None,
        max_pain_strike=None,
        call_pressure=PressureType.UNKNOWN,
        put_pressure=PressureType.UNKNOWN,
        positioning_bias=PositioningBias.NEUTRAL,
        strikes=(),
    )


def request(**overrides) -> TradingViewEvidenceRequest:
    data = {
        "evidence_id": "evidence-1",
        "timestamp": NOW,
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": "1m",
        "latest_price": 100.0,
        "latest_candle": candle(),
        "camarilla": camarilla(),
        "cpr": cpr(),
        "vwap": vwap(),
        "adr": None,
        "price_action": price_action(),
        "market_context": market_context(),
        "option_chain": option_chain(),
        "moving_averages": (),
        "momentum": None,
        "volume": None,
        "correlation_id": "corr-1",
    }
    data.update(overrides)
    return TradingViewEvidenceRequest(**data)


def engine(bus=None) -> TradingViewEvidenceMappingEngine:
    item = TradingViewEvidenceMappingEngine(bus or EventBus(), instrument="NIFTY", timeframe="1m")
    item.start()
    return item


def map_request(**overrides) -> TradingViewEvidenceSnapshot:
    return engine().map_evidence(request(**overrides))


def test_models_are_immutable_validate_timestamp_instrument_price_tuple_and_safety():
    status = EvidenceStatus("latest_price", EvidenceAvailability.AVAILABLE, NOW, 0, None)
    distance = LevelDistance("H3", 103.0, -3.0, -2.912621359, PriceLocation.BELOW)
    moving_average = MovingAverageObservation("EMA", 20, 100.0, PriceLocation.AT, None, EvidenceAvailability.AVAILABLE)
    req = request(moving_averages=[moving_average])
    result = map_request(moving_averages=(moving_average,))
    snapshot = engine().snapshot()

    for item in (status, distance, moving_average, req, result, snapshot):
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            item.extra = "blocked"

    with pytest.raises(ValueError, match="timezone-aware"):
        request(timestamp=datetime(2026, 7, 21, 9, 30))
    with pytest.raises(TypeError, match="instrument"):
        request(instrument="NIFTY")
    for bad_price in (0, -1, float("nan"), float("inf"), True):
        with pytest.raises((TypeError, ValueError)):
            request(latest_price=bad_price)
    assert isinstance(req.moving_averages, tuple)
    assert result.strategy_calls == 0
    assert result.risk_calls == 0
    assert result.execution_policy_calls == 0
    assert result.authorization_calls == 0
    assert result.paper_execution_calls == 0
    assert result.broker_order_calls == 0
    assert result.trade_decision_generated is False
    assert result.live_order_submission_enabled is False
    assert snapshot.broker_order_calls == 0
    assert snapshot.trade_decision_generated is False
    assert snapshot.live_order_submission_enabled is False


def test_future_source_timestamp_is_rejected():
    with pytest.raises(ValueError, match="source timestamp"):
        request(vwap=vwap(timestamp=NOW + timedelta(seconds=1)))


def test_lifecycle_stop_failed_reset_and_expected_mapping_outcomes_are_safe():
    bus = EventBus()
    business_events = []
    for name in (TRADINGVIEW_EVIDENCE_MAPPED, TRADINGVIEW_EVIDENCE_PARTIAL, TRADINGVIEW_EVIDENCE_INVALID):
        bus.subscribe(name, lambda payload, name=name: business_events.append((name, payload)))
    item = TradingViewEvidenceMappingEngine(bus, instrument="NIFTY", timeframe="1m")
    assert item.snapshot().lifecycle_state is TradingViewEvidenceLifecycle.CREATED
    assert item.start().lifecycle_state is TradingViewEvidenceLifecycle.READY
    first = item.map_evidence(request())
    assert first.camarilla_status.availability is EvidenceAvailability.AVAILABLE
    assert item.snapshot().lifecycle_state is TradingViewEvidenceLifecycle.ACTIVE
    second = item.map_evidence(request(evidence_id="evidence-2", latest_price=101.0))
    assert second.evidence_id == "evidence-2"
    assert item.snapshot().lifecycle_state is TradingViewEvidenceLifecycle.ACTIVE
    assert item.stop().lifecycle_state is TradingViewEvidenceLifecycle.STOPPED
    before = item.snapshot()
    business_events.clear()
    with pytest.raises(RuntimeError, match="stopped"):
        item.map_evidence(request(evidence_id="stopped"))
    assert item.snapshot() == before
    assert item.get_evidence("stopped") is None
    assert business_events == []
    assert item.reset().lifecycle_state is TradingViewEvidenceLifecycle.READY
    item._lifecycle_state = TradingViewEvidenceLifecycle.FAILED
    with pytest.raises(RuntimeError, match="failed"):
        item.map_evidence(request(evidence_id="failed"))
    assert item.reset().lifecycle_state is TradingViewEvidenceLifecycle.READY
    missing = item.map_evidence(request(evidence_id="missing", latest_price=None))
    invalid = item.map_evidence(request(evidence_id="invalid", camarilla=object()))
    stale = item.map_evidence(request(evidence_id="stale", vwap=vwap(timestamp=NOW - timedelta(seconds=301))))
    assert missing.latest_price_status.availability is EvidenceAvailability.MISSING
    assert invalid.camarilla_status.availability is EvidenceAvailability.INVALID
    assert stale.vwap_status.availability is EvidenceAvailability.STALE
    assert item.snapshot().lifecycle_state is TradingViewEvidenceLifecycle.ACTIVE


@pytest.mark.parametrize(
    ("price", "expected"),
    (
        (106.1, CamarillaRegion.ABOVE_H6),
        (105.5, CamarillaRegion.H5_H6),
        (104.5, CamarillaRegion.H4_H5),
        (103.5, CamarillaRegion.H3_H4),
        (100.0, CamarillaRegion.L3_H3),
        (96.5, CamarillaRegion.L4_L3),
        (95.5, CamarillaRegion.L5_L4),
        (94.5, CamarillaRegion.L6_L5),
        (93.9, CamarillaRegion.BELOW_L6),
        (103.0, CamarillaRegion.L3_H3),
        (104.0, CamarillaRegion.H3_H4),
        (105.0, CamarillaRegion.H4_H5),
        (106.0, CamarillaRegion.H5_H6),
        (97.0, CamarillaRegion.L3_H3),
        (96.0, CamarillaRegion.L4_L3),
        (95.0, CamarillaRegion.L5_L4),
        (94.0, CamarillaRegion.L6_L5),
    ),
)
def test_camarilla_region_boundaries_are_deterministic(price, expected):
    result = map_request(latest_price=price)
    assert result.camarilla_region is expected
    assert tuple(distance.level_name for distance in result.camarilla_distances) == ("H3", "H4", "H5", "H6", "L3", "L4", "L5", "L6")
    h3 = result.camarilla_distances[0]
    assert h3.absolute_points == pytest.approx(price - 103.0)
    assert h3.percentage == pytest.approx(((price - 103.0) / 103.0) * 100)


def test_camarilla_nearest_level_signed_distance_percentage_tie_and_input_unchanged():
    levels = camarilla()
    result = map_request(latest_price=103.5, camarilla=levels)
    assert result.nearest_camarilla_level.level_name == "H3"
    assert result.nearest_camarilla_level.absolute_points == pytest.approx(0.5)
    assert result.camarilla_distances[1].absolute_points == pytest.approx(-0.5)
    assert result.camarilla_distances[1].price_location is PriceLocation.BELOW
    assert levels.h3 == 103.0


@pytest.mark.parametrize(
    ("price", "bc", "tc", "expected"),
    (
        (102.0, 99.0, 101.0, CPRRegion.ABOVE_CPR),
        (100.0, 99.0, 101.0, CPRRegion.INSIDE_CPR),
        (98.0, 99.0, 101.0, CPRRegion.BELOW_CPR),
        (99.0, 99.0, 101.0, CPRRegion.INSIDE_CPR),
        (101.0, 99.0, 101.0, CPRRegion.INSIDE_CPR),
        (100.0, 101.0, 99.0, CPRRegion.INSIDE_CPR),
    ),
)
def test_cpr_region_distances_reversed_bounds_and_input_unchanged(price, bc, tc, expected):
    levels = cpr(bc=bc, tc=tc)
    result = map_request(latest_price=price, cpr=levels)
    assert result.cpr_region is expected
    assert result.cpr_distance_to_pivot == pytest.approx(price - 100.0)
    assert result.cpr_distance_to_bc == pytest.approx(price - bc)
    assert result.cpr_distance_to_tc == pytest.approx(price - tc)
    assert levels.bc == bc
    assert levels.tc == tc


@pytest.mark.parametrize(
    ("price", "expected"),
    ((101.0, PriceLocation.ABOVE), (99.0, PriceLocation.BELOW), (100.0, PriceLocation.AT)),
)
def test_vwap_location_distance_percentage_and_input_unchanged(price, expected):
    levels = vwap(value=100.0)
    result = map_request(latest_price=price, vwap=levels)
    assert result.vwap_location is expected
    assert result.vwap_distance_points == pytest.approx(price - 100.0)
    assert result.vwap_distance_percentage == pytest.approx(((price - 100.0) / 100.0) * 100)
    assert levels.vwap == 100.0


def test_availability_missing_invalid_stale_ordering_and_partial_complete_counts():
    item = engine()
    complete = item.map_evidence(request(evidence_id="complete"))
    partial_missing = item.map_evidence(request(evidence_id="partial-missing", latest_candle=None))
    partial_invalid = item.map_evidence(request(evidence_id="partial-invalid", cpr=object()))
    partial_stale = item.map_evidence(request(evidence_id="partial-stale", vwap=vwap(timestamp=NOW - timedelta(seconds=301))))
    optional_missing = item.map_evidence(
        request(
            evidence_id="optional-missing",
            adr=None,
            option_chain=None,
            moving_averages=(),
            momentum=None,
            volume=None,
        )
    )
    assert complete.latest_price_status.availability is EvidenceAvailability.AVAILABLE
    assert partial_missing.latest_candle_status.availability is EvidenceAvailability.MISSING
    assert partial_invalid.cpr_status.availability is EvidenceAvailability.INVALID
    assert partial_stale.vwap_status.availability is EvidenceAvailability.STALE
    assert optional_missing.option_chain_status.availability is EvidenceAvailability.MISSING
    assert optional_missing.momentum_status.availability is EvidenceAvailability.MISSING
    assert optional_missing.adr_status.availability is EvidenceAvailability.MISSING
    assert "latest_candle" in partial_missing.missing_evidence
    assert "cpr" in partial_invalid.invalid_evidence
    assert "vwap" in partial_stale.stale_evidence
    assert optional_missing.missing_evidence == (
        "adr",
        "option_chain",
        "moving_averages",
        "momentum",
        "volume",
    )
    snapshot = item.snapshot()
    assert snapshot.mapping_count == 5
    assert snapshot.available_mapping_count == 2
    assert snapshot.partial_mapping_count == 3
    assert snapshot.invalid_mapping_count == 1


def test_source_without_timestamp_is_available_when_model_is_valid_and_latest_price_missing_unknowns():
    result = map_request(latest_price=None)
    assert result.camarilla_status.source_timestamp is None
    assert result.camarilla_status.availability is EvidenceAvailability.AVAILABLE
    assert result.camarilla_region is CamarillaRegion.UNKNOWN
    assert result.camarilla_distances == ()
    assert result.cpr_region is CPRRegion.UNKNOWN
    assert result.vwap_location is PriceLocation.UNKNOWN
    assert result.latest_price_status.availability is EvidenceAvailability.MISSING


def test_moving_average_observations_preserve_values_and_do_not_calculate_periods():
    ma = MovingAverageObservation("EMA", 20, 99.0, PriceLocation.UNKNOWN, 0.5, EvidenceAvailability.AVAILABLE)
    result = map_request(moving_averages=(ma,))
    assert result.moving_average_status.availability is EvidenceAvailability.AVAILABLE
    assert result.moving_average_observations[0].name == "EMA"
    assert result.moving_average_observations[0].period == 20
    assert result.moving_average_observations[0].value == 99.0
    assert result.moving_average_observations[0].slope == 0.5
    assert result.moving_average_observations[0].price_location is PriceLocation.ABOVE


def test_idempotency_duplicate_no_republish_and_changed_duplicate_rejected():
    bus = EventBus()
    events_seen = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_MAPPED, lambda payload: events_seen.append(payload))
    item = engine(bus)
    req = request()
    first = item.map_evidence(req)
    second = item.map_evidence(req)
    assert first is second
    assert item.snapshot().mapping_count == 1
    assert events_seen == [first]
    with pytest.raises(ValueError, match="different request"):
        item.map_evidence(request(latest_price=101.0))
    assert item.snapshot().mapping_count == 1
    assert item.get_evidence("evidence-1") is first


def test_events_publish_one_business_result_and_state_failed_event_only_for_unexpected_errors(monkeypatch):
    bus = EventBus()
    seen = []
    for name in (
        TRADINGVIEW_EVIDENCE_MAPPED,
        TRADINGVIEW_EVIDENCE_PARTIAL,
        TRADINGVIEW_EVIDENCE_INVALID,
        TRADINGVIEW_EVIDENCE_STATE_UPDATED,
        TRADINGVIEW_EVIDENCE_FAILED,
    ):
        bus.subscribe(name, lambda payload, name=name: seen.append(name))
    item = engine(bus)
    seen.clear()
    item.map_evidence(request(evidence_id="complete"))
    item.map_evidence(request(evidence_id="partial", latest_candle=None))
    item.map_evidence(request(evidence_id="invalid", vwap=object()))
    assert seen.count(TRADINGVIEW_EVIDENCE_MAPPED) == 1
    assert seen.count(TRADINGVIEW_EVIDENCE_PARTIAL) == 1
    assert seen.count(TRADINGVIEW_EVIDENCE_INVALID) == 1
    assert seen.count(TRADINGVIEW_EVIDENCE_FAILED) == 0


def test_symbol_runtime_and_orchestrator_facades_reuse_instrument_timeframe_eventbus_and_snapshot():
    bus = EventBus()
    orchestrator = ApplicationOrchestrator(bus, RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY)))
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    assert runtime.tradingview_evidence_engine._event_bus is bus
    assert orchestrator.start().status.value == "running"
    req = request()
    result = orchestrator.map_tradingview_evidence(RuntimeInstrument.NIFTY, req)
    assert result.instrument is RuntimeInstrument.NIFTY
    assert orchestrator.get_tradingview_evidence(RuntimeInstrument.NIFTY, "evidence-1") is result
    assert orchestrator.get_tradingview_evidence_snapshot(RuntimeInstrument.NIFTY).mapping_count == 1
    assert orchestrator.snapshot().runtime_snapshots[0].tradingview_evidence.mapping_count == 1
    with pytest.raises(ValueError, match="instrument"):
        orchestrator.map_tradingview_evidence(RuntimeInstrument.BANKNIFTY, req)
    assert orchestrator.reset_tradingview_evidence(RuntimeInstrument.NIFTY).mapping_count == 0
    assert orchestrator.stop().status.value == "stopped"


def test_tick_and_candle_processing_do_not_automatically_invoke_evidence_mapping():
    bus = EventBus()
    orchestrator = ApplicationOrchestrator(bus, RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,)))
    orchestrator.start()
    tick = Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=NOW,
        last_price=100.0,
        volume=1,
        bid_price=99.5,
        ask_price=100.5,
        open_interest=0,
    )
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    orchestrator.warm_up_candles(RuntimeInstrument.NIFTY, (candle(end_time=NOW - timedelta(minutes=1)),))
    assert runtime.tradingview_evidence_snapshot().mapping_count == 0
    orchestrator.process_tick(tick)
    assert runtime.tradingview_evidence_snapshot().mapping_count == 0


def test_intelligence_boundary_and_safety_search_terms_are_absent_from_engine_source():
    source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in __import__("pathlib").Path("engines/tradingview_evidence").glob("*.py")
    )
    for forbidden in ("place_order", "modify_order", "cancel_order", "execute_paper", "datetime.now", "datetime.utcnow", "time.time", "threading", "asyncio", "sleep", "qtimer", "requests", "httpx", "eventbus("):
        assert forbidden not in source
    result = map_request()
    assert result.strategy_calls == 0
    assert result.risk_calls == 0
    assert result.execution_policy_calls == 0
    assert result.authorization_calls == 0
    assert result.paper_execution_calls == 0
    assert result.broker_order_calls == 0
    assert result.trade_decision_generated is False
    assert result.live_order_submission_enabled is False
