from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from application.tradingview_evidence_assembly import (
    TradingViewEvidenceAssemblyCoordinator,
    TradingViewEvidenceAssemblyInput,
    TradingViewEvidenceAssemblySnapshot,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import TRADINGVIEW_EVIDENCE_MAPPED, TRADINGVIEW_EVIDENCE_PARTIAL
from core.models.tick import Tick
from engines.tradingview_evidence import EvidenceAvailability, TradingViewEvidenceMappingEngine
from tests.test_tradingview_evidence_mapping_engine_v1 import (
    NOW,
    camarilla,
    candle,
    cpr,
    market_context,
    option_chain,
    price_action,
    vwap,
)


def mapping_engine(bus: EventBus) -> TradingViewEvidenceMappingEngine:
    item = TradingViewEvidenceMappingEngine(bus, instrument="NIFTY", timeframe="1m")
    item.start()
    return item


def coordinator(bus: EventBus | None = None) -> TradingViewEvidenceAssemblyCoordinator:
    bus = bus or EventBus()
    return TradingViewEvidenceAssemblyCoordinator(
        instrument=RuntimeInstrument.NIFTY,
        timeframe="1m",
        mapping_engine=mapping_engine(bus),
    )


def source(**overrides) -> TradingViewEvidenceAssemblyInput:
    data = {
        "timestamp": NOW,
        "instrument": RuntimeInstrument.NIFTY,
        "timeframe": "1m",
        "latest_price": 100.0,
        "latest_candle": candle(),
        "price_action": price_action(),
        "camarilla": camarilla(),
        "cpr": cpr(),
        "vwap": vwap(),
        "option_chain": option_chain(),
        "market_context": market_context(),
        "correlation_id": "assembly-1",
    }
    data.update(overrides)
    return TradingViewEvidenceAssemblyInput(**data)


def live_tick(timestamp=NOW, price=100.0) -> Tick:
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=100,
        bid_price=price - 0.5,
        ask_price=price + 0.5,
        open_interest=0,
    )


def test_happy_path_all_engines_publish_one_tradingview_evidence_snapshot():
    bus = EventBus()
    mapped = []
    partial = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_MAPPED, lambda payload: mapped.append(payload))
    bus.subscribe(TRADINGVIEW_EVIDENCE_PARTIAL, lambda payload: partial.append(payload))
    item = coordinator(bus)

    result = item.assemble(source())

    assert result is mapped[0]
    assert partial == []
    assert result.latest_candle == candle()
    assert result.price_action_observation == price_action()
    assert result.camarilla_status.availability is EvidenceAvailability.AVAILABLE
    assert result.cpr_status.availability is EvidenceAvailability.AVAILABLE
    assert result.vwap_status.availability is EvidenceAvailability.AVAILABLE
    assert result.option_chain_observation == option_chain()
    assert result.market_context_observation == market_context()
    assert item.snapshot().assembled_count == 1


@pytest.mark.parametrize(
    ("field_name", "status_name"),
    (
        ("price_action", "price_action_status"),
        ("cpr", "cpr_status"),
        ("vwap", "vwap_status"),
        ("option_chain", "option_chain_status"),
        ("market_context", "market_context_status"),
    ),
)
def test_missing_required_upstream_snapshot_publishes_partial(field_name, status_name):
    bus = EventBus()
    mapped = []
    partial = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_MAPPED, lambda payload: mapped.append(payload))
    bus.subscribe(TRADINGVIEW_EVIDENCE_PARTIAL, lambda payload: partial.append(payload))
    item = coordinator(bus)

    result = item.assemble(source(**{field_name: None}))

    assert mapped == []
    assert result is partial[0]
    assert getattr(result, status_name).availability is EvidenceAvailability.MISSING
    assert field_name in result.missing_evidence
    assert item.snapshot().assembled_count == 1


def test_stale_required_timestamp_publishes_partial():
    bus = EventBus()
    partial = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_PARTIAL, lambda payload: partial.append(payload))
    item = coordinator(bus)

    result = item.assemble(source(option_chain=option_chain_with_timestamp(NOW - timedelta(seconds=301))))

    assert result is partial[0]
    assert result.option_chain_status.availability is EvidenceAvailability.STALE
    assert result.option_chain_status.age_seconds == pytest.approx(301.0)
    assert "option_chain" in result.stale_evidence


