from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from application import ApplicationOrchestrator
from application.enums import RuntimeInstrument, RuntimeStatus
from application.lifecycle_manager import LifecycleSnapshot
from application.models import RuntimeConfiguration
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import CANDLE_CLOSED, NEW_TICK, OPTION_CHAIN_UPDATED
from dashboard.presenters import build_runtime_view
from engines.candle.candle_engine import CandleEngine
from engines.historical_market_replay import (
    HistoricalMarketReplayEngine,
    HistoricalReplayRepository,
    ReplayConfiguration,
    ReplayLifecycleError,
    ReplayLifecycleState,
    ReplayMode,
    ReplayOutcome,
    ReplaySeverity,
)
from engines.live_market_validation import LiveMarketValidationConfiguration, LiveMarketValidationEngine, ValidationMode


IST = timezone(timedelta(hours=5, minutes=30))
TS = datetime(2026, 7, 17, 9, 15, tzinfo=IST)


class Clock:
    def __init__(self):
        self.value = datetime(2026, 7, 18, 10, 0, tzinfo=IST)

    def __call__(self):
        return self.value


class Mono:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        current = self.value
        self.value += 0.001
        return current


class Sleeper:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


def manifest(record_count=3, instruments=("NIFTY",)):
    return {
        "schema_version": 1,
        "session_id": "nifty-20260717",
        "trading_date": "2026-07-17",
        "timezone": "Asia/Kolkata",
        "instruments": list(instruments),
        "created_at": "2026-07-18T10:00:00+05:30",
        "record_count": record_count,
        "source": "recorded_market_session",
    }


def tick_record(sequence, offset_ms=0, instrument="NIFTY", price=100.0):
    return {
        "schema_version": 1,
        "sequence": sequence,
        "record_type": "TICK",
        "event_timestamp": (TS + timedelta(milliseconds=offset_ms)).isoformat(),
        "instrument": instrument,
        "payload": {
            "exchange": "NSE",
            "last_price": price,
            "volume": sequence,
            "bid_price": price - 0.5,
            "ask_price": price + 0.5,
            "open_interest": 0,
        },
    }


def option_record(sequence=3, offset_ms=200, instrument="NIFTY", *, bid=9.5, ask=10.5, oi=100, duplicate_strike=False):
    strikes = [
        {
            "strike_price": 100.0,
            "call": {"last_price": 10.0, "open_interest": oi, "change_in_open_interest": 1, "volume": 2, "bid_price": bid, "ask_price": ask},
            "put": {"last_price": 11.0, "open_interest": 90, "change_in_open_interest": -1, "volume": 3, "bid_price": 10.0, "ask_price": 12.0},
        },
        {
            "strike_price": 101.0 if not duplicate_strike else 100.0,
            "call": {"last_price": 9.0, "open_interest": 80, "change_in_open_interest": 1, "volume": 1, "bid_price": 8.0, "ask_price": 10.0},
            "put": {"last_price": 12.0, "open_interest": 95, "change_in_open_interest": 1, "volume": 1, "bid_price": 11.0, "ask_price": 13.0},
        },
    ]
    return {
        "schema_version": 1,
        "sequence": sequence,
        "record_type": "OPTION_CHAIN",
        "event_timestamp": (TS + timedelta(milliseconds=offset_ms)).isoformat(),
        "instrument": instrument,
        "payload": {"exchange": "NSE", "expiry_date": "2026-07-30", "underlying_price": 100.5, "strikes": strikes},
    }


def write_session(tmp_path, rows=None, header=None):
    items = rows if rows is not None else (tick_record(1), tick_record(2, 100), option_record(3, 200))
    head = header if header is not None else manifest(len(items))
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(json.dumps(item) for item in (head, *items)), encoding="utf-8")
    return path


def engine(tmp_path, *, mode=ReplayMode.STEP, source=None, live_active=False, sleeper=None, mono=None, **overrides):
    config = ReplayConfiguration(enabled=True, mode=mode, source_path=source, output_dir=tmp_path / "reports", **overrides)
    return HistoricalMarketReplayEngine(
        EventBus(),
        config,
        clock=Clock(),
        monotonic_clock=mono or Mono(),
        sleeper=sleeper or Sleeper(),
        live_market_data_active=lambda: live_active,
    )


