from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from application import symbol_runtime as symbol_runtime_module
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.event_bus import EventBus
from core.models.candle import Candle
from core.models.tick import Tick
from engines.vision_method import VisionCandidateState, calculate_vision_method_snapshot, validate_vision_method
from engines.vision_method.runtime_evaluator import VisionMethodRuntimeAssembly
from tests.test_vision_method_calculator_v1 import IST, request


START = datetime(2026, 7, 29, 10, 25, tzinfo=IST)


def tick(timestamp: datetime, *, price: float = 100.0, volume: int = 10) -> Tick:
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=volume,
        bid_price=price - 0.5,
        ask_price=price + 0.5,
        open_interest=0,
    )


def candle(offset: int, *, price: float = 100.0) -> Candle:
    start = START + timedelta(minutes=offset)
    return Candle(
        symbol="NIFTY",
        timeframe="1m",
        start_time=start,
        end_time=start + timedelta(minutes=1),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=10,
    )


def runtime() -> SymbolRuntime:
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m", "15m")),
        RuntimeInstrument.NIFTY,
    )
    item.start()
    return item


def method_at(timestamp: datetime, *, state: VisionCandidateState = VisionCandidateState.OBSERVE):
    snapshot = calculate_vision_method_snapshot(
        request(
            timestamp=timestamp,
            price_action_trigger_context=None,
        )
    )
    snapshot = replace(snapshot, timestamp=timestamp, candidate_state=state, quality="low")
    report = validate_vision_method(snapshot)
    return snapshot, report


def install_fake_evaluator(monkeypatch, calls):
    def fake_evaluator(runtime_item, *, runtime_snapshot=None, timestamp=None, **_kwargs):
        snapshot, report = method_at(timestamp)
        calls.append(timestamp)
        return VisionMethodRuntimeAssembly(
            runtime_snapshot=runtime_snapshot or runtime_item.snapshot(),
            timeframe=TimeFrame.FIVE_MINUTES,
            timestamp=timestamp,
            trading_date=timestamp.date(),
            snapshot=snapshot,
            report=report,
            failures=(),
        )

    monkeypatch.setattr(symbol_runtime_module, "assemble_vision_method_runtime", fake_evaluator)


def close_first_five_minute_candle(item: SymbolRuntime) -> None:
    item.process_tick(tick(START, price=100.0))
    item.process_tick(tick(START + timedelta(minutes=5), price=101.0))


def test_runtime_owned_closed_5m_candle_creates_canonical_trade_candidate_without_dashboard(monkeypatch):
    calls = []
    install_fake_evaluator(monkeypatch, calls)
    item = runtime()

    close_first_five_minute_candle(item)
    snapshot = item.snapshot()

    assert calls == [START + timedelta(minutes=5)]
    assert snapshot.vision_method_snapshot is not None
    assert snapshot.vision_method_validation_report is not None
    assert snapshot.vision_trade_candidate is not None
    assert snapshot.vision_trade_candidate.timeframe is TimeFrame.FIVE_MINUTES


def test_snapshot_and_same_bucket_ticks_do_not_reevaluate_old_5m_candle(monkeypatch):
    calls = []
    install_fake_evaluator(monkeypatch, calls)
    item = runtime()

    close_first_five_minute_candle(item)
    item.snapshot()
    item.snapshot()
    item.process_tick(tick(START + timedelta(minutes=5, seconds=30), price=102.0))

    assert calls == [START + timedelta(minutes=5)]


def test_consecutive_closed_5m_candles_have_distinct_runtime_decisions(monkeypatch):
    calls = []
    install_fake_evaluator(monkeypatch, calls)
    item = runtime()

    close_first_five_minute_candle(item)
    first = item.snapshot().vision_trade_candidate
    item.process_tick(tick(START + timedelta(minutes=10), price=102.0))
    second_snapshot = item.snapshot()

    assert calls == [START + timedelta(minutes=5), START + timedelta(minutes=10)]
    assert second_snapshot.vision_trade_candidate is not None
    assert first.snapshot_reference != second_snapshot.vision_trade_candidate.snapshot_reference
    assert second_snapshot.vision_trade_candidate.timestamp == START + timedelta(minutes=10)


def test_historical_warmup_does_not_replay_vision_decisions(monkeypatch):
    calls = []
    install_fake_evaluator(monkeypatch, calls)
    item = runtime()
    historical = tuple(candle(index, price=100.0 + index) for index in range(5))

    item.warm_up_candles(historical)

    assert calls == []
    assert item.snapshot().vision_trade_candidate is None


