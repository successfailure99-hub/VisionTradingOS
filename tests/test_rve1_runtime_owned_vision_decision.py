from dataclasses import replace
from datetime import datetime, timedelta

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
    item.process_tick(tick(START + timedelta(minutes=25), price=105.0))

    assert calls == [START + timedelta(minutes=25)]
    assert item.snapshot().vision_trade_candidate.timestamp == START + timedelta(minutes=25)