def test_configuration_defaults_and_validation(tmp_path):
    default = ReplayConfiguration(output_dir=tmp_path)
    assert default.enabled is False
    assert default.mode is ReplayMode.OFF
    assert ReplayConfiguration(enabled=True, mode=ReplayMode.STEP, source_path=tmp_path / "s", output_dir=tmp_path)
    assert ReplayConfiguration(enabled=True, mode=ReplayMode.REALTIME, source_path=tmp_path / "s", output_dir=tmp_path)
    assert ReplayConfiguration(enabled=True, mode=ReplayMode.ACCELERATED, source_path=tmp_path / "s", speed_multiplier=1000.0, output_dir=tmp_path)
    for bad in (0, -1, float("inf")):
        with pytest.raises(ValueError):
            ReplayConfiguration(speed_multiplier=bad, output_dir=tmp_path)
    with pytest.raises(ValueError):
        ReplayConfiguration(max_findings=0, output_dir=tmp_path)
    with pytest.raises(ValueError):
        ReplayConfiguration(enabled=True, mode=ReplayMode.STEP, auto_start=True, output_dir=tmp_path)
    with pytest.raises(ValueError):
        ReplayConfiguration(enabled=True, mode=ReplayMode.OFF, auto_start=True, source_path=tmp_path / "s", output_dir=tmp_path)


def test_repository_loads_valid_session_and_production_payloads(tmp_path):
    path = write_session(tmp_path)
    repo = HistoricalReplayRepository(tmp_path / "reports")
    loaded_manifest, records = repo.load_session(path)
    assert loaded_manifest.session_id == "nifty-20260717"
    assert loaded_manifest.instruments == (RuntimeInstrument.NIFTY,)
    assert records[0].payload.symbol is Instrument.NIFTY
    assert records[0].payload.timestamp == TS
    assert records[2].payload.symbol == "NIFTY"


@pytest.mark.parametrize(
    ("header", "rows", "message"),
    [
        ({"schema_version": 2}, (), "schema"),
        ({**manifest(0), "session_id": None}, (), "non-empty"),
        (manifest(0), (), "empty"),
        (manifest(2), (tick_record(1),), "record_count"),
        ({**manifest(1), "instruments": ["MIDCPNIFTY"]}, (tick_record(1, instrument="MIDCPNIFTY"),), "supports only"),
        (manifest(1), ({**tick_record(1), "record_type": "CANDLE"},), "record_type"),
        (manifest(1), ({**tick_record(1), "event_timestamp": "2026-07-17T09:15:00"},), "timezone"),
        (manifest(1), (tick_record(1, offset_ms=86400000),), "trading date"),
        (manifest(2), (tick_record(1), tick_record(1, 100)), "Duplicate"),
        (manifest(2), (tick_record(2, 100), tick_record(1)), "ordered"),
        (manifest(1), (tick_record(1, price=0),), "last_price"),
        (manifest(1), (option_record(bid=12, ask=10),), "bid_price"),
        (manifest(1), (option_record(oi=-1),), "open_interest"),
        (manifest(1), (option_record(duplicate_strike=True),), "unique"),
    ],
)
def test_repository_rejects_malformed_sessions(tmp_path, header, rows, message):
    path = write_session(tmp_path, rows=rows, header=header)
    with pytest.raises(Exception, match=message):
        HistoricalReplayRepository(tmp_path / "reports").load_session(path)


