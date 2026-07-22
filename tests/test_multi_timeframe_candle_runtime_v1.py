from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.event_bus import EventBus
from core.events import NEW_TICK, TRADINGVIEW_EVIDENCE_MAPPED
from core.models.building_candle import BuildingCandle
from core.models.candle import Candle
from core.models.tick import Tick
from engines.candle.candle_engine import CandleEngine
from engines.tradingview_evidence import TradingViewEvidenceRequest
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


def tick(timestamp: datetime, price: float = 100.0, volume: int = 10) -> Tick:
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=volume,
        bid_price=price - 0.5,
        ask_price=price + 0.5,
        open_interest=100,
    )


@pytest.mark.parametrize(
    ("timeframe", "timestamp", "expected_start", "expected_end"),
    (
        (TimeFrame.ONE_MINUTE, datetime(2026, 7, 21, 9, 17, 42), datetime(2026, 7, 21, 9, 17), datetime(2026, 7, 21, 9, 18)),
        (TimeFrame.THREE_MINUTES, datetime(2026, 7, 21, 9, 17, 42), datetime(2026, 7, 21, 9, 15), datetime(2026, 7, 21, 9, 18)),
        (TimeFrame.FIVE_MINUTES, datetime(2026, 7, 21, 9, 17, 42), datetime(2026, 7, 21, 9, 15), datetime(2026, 7, 21, 9, 20)),
        (TimeFrame.FIFTEEN_MINUTES, datetime(2026, 7, 21, 9, 17, 42), datetime(2026, 7, 21, 9, 15), datetime(2026, 7, 21, 9, 30)),
        (TimeFrame.THIRTY_MINUTES, datetime(2026, 7, 21, 9, 17, 42), datetime(2026, 7, 21, 9, 15), datetime(2026, 7, 21, 9, 45)),
    ),
)
def test_building_candle_uses_timeframe_duration_for_boundaries(timeframe, timestamp, expected_start, expected_end):
    item = BuildingCandle.from_tick(tick(timestamp), timeframe=timeframe)

    assert item.timeframe is timeframe
    assert item.start_time == expected_start
    assert item.end_time == expected_end


@pytest.mark.parametrize(
    ("timeframe", "closing_timestamp", "expected_start", "expected_end"),
    (
        (TimeFrame.ONE_MINUTE, datetime(2026, 7, 21, 9, 18), datetime(2026, 7, 21, 9, 17), datetime(2026, 7, 21, 9, 18)),
        (TimeFrame.THREE_MINUTES, datetime(2026, 7, 21, 9, 18), datetime(2026, 7, 21, 9, 15), datetime(2026, 7, 21, 9, 18)),
        (TimeFrame.FIVE_MINUTES, datetime(2026, 7, 21, 9, 20), datetime(2026, 7, 21, 9, 15), datetime(2026, 7, 21, 9, 20)),
        (TimeFrame.FIFTEEN_MINUTES, datetime(2026, 7, 21, 9, 30), datetime(2026, 7, 21, 9, 15), datetime(2026, 7, 21, 9, 30)),
        (TimeFrame.THIRTY_MINUTES, datetime(2026, 7, 21, 9, 45), datetime(2026, 7, 21, 9, 15), datetime(2026, 7, 21, 9, 45)),
    ),
)
def test_candle_engine_aggregates_supported_runtime_timeframes(timeframe, closing_timestamp, expected_start, expected_end):
    engine = CandleEngine(EventBus(), timeframe)
    engine.on_tick(tick(datetime(2026, 7, 21, 9, 17, 42), price=100.0, volume=7))
    current = engine.on_tick(tick(closing_timestamp, price=102.0, volume=3))
    history = engine.get_history(Instrument.NIFTY)

    assert len(history) == 1
    assert history[0].timeframe == timeframe.value
    assert history[0].start_time == expected_start
    assert history[0].end_time == expected_end
    assert history[0].open == 100.0
    assert history[0].close == 100.0
    assert history[0].volume == 7
    assert current.start_time == expected_end


