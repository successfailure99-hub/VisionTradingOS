from datetime import datetime, timedelta
from types import SimpleNamespace

from application.enums import RuntimeInstrument
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from core.models.tick import Tick
from engines.vwap.levels import VWAPLevels
from engines.vision_method.runtime_evaluator import _fresh_option_inputs, assemble_vision_method_runtime
from tests.test_vision_method_level_context_v1 import NOW, adr, camarilla, cpr, vwap
from tests.test_vision_method_option_confirmation_v1 import analytics, option_chain


def candle(start: datetime, end: datetime, *, close: float = 111.0) -> Candle:
    return Candle(
        symbol="NIFTY",
        timeframe="5m",
        start_time=start,
        end_time=end,
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=100,
    )


def tick(timestamp: datetime, *, price: float) -> Tick:
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=100,
        bid_price=price - 0.1,
        ask_price=price + 0.1,
        open_interest=0,
    )


def runtime_with(snapshot, history, **overrides):
    values = dict(
        vision_decision_timeframe=TimeFrame.FIVE_MINUTES,
        snapshot=lambda: snapshot,
        get_candle_history=lambda _timeframe: tuple(history),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_closed_5m_decision_uses_source_candle_close_not_next_tick_price():
    start = NOW.replace(hour=10, minute=0)
    end = NOW.replace(hour=10, minute=5)
    source = candle(start, end, close=111.0)
    captured = {}
    snapshot = SimpleNamespace(
        symbol=RuntimeInstrument.NIFTY,
        latest_tick=tick(end + timedelta(seconds=1), price=999.0),
        cpr=cpr(),
        camarilla=camarilla(),
        adr=None,
        vwap=None,
        runtime_session=None,
        updated_at=end + timedelta(seconds=1),
        snapshot_created_at=end + timedelta(seconds=1),
        latest_closed_candle_at=end,
    )

    def level_assembler(request, **_kwargs):
        captured["latest_price"] = request.latest_price
        raise ValueError("stop after level request capture")

    assemble_vision_method_runtime(
        runtime_with(snapshot, (source,)),
        runtime_snapshot=snapshot,
        timestamp=end,
        decision_source_candle=source,
        level_assembler=level_assembler,
    )

    assert captured["latest_price"] == 111.0


def test_future_vwap_is_not_passed_into_closed_5m_decision_level_request():
    start = NOW.replace(hour=10, minute=0)
    end = NOW.replace(hour=10, minute=5)
    source = candle(start, end, close=111.0)
    captured = {}
    future_vwap = VWAPLevels(Instrument.NIFTY, end.date(), end + timedelta(seconds=1), 100.0, 100, 10000.0)
    snapshot = SimpleNamespace(
        symbol=RuntimeInstrument.NIFTY,
        latest_tick=tick(end + timedelta(seconds=1), price=999.0),
        cpr=cpr(),
        camarilla=camarilla(),
        adr=None,
        vwap=future_vwap,
        runtime_session=None,
        updated_at=end + timedelta(seconds=1),
        snapshot_created_at=end + timedelta(seconds=1),
        latest_closed_candle_at=end,
    )

    def level_assembler(request, **_kwargs):
        captured["vwap"] = request.vwap
        raise ValueError("stop after level request capture")

    assembly = assemble_vision_method_runtime(
        runtime_with(snapshot, (source,)),
        runtime_snapshot=snapshot,
        timestamp=end,
        decision_source_candle=source,
        level_assembler=level_assembler,
    )

    assert captured["vwap"] is None
    assert any(failure.stage == "VWAP" and "newer" in failure.validation_message for failure in assembly.failures)


def test_asof_vwap_and_adr_are_used_when_current_snapshots_are_newer_than_closed_5m_decision():
    start = NOW.replace(hour=10, minute=0)
    end = NOW.replace(hour=10, minute=5)
    source = candle(start, end, close=111.0)
    captured = {}
    current_vwap = VWAPLevels(Instrument.NIFTY, end.date(), end + timedelta(seconds=1), 101.0, 100, 10100.0)
    asof_vwap = vwap(timestamp=end)
    current_adr = adr()
    object.__setattr__(current_adr, "timestamp", end + timedelta(seconds=1))
    asof_adr = adr()
    object.__setattr__(asof_adr, "timestamp", end)
    snapshot = SimpleNamespace(
        symbol=RuntimeInstrument.NIFTY,
        latest_tick=tick(end + timedelta(seconds=1), price=999.0),
        cpr=cpr(),
        camarilla=camarilla(),
        adr=current_adr,
        vwap=current_vwap,
        runtime_session=None,
        updated_at=end + timedelta(seconds=1),
        snapshot_created_at=end + timedelta(seconds=1),
        latest_closed_candle_at=end,
    )

    def level_assembler(request, **_kwargs):
        captured["vwap"] = request.vwap
        captured["adr"] = request.adr
        raise ValueError("stop after level request capture")

    assembly = assemble_vision_method_runtime(
        runtime_with(
            snapshot,
            (source,),
            _vwap_as_of=lambda _timestamp: asof_vwap,
            _adr_as_of=lambda _timestamp: asof_adr,
        ),
        runtime_snapshot=snapshot,
        timestamp=end,
        decision_source_candle=source,
        level_assembler=level_assembler,
    )

    assert captured["vwap"] is asof_vwap
    assert captured["adr"] is asof_adr
    assert not any(failure.stage in {"VWAP", "ADR"} and "newer" in failure.validation_message for failure in assembly.failures)


def test_same_or_earlier_vwap_remains_available_for_closed_5m_decision():
    start = NOW.replace(hour=10, minute=0)
    end = NOW.replace(hour=10, minute=5)
    source = candle(start, end, close=111.0)
    captured = {}
    current_vwap = vwap(timestamp=end)
    snapshot = SimpleNamespace(
        symbol=RuntimeInstrument.NIFTY,
        latest_tick=tick(end + timedelta(seconds=1), price=999.0),
        cpr=cpr(),
        camarilla=camarilla(),
        adr=None,
        vwap=current_vwap,
        runtime_session=None,
        updated_at=end + timedelta(seconds=1),
        snapshot_created_at=end + timedelta(seconds=1),
        latest_closed_candle_at=end,
    )

    def level_assembler(request, **_kwargs):
        captured["vwap"] = request.vwap
        raise ValueError("stop after level request capture")

    assemble_vision_method_runtime(
        runtime_with(snapshot, (source,)),
        runtime_snapshot=snapshot,
        timestamp=end,
        decision_source_candle=source,
        level_assembler=level_assembler,
    )

    assert captured["vwap"] is current_vwap


def test_pivot_flight_plan_failure_is_visible_in_runtime_assembly_failures():
    start = NOW.replace(hour=10, minute=0)
    end = NOW.replace(hour=10, minute=5)
    source = candle(start, end, close=111.0)
    snapshot = SimpleNamespace(
        symbol=RuntimeInstrument.NIFTY,
        latest_tick=tick(end, price=111.0),
        cpr=cpr(),
        camarilla=camarilla(),
        adr=None,
        vwap=None,
        runtime_session=SimpleNamespace(trading_date=end.date(), previous_completed_trading_date=end.date() - timedelta(days=1)),
        updated_at=end,
        snapshot_created_at=end,
        latest_closed_candle_at=end,
    )

    assembly = assemble_vision_method_runtime(
        runtime_with(
            snapshot,
            (source,),
            _current_pivot_flight_plan=lambda *_args: (_ for _ in ()).throw(ValueError("pivot flight plan invalid")),
        ),
        runtime_snapshot=snapshot,
        timestamp=end,
        decision_source_candle=source,
    )

    assert any(
        failure.stage == "Pivot Flight Plan" and "pivot flight plan invalid" in failure.validation_message
        for failure in assembly.failures
    )


def test_option_confirmation_runtime_freshness_rejects_hours_old_and_future_inputs():
    fresh_chain = option_chain(timestamp=NOW - timedelta(minutes=4, seconds=59))
    fresh_analytics = analytics(fresh_chain)
    failures = []

    chain, chain_analytics = _fresh_option_inputs(fresh_chain, fresh_analytics, NOW, failures)

    assert chain is fresh_chain
    assert chain_analytics is fresh_analytics
    assert failures == []

    stale_chain = option_chain(timestamp=NOW - timedelta(hours=2))
    stale_analytics = analytics(stale_chain)
    failures = []
    chain, chain_analytics = _fresh_option_inputs(stale_chain, stale_analytics, NOW, failures)

    assert chain is None
    assert chain_analytics is None
    assert any("stale" in failure.validation_message for failure in failures)

    future_chain = option_chain(timestamp=NOW + timedelta(seconds=1))
    future_analytics = analytics(future_chain)
    failures = []
    chain, chain_analytics = _fresh_option_inputs(future_chain, future_analytics, NOW, failures)

    assert chain is None
    assert chain_analytics is None
    assert any("newer" in failure.validation_message for failure in failures)
