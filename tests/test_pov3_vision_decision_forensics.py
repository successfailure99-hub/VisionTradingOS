import json
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from application.models import RuntimeDiagnostics, VisionForensicCounters
from application.vision_forensics import VisionForensicTrace
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.event_bus import EventBus
from core.models.candle import Candle
from core.models.tick import Tick
from dashboard.presenters import _runtime_diagnostic_rows
from desktop.vision_method.live_integration import _vision_decision_timeframe
from engines.runtime_adapter import TradeCandidateState, adapt_vision_method_to_trade_candidate
from engines.vision_method import VisionCandidateState, VisionOptionConfirmation, calculate_vision_method_snapshot, validate_vision_method
from tests.test_vision_method_calculator_v1 import IST, NOW, option, request
from tests.test_vision_method_inspector_v1 import _runtime_snapshot


def test_runtime_exposes_1m_base_5m_decision_and_15m_confirmation_roles():
    runtime = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m", "15m")),
        RuntimeInstrument.NIFTY,
    )

    assert runtime.base_timeframe is TimeFrame.ONE_MINUTE
    assert runtime.vision_decision_timeframe is TimeFrame.FIVE_MINUTES
    assert runtime.confirmation_timeframe is TimeFrame.FIFTEEN_MINUTES
    assert TimeFrame.ONE_MINUTE in runtime.candle_engines
    assert TimeFrame.FIVE_MINUTES in runtime.candle_engines
    assert TimeFrame.FIFTEEN_MINUTES in runtime.candle_engines


def test_live_bridge_timeframe_authority_prefers_5m_decision_when_snapshot_is_1m():
    runtime_snapshot = replace(_runtime_snapshot(), timeframe="1m")
    runtime = type("Runtime", (), {"vision_decision_timeframe": TimeFrame.FIVE_MINUTES})()

    assert _vision_decision_timeframe(runtime, runtime_snapshot) is TimeFrame.FIVE_MINUTES


def test_five_minute_trace_writes_once_and_repeated_refresh_does_not_duplicate(tmp_path):
    trace = VisionForensicTrace(
        instrument=RuntimeInstrument.NIFTY,
        decision_timeframe=TimeFrame.FIVE_MINUTES,
        path=tmp_path / "trace.jsonl",
    )
    snapshot = calculate_vision_method_snapshot(request())
    report = validate_vision_method(snapshot)
    candidate = adapt_vision_method_to_trade_candidate(snapshot, report)
    candle = _decision_candle()

    assert trace.record(
        snapshot=snapshot,
        validation_report=report,
        source_candle=candle,
        runtime_timestamp=NOW,
        trade_candidate=candidate,
        risk_snapshot=None,
        paper_position=None,
        decision_audit=None,
        option_sync_status="synchronized",
        option_latency_ms=125.0,
    )
    assert not trace.record(
        snapshot=snapshot,
        validation_report=report,
        source_candle=candle,
        runtime_timestamp=NOW,
        trade_candidate=candidate,
        risk_snapshot=None,
        paper_position=None,
        decision_audit=None,
        option_sync_status="synchronized",
        option_latency_ms=125.0,
    )

    rows = _read_rows(tmp_path / "trace.jsonl")
    assert len(rows) == 1
    assert rows[0]["decision_timeframe"] == "5m"
    assert rows[0]["vision_method"]["candidate_state"] == "long_eligible"
    assert rows[0]["runtime_adapter"]["trade_candidate_created"] is True
    assert trace.counters.candles_evaluated == 1
    assert trace.counters.long_eligible == 1
    assert trace.counters.trade_candidates_created == 1


def test_one_minute_live_candle_close_does_not_write_vision_decision_trace(tmp_path):
    runtime = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m", "15m")),
        RuntimeInstrument.NIFTY,
    )
    runtime.start()
    runtime._vision_forensic_trace = VisionForensicTrace(
        instrument=RuntimeInstrument.NIFTY,
        decision_timeframe=TimeFrame.FIVE_MINUTES,
        path=tmp_path / "trace.jsonl",
    )

    runtime.process_tick(_tick(datetime(2026, 7, 29, 9, 15, 0, tzinfo=IST), 100.0))
    runtime.process_tick(_tick(datetime(2026, 7, 29, 9, 16, 0, tzinfo=IST), 101.0))

    assert len(runtime.get_candle_history(TimeFrame.ONE_MINUTE)) == 1
    assert len(runtime.get_candle_history(TimeFrame.FIVE_MINUTES)) == 0
    assert not (tmp_path / "trace.jsonl").exists()