def test_thirty_minute_boundaries_are_session_anchored_not_midnight_anchored():
    first = BuildingCandle.from_tick(
        tick(datetime(2026, 7, 21, 9, 17, 0)),
        timeframe=TimeFrame.THIRTY_MINUTES,
    )
    second = BuildingCandle.from_tick(
        tick(datetime(2026, 7, 21, 9, 45, 0)),
        timeframe=TimeFrame.THIRTY_MINUTES,
    )
    third = BuildingCandle.from_tick(
        tick(datetime(2026, 7, 21, 10, 15, 0)),
        timeframe=TimeFrame.THIRTY_MINUTES,
    )

    assert (first.start_time, first.end_time) == (
        datetime(2026, 7, 21, 9, 15),
        datetime(2026, 7, 21, 9, 45),
    )
    assert (second.start_time, second.end_time) == (
        datetime(2026, 7, 21, 9, 45),
        datetime(2026, 7, 21, 10, 15),
    )
    assert (third.start_time, third.end_time) == (
        datetime(2026, 7, 21, 10, 15),
        datetime(2026, 7, 21, 10, 45),
    )


def test_session_open_exact_boundary_starts_first_candle_at_session_open():
    item = BuildingCandle.from_tick(
        tick(datetime(2026, 7, 21, 9, 15, 0)),
        timeframe=TimeFrame.FIFTEEN_MINUTES,
    )

    assert item.start_time == datetime(2026, 7, 21, 9, 15)
    assert item.end_time == datetime(2026, 7, 21, 9, 30)


def test_session_close_partial_candle_boundary_is_deterministic():
    item = BuildingCandle.from_tick(
        tick(datetime(2026, 7, 21, 15, 29, 59)),
        timeframe=TimeFrame.THIRTY_MINUTES,
    )

    assert item.start_time == datetime(2026, 7, 21, 15, 15)
    assert item.end_time == datetime(2026, 7, 21, 15, 45)


def test_exact_boundary_timestamp_opens_the_next_candle():
    engine = CandleEngine(EventBus(), TimeFrame.FIVE_MINUTES)

    engine.on_tick(tick(datetime(2026, 7, 21, 9, 15), price=100.0))
    current = engine.on_tick(tick(datetime(2026, 7, 21, 9, 20), price=101.0))

    history = engine.get_history(Instrument.NIFTY)
    assert len(history) == 1
    assert history[0].start_time == datetime(2026, 7, 21, 9, 15)
    assert history[0].end_time == datetime(2026, 7, 21, 9, 20)
    assert current.start_time == datetime(2026, 7, 21, 9, 20)
    assert current.end_time == datetime(2026, 7, 21, 9, 25)


def test_runtime_configuration_supports_legacy_timeframe_and_multi_timeframes():
    legacy = RuntimeConfiguration(timeframe="1m")
    multi = RuntimeConfiguration(timeframes=("1m", "5m", "15m"))

    assert legacy.timeframe == "1m"
    assert legacy.timeframes == ("1m",)
    assert multi.timeframe == "1m"
    assert multi.timeframes == ("1m", "5m", "15m")


def test_symbol_runtime_creates_independent_candle_and_analysis_lanes():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m", "15m")),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    assert tuple(runtime.candle_engines) == (
        TimeFrame.ONE_MINUTE,
        TimeFrame.FIVE_MINUTES,
        TimeFrame.FIFTEEN_MINUTES,
    )
    assert len(runtime.candle_engines) == 3
    assert runtime.candle_engine is runtime.candle_engines[TimeFrame.ONE_MINUTE]
    assert runtime.price_action_engine is runtime.price_action_engines[TimeFrame.ONE_MINUTE]
    assert runtime.market_context_engine is runtime.market_context_engines[TimeFrame.ONE_MINUTE]
    assert runtime.tradingview_evidence_engine is runtime.tradingview_evidence_engines[TimeFrame.ONE_MINUTE]