def test_runtime_snapshot_is_read_only_for_vision_extension_builders(monkeypatch):
    item = runtime()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("RuntimeSnapshot must not build Vision extension contexts")

    monkeypatch.setattr(item, "_current_pivot_flight_plan", forbidden)
    monkeypatch.setattr(item, "_current_pivot_opening_assessment", forbidden)
    monkeypatch.setattr(item, "_current_pivot_confluence_context", forbidden)
    monkeypatch.setattr(item, "_current_price_action_trigger_context", forbidden)

    view = item.snapshot()

    assert view.pivot_flight_plan is None
    assert view.pivot_opening_assessment is None
    assert view.pivot_confluence_context is None
    assert view.price_action_trigger_context is None


def test_supporting_engine_failures_are_visible_without_blocking_candles(monkeypatch):
    item = runtime()

    def fail_supporting_engine(_candle):
        raise ValueError("moving average source unavailable")

    monkeypatch.setattr(item.moving_average_context_engines[TimeFrame.ONE_MINUTE], "process", fail_supporting_engine)

    item.process_tick(tick(START, price=100.0))
    item.process_tick(tick(START + timedelta(minutes=1), price=101.0))

    view = item.snapshot()

    assert view.latest_closed_candle_at == START + timedelta(minutes=1)
    assert any(
        item == "DEGRADED Moving Average Context 1m: moving average source unavailable"
        for item in view.runtime_diagnostics.supporting_engine_status
    )
    diagnostic = next(
        item
        for item in view.runtime_diagnostics.supporting_engine_diagnostics
        if item.component == "Moving Average Context" and item.timeframe is TimeFrame.ONE_MINUTE
    )
    assert diagnostic.status == "DEGRADED"
    assert diagnostic.occurrence_count == 1
    assert diagnostic.blocking is False


def test_warmup_supporting_engine_failures_are_visible(monkeypatch):
    item = runtime()

    def fail_supporting_engine(_candle):
        raise RuntimeError("warmup moving average unavailable")

    monkeypatch.setattr(item.moving_average_context_engine, "process", fail_supporting_engine)

    item.warm_up_candles((candle(0),))

    view = item.snapshot()

    assert any(
        status == "DEGRADED Moving Average Context 1m: warmup moving average unavailable"
        for status in view.runtime_diagnostics.supporting_engine_status
    )


def test_market_context_failure_is_visible_without_blocking_closed_candle(monkeypatch):
    item = runtime()

    def fail_market_context(**_kwargs):
        raise ValueError("market context source unavailable")

    monkeypatch.setattr(item, "build_market_context", fail_market_context)

    item.process_tick(tick(START, price=100.0))
    item.process_tick(tick(START + timedelta(minutes=1), price=101.0))

    view = item.snapshot()

    assert view.latest_closed_candle_at == START + timedelta(minutes=1)
    assert any(
        status == "DEGRADED Market Context 1m: market context source unavailable"
        for status in view.runtime_diagnostics.supporting_engine_status
    )


def test_tradingview_evidence_failure_is_visible_without_blocking_closed_candle(monkeypatch):
    item = runtime()

    def fail_tradingview_evidence(*_args, **_kwargs):
        raise ValueError("tradingview evidence unavailable")

    monkeypatch.setattr(item, "_assemble_tradingview_evidence", fail_tradingview_evidence)

    item.process_tick(tick(START, price=100.0))
    item.process_tick(tick(START + timedelta(minutes=1), price=101.0))

    view = item.snapshot()

    assert view.latest_closed_candle_at == START + timedelta(minutes=1)
    assert any(
        status == "DEGRADED TradingView Evidence 1m: tradingview evidence unavailable"
        for status in view.runtime_diagnostics.supporting_engine_status
    )


def test_legacy_primary_ai_strategy_failure_is_visible_and_non_blocking(monkeypatch):
    item = runtime()

    def fail_ai(_context):
        raise RuntimeError("legacy ai unavailable")

    monkeypatch.setattr(item, "run_ai_reasoning", fail_ai)

    item._refresh_primary_closed_candle_analysis(SimpleNamespace(updated_at=START))
    view = item.snapshot()

    assert any(
        status == "DEGRADED Legacy AI/Strategy 1m: legacy ai unavailable"
        for status in view.runtime_diagnostics.supporting_engine_status
    )
    assert view.runtime_diagnostics.supporting_engine_diagnostics[0].blocking is False