def test_stale_prior_session_vision_reference_is_rejected(tmp_path):
    trace = VisionForensicTrace(
        instrument=RuntimeInstrument.NIFTY,
        decision_timeframe=TimeFrame.FIVE_MINUTES,
        path=tmp_path / "trace.jsonl",
    )
    snapshot = calculate_vision_method_snapshot(request())
    report = validate_vision_method(snapshot)
    stale_candidate = replace(
        adapt_vision_method_to_trade_candidate(snapshot, report),
        snapshot_reference="vision_method:NIFTY:5m:2026-07-29T10:30:00+05:30:long_eligible:high",
    )
    aug_7 = NOW.replace(month=8, day=7)
    aug_7_snapshot = replace(snapshot, timestamp=aug_7, price_action_trigger_context=None)
    aug_7_report = replace(report, timestamp=aug_7)
    candle = _decision_candle(timestamp=aug_7)

    with pytest.raises(ValueError, match="stale Vision snapshot reference"):
        trace.record(
            snapshot=aug_7_snapshot,
            validation_report=aug_7_report,
            source_candle=candle,
            runtime_timestamp=aug_7,
            trade_candidate=stale_candidate,
            risk_snapshot=None,
            paper_position=None,
            decision_audit=None,
            option_sync_status="synchronized",
            option_latency_ms=125.0,
        )


def test_session_rollover_resets_forensic_counters(tmp_path):
    trace = VisionForensicTrace(
        instrument=RuntimeInstrument.NIFTY,
        decision_timeframe=TimeFrame.FIVE_MINUTES,
        path=tmp_path / "trace.jsonl",
    )
    first = calculate_vision_method_snapshot(request())
    first_report = validate_vision_method(first)
    first_candidate = adapt_vision_method_to_trade_candidate(first, first_report)
    trace.record(
        snapshot=first,
        validation_report=first_report,
        source_candle=_decision_candle(),
        runtime_timestamp=NOW,
        trade_candidate=first_candidate,
        risk_snapshot=None,
        paper_position=None,
        decision_audit=None,
        option_sync_status="synchronized",
        option_latency_ms=125.0,
    )

    next_day = NOW + timedelta(days=1)
    second = replace(first, timestamp=next_day, price_action_trigger_context=None)
    second_report = replace(first_report, timestamp=next_day)
    second_candidate = replace(
        first_candidate,
        timestamp=next_day,
        snapshot_reference=f"vision_method:NIFTY:5m:{next_day.isoformat()}:long_eligible:high",
        validation_reference=f"vision_method_validation:NIFTY:5m:{next_day.isoformat()}:valid",
    )
    trace.record(
        snapshot=second,
        validation_report=second_report,
        source_candle=_decision_candle(timestamp=next_day),
        runtime_timestamp=next_day,
        trade_candidate=second_candidate,
        risk_snapshot=None,
        paper_position=None,
        decision_audit=None,
        option_sync_status="synchronized",
        option_latency_ms=125.0,
    )

    assert trace.counters.session_trading_date == next_day.date()
    assert trace.counters.candles_evaluated == 1
    assert len(_read_rows(tmp_path / "trace.jsonl")) == 2


def test_prepare_state_and_unavailable_option_are_traced_without_hard_blocking(tmp_path):
    trace = VisionForensicTrace(
        instrument=RuntimeInstrument.NIFTY,
        decision_timeframe=TimeFrame.FIVE_MINUTES,
        path=tmp_path / "trace.jsonl",
    )
    snapshot = calculate_vision_method_snapshot(
        request(option_confirmation_context=option(state=VisionOptionConfirmation.UNAVAILABLE))
    )
    report = validate_vision_method(snapshot)
    candidate = adapt_vision_method_to_trade_candidate(snapshot, report)

    trace.record(
        snapshot=snapshot,
        validation_report=report,
        source_candle=_decision_candle(),
        runtime_timestamp=NOW,
        trade_candidate=candidate,
        risk_snapshot=None,
        paper_position=None,
        decision_audit=None,
        option_sync_status="unavailable",
        option_latency_ms=None,
    )

    row = _read_rows(tmp_path / "trace.jsonl")[0]
    assert snapshot.candidate_state is VisionCandidateState.LONG_ELIGIBLE
    assert candidate.candidate_state is TradeCandidateState.LONG
    assert row["option_confirmation"]["state"] == "unavailable"
    assert row["entry_location"]["entry_location_state"] == "acceptable"
    assert row["runtime_adapter"]["trade_candidate_created"] is True
    assert row["risk"]["evaluated"] is False
    assert trace.counters.long_eligible == 1