def test_one_accepted_tick_fans_out_to_all_candle_lanes_with_one_market_data_engine():
    bus = EventBus()
    accepted = []
    bus.subscribe(NEW_TICK, accepted.append)
    orchestrator = ApplicationOrchestrator(
        bus,
        RuntimeConfiguration(timeframes=("1m", "3m", "5m", "15m", "30m")),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 17, 42), price=101.0))

    assert len(accepted) == 1
    assert len(orchestrator.market_data_engine.get_all_latest()) == 1
    assert len(runtime.candle_engines) == 5
    assert runtime.vwap_engine is runtime.vwap_engine
    assert runtime.cpr_engine is runtime.cpr_engine
    assert runtime.camarilla_engine is runtime.camarilla_engine
    assert runtime.option_chain_engine is runtime.option_chain_engine
    assert all(engine.get_current(Instrument.NIFTY) is not None for engine in runtime.candle_engines.values())


def test_one_minute_price_action_does_not_mutate_five_minute_price_action_until_five_minute_close():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m")),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 15, 10), price=100.0))
    orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 16, 0), price=101.0))

    assert runtime.price_action_engines[TimeFrame.ONE_MINUTE].state is not None
    assert runtime.price_action_engines[TimeFrame.FIVE_MINUTES].state is None
    assert len(runtime.get_candle_history(TimeFrame.ONE_MINUTE)) == 1
    assert len(runtime.get_candle_history(TimeFrame.FIVE_MINUTES)) == 0


def test_closed_candle_triggers_primary_analysis_exactly_once():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframe="1m"),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    calls = {"context": 0, "evidence": 0, "ai": 0, "strategy": 0}
    original_context = runtime.build_market_context
    original_evidence = runtime._assemble_tradingview_evidence
    original_ai = runtime.run_ai_reasoning
    original_strategy = runtime.run_strategy

    def build_context_wrapper(*args, **kwargs):
        calls["context"] += 1
        return original_context(*args, **kwargs)

    def evidence_wrapper(*args, **kwargs):
        calls["evidence"] += 1
        return original_evidence(*args, **kwargs)

    def ai_wrapper(*args, **kwargs):
        calls["ai"] += 1
        return original_ai(*args, **kwargs)

    def strategy_wrapper(*args, **kwargs):
        calls["strategy"] += 1
        return original_strategy(*args, **kwargs)

    runtime.build_market_context = build_context_wrapper
    runtime._assemble_tradingview_evidence = evidence_wrapper
    runtime.run_ai_reasoning = ai_wrapper
    runtime.run_strategy = strategy_wrapper

    orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 15, 10), price=100.0))
    assert calls == {"context": 0, "evidence": 0, "ai": 0, "strategy": 0}

    orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 16, 0), price=101.0))
    assert calls == {"context": 1, "evidence": 1, "ai": 1, "strategy": 1}

    orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 16, 30), price=102.0))
    assert calls == {"context": 1, "evidence": 1, "ai": 1, "strategy": 1}


def test_one_hundred_ticks_inside_one_candle_do_not_recompute_analysis():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframe="5m"),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    calls = {"context": 0, "evidence": 0, "ai": 0, "strategy": 0}
    original_context = runtime.build_market_context
    original_evidence = runtime._assemble_tradingview_evidence
    original_ai = runtime.run_ai_reasoning
    original_strategy = runtime.run_strategy

    def build_context_wrapper(*args, **kwargs):
        calls["context"] += 1
        return original_context(*args, **kwargs)

    def evidence_wrapper(*args, **kwargs):
        calls["evidence"] += 1
        return original_evidence(*args, **kwargs)

    def ai_wrapper(*args, **kwargs):
        calls["ai"] += 1
        return original_ai(*args, **kwargs)

    def strategy_wrapper(*args, **kwargs):
        calls["strategy"] += 1
        return original_strategy(*args, **kwargs)

    runtime.build_market_context = build_context_wrapper
    runtime._assemble_tradingview_evidence = evidence_wrapper
    runtime.run_ai_reasoning = ai_wrapper
    runtime.run_strategy = strategy_wrapper

    for offset in range(100):
        orchestrator.process_tick(
            tick(
                datetime(2026, 7, 21, 9, 15, 0) + timedelta(seconds=offset),
                price=100.0 + (offset / 1000),
            )
        )

    assert calls == {"context": 0, "evidence": 0, "ai": 0, "strategy": 0}
    assert runtime.market_context_engine.state is None
    assert runtime.ai_reasoning_engine.state is None
    assert runtime.strategy_engine.state is None