def test_future_upstream_timestamp_is_rejected_by_request_validation_not_normalized():
    bus = EventBus()
    mapped = []
    partial = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_MAPPED, lambda payload: mapped.append(payload))
    bus.subscribe(TRADINGVIEW_EVIDENCE_PARTIAL, lambda payload: partial.append(payload))
    item = coordinator(bus)

    with pytest.raises(ValueError, match="source timestamp"):
        item.assemble(source(option_chain=option_chain_with_timestamp(NOW + timedelta(seconds=5))))

    snapshot = item.snapshot()
    assert mapped == []
    assert partial == []
    assert snapshot.assembled_count == 0
    assert snapshot.last_evidence is None


def test_event_ordering_waits_for_price_and_closed_candle_before_publishing():
    bus = EventBus()
    events = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_MAPPED, lambda payload: events.append(payload))
    bus.subscribe(TRADINGVIEW_EVIDENCE_PARTIAL, lambda payload: events.append(payload))
    item = coordinator(bus)

    assert item.assemble(source(latest_price=None)) is None
    assert item.assemble(source(latest_candle=None)) is None

    snapshot = item.snapshot()
    assert events == []
    assert snapshot.assembled_count == 0
    assert snapshot.skipped_count == 2
    assert snapshot.last_wait_reason == "latest closed candle is unavailable"


def test_duplicate_events_publish_only_one_snapshot_per_update_cycle():
    bus = EventBus()
    events = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_MAPPED, lambda payload: events.append(payload))
    item = coordinator(bus)
    request = source()

    first = item.assemble(request)
    second = item.assemble(request)

    assert first is second
    assert events == [first]
    assert item.snapshot().assembled_count == 1
    assert item.snapshot().duplicate_count == 1


def test_repeated_identical_inputs_are_deterministic_and_models_are_immutable():
    item = coordinator()
    request = source()

    first = item.assemble(request)
    second = item.assemble(request)
    snapshot = item.snapshot()

    assert first == second
    assert first.source_fingerprint == second.source_fingerprint
    assert isinstance(snapshot, TradingViewEvidenceAssemblySnapshot)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        snapshot.extra = "blocked"


def test_symbol_runtime_integrates_assembly_automatically_after_closed_candle_update():
    bus = EventBus()
    partial = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_PARTIAL, lambda payload: partial.append(payload))
    orchestrator = ApplicationOrchestrator(
        bus,
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,)),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    orchestrator.warm_up_candles(RuntimeInstrument.NIFTY, (candle(end_time=NOW - timedelta(minutes=1)),))

    orchestrator.process_tick(live_tick())
    orchestrator.process_tick(live_tick(timestamp=NOW + timedelta(minutes=1), price=101.0))

    evidence = runtime.tradingview_evidence_snapshot()
    assert evidence.mapping_count == 1
    assert evidence.partial_mapping_count == 1
    assert partial == [evidence.last_evidence]
    assert evidence.last_evidence.price_action_status.availability is EvidenceAvailability.AVAILABLE
    assert evidence.last_evidence.option_chain_status.availability is EvidenceAvailability.MISSING


def test_runtime_bare_tick_without_closed_candle_does_not_publish_evidence():
    bus = EventBus()
    events = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_PARTIAL, lambda payload: events.append(payload))
    orchestrator = ApplicationOrchestrator(
        bus,
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,)),
    )
    orchestrator.start()

    orchestrator.process_tick(live_tick())

    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    assert events == []
    assert runtime.tradingview_evidence_snapshot().mapping_count == 0
    assert runtime.tradingview_evidence_assembly_coordinator.snapshot().last_wait_reason is None


def option_chain_with_timestamp(timestamp):
    state = option_chain()
    return type(state)(
        symbol=state.symbol,
        exchange=state.exchange,
        expiry_date=state.expiry_date,
        timestamp=timestamp,
        underlying_price=state.underlying_price,
        atm_strike=state.atm_strike,
        strike_count=state.strike_count,
        total_call_oi=state.total_call_oi,
        total_put_oi=state.total_put_oi,
        total_call_change_oi=state.total_call_change_oi,
        total_put_change_oi=state.total_put_change_oi,
        oi_pcr=state.oi_pcr,
        change_oi_pcr=state.change_oi_pcr,
        max_call_oi=state.max_call_oi,
        max_put_oi=state.max_put_oi,
        max_call_change_oi=state.max_call_change_oi,
        max_put_change_oi=state.max_put_change_oi,
        resistance_strike=state.resistance_strike,
        support_strike=state.support_strike,
        max_pain_strike=state.max_pain_strike,
        call_pressure=state.call_pressure,
        put_pressure=state.put_pressure,
        positioning_bias=state.positioning_bias,
        strikes=state.strikes,
    )