def test_historical_warmup_seeds_complete_five_minute_decision_candles():
    runtime = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(timeframes=("1m", "5m", "15m")),
        RuntimeInstrument.NIFTY,
    )
    runtime.start()
    start = datetime(2026, 7, 29, 9, 15, tzinfo=IST)
    candles = tuple(
        Candle(
            symbol="NIFTY",
            timeframe="1m",
            start_time=start + timedelta(minutes=index),
            end_time=start + timedelta(minutes=index + 1),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=100 + index,
        )
        for index in range(5)
    )

    accepted = runtime.warm_up_candles(candles)
    decision_history = runtime.get_candle_history(TimeFrame.FIVE_MINUTES)
    confirmation_history = runtime.get_candle_history(TimeFrame.FIFTEEN_MINUTES)

    assert len(accepted) == 5
    assert len(runtime.get_candle_history(TimeFrame.ONE_MINUTE)) == 5
    assert len(decision_history) == 1
    assert decision_history[0].timeframe == "5m"
    assert decision_history[0].start_time == start
    assert decision_history[0].end_time == start + timedelta(minutes=5)
    assert decision_history[0].open == 100.0
    assert decision_history[0].high == 105.0
    assert decision_history[0].low == 99.0
    assert decision_history[0].close == 104.5
    assert decision_history[0].volume == 510
    assert confirmation_history == ()


def test_runtime_diagnostics_expose_timeframe_roles_and_forensic_counters_read_only():
    snapshot = replace(
        _runtime_snapshot(),
        timeframe="1m",
        base_timeframe="1m",
        vision_decision_timeframe="5m",
        confirmation_timeframe="15m",
        runtime_diagnostics=RuntimeDiagnostics(
            current_stage="READY",
            blocking_stage="NONE",
            current_candidate="prepare_long",
            paper_trade_state="idle",
            journal_state="ready_empty",
            last_successful_snapshot="vision_method:NIFTY:5m",
            last_validation="valid",
        ),
        vision_forensic_counters=VisionForensicCounters(
            runtime_session_id="NIFTY:2026-07-29:5m",
            session_trading_date=NOW.date(),
            decision_timeframe="5m",
            candles_evaluated=3,
            prepare_long=1,
            trade_candidates_created=1,
            paper_positions_opened=1,
            paper_positions_closed=1,
        ),
    )

    rows = {row.name: row.detail for row in _runtime_diagnostic_rows((snapshot,))}

    assert rows["NIFTY Base Timeframe"] == "1m"
    assert rows["NIFTY Vision Decision Timeframe"] == "5m"
    assert rows["NIFTY Confirmation Timeframe"] == "15m"
    assert rows["NIFTY 5m Candles Evaluated"] == "3"
    assert rows["NIFTY Prepare Long"] == "1"
    assert rows["NIFTY Trade Candidates Created"] == "1"
    assert rows["NIFTY Paper Positions Opened"] == "1"
    assert rows["NIFTY Paper Positions Closed"] == "1"
    assert rows["NIFTY Current Session Realized P&L"] == "0.0"
    assert rows["NIFTY Current Session Unrealized P&L"] == "0.0"


def _decision_candle(*, timestamp=NOW):
    return Candle(
        symbol="NIFTY",
        timeframe="5m",
        start_time=timestamp - timedelta(minutes=5),
        end_time=timestamp,
        open=100.0,
        high=104.0,
        low=99.0,
        close=103.0,
        volume=10_000,
    )


def _tick(timestamp, price):
    return Tick(Instrument.NIFTY, Exchange.NSE, timestamp, price, 1000, price - 0.5, price + 0.5, 10)


def _read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