def test_each_timeframe_can_publish_its_own_tradingview_evidence_snapshot():
    bus = EventBus()
    mapped = []
    bus.subscribe(TRADINGVIEW_EVIDENCE_MAPPED, mapped.append)
    orchestrator = ApplicationOrchestrator(
        bus,
        RuntimeConfiguration(timeframes=("1m", "5m")),
    )
    orchestrator.start()
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)

    for timeframe in ("1m", "5m"):
        request = evidence_request(timeframe)
        result = runtime.map_tradingview_evidence(request)
        assert result.timeframe == timeframe
        assert runtime.tradingview_evidence_snapshot(timeframe).last_evidence is result

    assert [event.timeframe for event in mapped] == ["1m", "5m"]
    assert runtime.tradingview_evidence_snapshot("1m").last_evidence.timeframe == "1m"
    assert runtime.tradingview_evidence_snapshot("5m").last_evidence.timeframe == "5m"


def test_runtime_closed_candle_routing_filters_by_instrument_and_timeframe():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY),
            timeframes=("1m", "5m"),
        ),
    )
    orchestrator.start()
    nifty = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    banknifty = orchestrator.get_runtime(RuntimeInstrument.BANKNIFTY)

    orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 15, 10), price=100.0))
    orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 16, 0), price=101.0))

    assert nifty.price_action_engines[TimeFrame.ONE_MINUTE].state is not None
    assert nifty.price_action_engines[TimeFrame.FIVE_MINUTES].state is None
    assert banknifty.price_action_engines[TimeFrame.ONE_MINUTE].state is None
    assert banknifty.price_action_engines[TimeFrame.FIVE_MINUTES].state is None


def test_multi_timeframe_runtime_keeps_primary_snapshot_backward_compatible():
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m", "15m")),
    )
    orchestrator.start()

    live_snapshot = orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 15, 10), price=101.0))

    assert live_snapshot.timeframe == "1m"
    assert live_snapshot.latest_candle.timeframe is TimeFrame.ONE_MINUTE
    assert live_snapshot.market_context is None

    closed_snapshot = orchestrator.process_tick(tick(datetime(2026, 7, 21, 9, 16), price=102.0))
    assert closed_snapshot.market_context is not None
    assert closed_snapshot.market_context.timeframe == "1m"


def evidence_request(timeframe: str) -> TradingViewEvidenceRequest:
    end_time = NOW
    source_candle = candle(end_time=end_time)
    if timeframe != "1m":
        minutes = TimeFrame.from_value(timeframe).minutes
        source_candle = Candle(
            symbol=source_candle.symbol,
            timeframe=timeframe,
            start_time=end_time - timedelta(minutes=minutes),
            end_time=end_time,
            open=source_candle.open,
            high=source_candle.high,
            low=source_candle.low,
            close=source_candle.close,
            volume=source_candle.volume,
        )
    pa = replace(price_action(), timeframe=timeframe, last_candle=source_candle)
    context = replace(market_context(), timeframe=timeframe, price_action_direction=market_context().price_action_direction)
    return TradingViewEvidenceRequest(
        evidence_id=f"evidence-{timeframe}",
        timestamp=NOW,
        instrument=RuntimeInstrument.NIFTY,
        timeframe=timeframe,
        latest_price=100.0,
        latest_candle=source_candle,
        camarilla=camarilla(),
        cpr=cpr(),
        vwap=vwap(),
        adr=None,
        price_action=pa,
        market_context=context,
        option_chain=option_chain(),
    )