def test_malformed_json_and_report_handling(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{bad", encoding="utf-8")
    repo = HistoricalReplayRepository(tmp_path / "reports")
    with pytest.raises(ValueError, match="Malformed"):
        repo.load_session(path)
    report = tmp_path / "report.json"
    report.write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed"):
        repo.load_report(report)


def test_lifecycle_step_mode_publishes_one_record_per_step_and_completes(tmp_path):
    path = write_session(tmp_path)
    item = engine(tmp_path, source=path)
    events = []
    item._event_bus.subscribe(NEW_TICK, lambda payload: events.append(("tick", payload.timestamp)))
    item._event_bus.subscribe(OPTION_CHAIN_UPDATED, lambda payload: events.append(("option", payload.timestamp)))
    assert item.snapshot().lifecycle_state is ReplayLifecycleState.IDLE
    assert item.load_session().lifecycle_state is ReplayLifecycleState.READY
    first = item.step()
    assert first.counters.published_records == 1
    assert first.lifecycle_state is ReplayLifecycleState.PAUSED
    second = item.step()
    assert second.counters.published_records == 2
    final = item.step()
    assert final.lifecycle_state is ReplayLifecycleState.COMPLETED
    assert final.final_outcome is ReplayOutcome.PASS
    assert [kind for kind, _ in events] == ["tick", "tick", "option"]
    with pytest.raises(ReplayLifecycleError):
        item.step()


def test_invalid_lifecycle_commands_raise(tmp_path):
    item = engine(tmp_path, source=write_session(tmp_path))
    with pytest.raises(ReplayLifecycleError):
        item.start()
    with pytest.raises(ReplayLifecycleError):
        item.pause()
    item.load_session()
    item.reset()
    with pytest.raises(ReplayLifecycleError):
        item.step()


def test_realtime_and_accelerated_timing_use_injected_sleeper(tmp_path):
    rows = (tick_record(1), tick_record(2, 1000), tick_record(3, 3000))
    path = write_session(tmp_path, rows=rows, header=manifest(len(rows)))
    sleeper = Sleeper()
    realtime = engine(tmp_path, mode=ReplayMode.REALTIME, source=path, sleeper=sleeper)
    realtime.load_session()
    realtime.start()
    assert sleeper.calls == [1.0, 2.0]
    sleeper_fast = Sleeper()
    accelerated = engine(tmp_path, mode=ReplayMode.ACCELERATED, source=path, sleeper=sleeper_fast, speed_multiplier=10.0)
    accelerated.load_session()
    accelerated.start()
    assert sleeper_fast.calls == [0.1, 0.2]


def test_replay_blocks_live_feed_without_publishing_or_mutating_live_config(tmp_path):
    path = write_session(tmp_path)
    item = engine(tmp_path, source=path, live_active=True)
    published = []
    item._event_bus.subscribe(NEW_TICK, published.append)
    item.load_session()
    with pytest.raises(ReplayLifecycleError, match="live market data"):
        item.start()
    assert published == []
    assert item.snapshot().lifecycle_state is ReplayLifecycleState.READY
    assert "LIVE_FEED_ACTIVE" in {finding.code for finding in item.snapshot().active_findings}


def test_pause_resume_stop_reset_and_reports(tmp_path):
    path = write_session(tmp_path)
    item = engine(tmp_path, source=path)
    item.load_session()
    assert item.start().lifecycle_state is ReplayLifecycleState.RUNNING
    assert item.pause().lifecycle_state is ReplayLifecycleState.PAUSED
    assert item.step().counters.published_records == 1
    assert item.step().counters.published_records == 2
    stopped = item.stop()
    assert stopped.lifecycle_state is ReplayLifecycleState.STOPPED
    assert item.latest_report().outcome is ReplayOutcome.STOPPED
    assert item.latest_report().report_path.exists()
    assert item.reset().lifecycle_state is ReplayLifecycleState.IDLE


def test_failure_on_publish_stops_and_persists_report(tmp_path):
    path = write_session(tmp_path, rows=(tick_record(1),), header=manifest(1))
    item = engine(tmp_path, mode=ReplayMode.REALTIME, source=path)
    item._event_bus.subscribe(NEW_TICK, lambda payload: (_ for _ in ()).throw(RuntimeError("boom access_token secret")))
    item.load_session()
    snap = item.start()
    assert snap.lifecycle_state is ReplayLifecycleState.FAILED
    assert snap.counters.published_records == 0
    assert "access_token" not in snap.failure_reason
    assert item.latest_report().outcome is ReplayOutcome.FAIL


def test_replay_models_are_immutable_and_memory_is_bounded(tmp_path):
    rows = tuple(tick_record(index + 1, index, price=100 + index) for index in range(20))
    path = write_session(tmp_path, rows=rows, header=manifest(len(rows)))
    item = engine(tmp_path, mode=ReplayMode.REALTIME, source=path, max_recent_identities=5, max_latency_samples=4, max_findings=3)
    snap = item.load_session()
    with pytest.raises(FrozenInstanceError):
        snap.session_id = "changed"
    item.start()
    assert len(item._recent_identities) == 5
    assert len(item._latencies) == 4
    for index in range(10):
        item._add_finding(ReplaySeverity.WARNING, f"WARN_{index}", "bounded")
    assert len(item.snapshot().active_findings) == 3
    assert not hasattr(item.snapshot(), "records")


def test_no_durable_io_per_replay_record(monkeypatch, tmp_path):
    path = write_session(tmp_path)
    fsync_calls = {"count": 0}
    original = __import__("engines.historical_market_replay.repository", fromlist=["os"]).os.fsync

    def fake_fsync(fd):
        fsync_calls["count"] += 1
        return original(fd)

    monkeypatch.setattr("engines.historical_market_replay.repository.os.fsync", fake_fsync)
    item = engine(tmp_path, source=path)
    item.load_session()
    item.step()
    item.step()
    assert fsync_calls["count"] == 0
    item.step()
    assert fsync_calls["count"] == 1


def test_replay_drives_existing_candle_engine_and_validation_without_calculating_candles(tmp_path):
    rows = (tick_record(1, 0), tick_record(2, 61000))
    path = write_session(tmp_path, rows=rows, header=manifest(len(rows)))
    bus = EventBus()
    candle = CandleEngine(bus)
    closed = []
    bus.subscribe(NEW_TICK, candle.on_tick)
    bus.subscribe(CANDLE_CLOSED, closed.append)
    validation = LiveMarketValidationEngine(
        bus,
        LiveMarketValidationConfiguration(enabled=True, mode=ValidationMode.SIMULATION, output_dir=tmp_path / "validation"),
        clock=Clock(),
        monotonic_clock=Mono(),
    )
    validation.start_session(session_id="replay-validation")
    item = HistoricalMarketReplayEngine(bus, ReplayConfiguration(enabled=True, mode=ReplayMode.REALTIME, source_path=path, output_dir=tmp_path / "reports"), clock=Clock(), monotonic_clock=Mono(), sleeper=Sleeper())
    item.load_session()
    item.start()
    assert len(closed) == 1
    assert validation.snapshot().instrument_summaries[0].tick_metrics.received_ticks == 2
    assert item.snapshot().counters.broker_order_calls == 0


def test_replay_works_when_validation_is_disabled_and_is_deterministic(tmp_path):
    path = write_session(tmp_path)

    def run_once():
        item = engine(tmp_path, mode=ReplayMode.REALTIME, source=path)
        events = []
        item._event_bus.subscribe(NEW_TICK, lambda payload: events.append(("tick", payload.timestamp, payload.last_price)))
        item._event_bus.subscribe(OPTION_CHAIN_UPDATED, lambda payload: events.append(("option", payload.timestamp, len(payload.strikes))))
        item.load_session()
        final = item.start()
        return events, final.counters, final.progress_percentage, final.final_outcome

    assert run_once() == run_once()


def test_application_snapshot_dashboard_and_shutdown_integration(tmp_path):
    path = write_session(tmp_path)
    config = RuntimeConfiguration(historical_replay_configuration=ReplayConfiguration(enabled=True, mode=ReplayMode.STEP, source_path=path, output_dir=tmp_path / "reports"))
    orchestrator = ApplicationOrchestrator(EventBus(), config)
    snap = orchestrator.snapshot()
    assert snap.historical_replay.lifecycle_state is ReplayLifecycleState.IDLE
    replay = orchestrator.historical_replay_engine
    replay.load_session()
    replay.step()
    view = build_runtime_view(LifecycleSnapshot(RuntimeStatus.RUNNING, 1, 0, 0, TS, None, None, orchestrator.snapshot()))
    assert view.replay_state == "Paused"
    assert view.replay_source == "Session.Jsonl"
    assert view.replay_published_records == 1
    stopped = orchestrator.stop()
    assert stopped.historical_replay.lifecycle_state is ReplayLifecycleState.STOPPED


def test_broker_safety_and_package_search():
    package = Path("engines/historical_market_replay")
    text = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    assert "place_order" not in text
    assert "modify_order" not in text
    assert "cancel_order" not in text
    assert "broker_order_calls: int = 0" in Path("engines/historical_market_replay/models.py").read_text(encoding="utf-8")