def test_legacy_primary_ai_strategy_recovery_is_visible(monkeypatch):
    item = runtime()
    monkeypatch.setattr(item, "run_ai_reasoning", lambda _context: (_ for _ in ()).throw(RuntimeError("legacy ai unavailable")))
    item._refresh_primary_closed_candle_analysis(SimpleNamespace(updated_at=START))

    monkeypatch.setattr(item, "run_ai_reasoning", lambda _context: object())
    monkeypatch.setattr(item, "run_strategy", lambda _context, _reasoning: None)
    item._refresh_primary_closed_candle_analysis(SimpleNamespace(updated_at=START + timedelta(minutes=1)))

    diagnostic = next(
        item
        for item in item.snapshot().runtime_diagnostics.supporting_engine_diagnostics
        if item.component == "Legacy AI/Strategy"
    )
    assert diagnostic.status == "RECOVERED"
    assert diagnostic.recovered_at == START + timedelta(minutes=1)


def test_multi_timeframe_runtime_failure_preserves_sanitized_reason(monkeypatch):
    item = runtime()
    fake_evidence = object()
    for timeframe in item.tradingview_evidence_engines:
        item.tradingview_evidence_engines[timeframe] = SimpleNamespace(
            snapshot=lambda fake_evidence=fake_evidence: SimpleNamespace(last_evidence=fake_evidence)
        )

    def fail_fusion(_snapshots, *, timestamp):
        raise ValueError("fusion source unavailable")

    monkeypatch.setattr(item.multi_timeframe_evidence_fusion_engine, "fuse", fail_fusion)

    item._last_tick = tick(START)
    item._fuse_multi_timeframe_evidence(START)
    view = item.snapshot()

    assert any(
        status == "DEGRADED Multi-Timeframe Intelligence 1m: fusion source unavailable"
        for status in view.runtime_diagnostics.supporting_engine_status
    )
    assert view.decision_audit.reason == "AI Reasoning V2 runtime handoff failed: fusion source unavailable"


def test_snapshot_does_not_restore_option_position_from_checkpoint(monkeypatch):
    item = runtime()

    def forbidden_restore():
        raise AssertionError("snapshot must not restore option paper checkpoint")

    monkeypatch.setattr(item, "_restore_option_paper_position_from_checkpoint", forbidden_restore)

    item.snapshot()


def test_repeated_snapshot_does_not_mutate_previous_runtime_timestamp():
    item = runtime()
    item.process_tick(tick(START, price=100.0))
    observed = item._previous_runtime_snapshot_timestamp

    item.snapshot()
    item.snapshot()

    assert item._previous_runtime_snapshot_timestamp == observed


def test_mid_session_warmup_processes_only_next_new_5m_close(monkeypatch):
    calls = []
    install_fake_evaluator(monkeypatch, calls)
    item = runtime()
    item.warm_up_candles(tuple(candle(index, price=100.0 + index) for index in range(5)))

    item.process_tick(tick(START + timedelta(minutes=5), price=105.0))
    item.process_tick(tick(START + timedelta(minutes=10), price=106.0))

    assert calls == [START + timedelta(minutes=10)]
    assert item.snapshot().vision_trade_candidate.timestamp == START + timedelta(minutes=10)


def test_feed_recovery_catchup_candles_do_not_create_fake_decisions(monkeypatch):
    calls = []
    install_fake_evaluator(monkeypatch, calls)
    item = runtime()

    item.process_tick(tick(START, price=100.0))
    item.process_tick(tick(START + timedelta(minutes=20), price=104.0))

    assert calls == [START + timedelta(minutes=20)]
    assert item.snapshot().vision_trade_candidate.timestamp == START + timedelta(minutes=20)
    assert item.snapshot().vision_decision_provenance == "RECOVERY_CONTEXT"

    item.process_tick(tick(START + timedelta(minutes=25), price=105.0))

    assert calls == [START + timedelta(minutes=20), START + timedelta(minutes=25)]
    assert item.snapshot().vision_trade_candidate.timestamp == START + timedelta(minutes=25)
    assert item.snapshot().vision_decision_provenance == "LIVE"

    item.process_tick(tick(START + timedelta(minutes=30), price=106.0))

    assert calls == [
        START + timedelta(minutes=20),
        START + timedelta(minutes=25),
        START + timedelta(minutes=30),
    ]
    assert item.snapshot().vision_trade_candidate.timestamp == START + timedelta(minutes=30)
    assert item.snapshot().vision_decision_provenance == "LIVE"
