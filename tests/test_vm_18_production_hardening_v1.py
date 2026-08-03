from __future__ import annotations

from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import timedelta
import gc
import json
from pathlib import Path
import threading
import time
import tracemalloc

from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from application.symbol_runtime import SymbolRuntime
from core.event_bus import EventBus
from core.models.daily_ohlc import DailyOHLC
from dashboard.presenters import build_dashboard_view, build_runtime_view
from tests.test_dashboard_presenters import lifecycle
from tests.test_vision_method_validation_v1 import NOW, snapshot
from tests.test_vision_paper_trading_integration_v1 import process, tick


FORBIDDEN_SECRET_TOKENS = (
    "access_token",
    "request_token",
    "api_secret",
    "password",
    "totp_seed",
    "ZERODHA_ACCESS_TOKEN",
)

PRODUCTION_STAGES = {
    "Application Startup",
    "Market Data",
    "Reference Data",
    "Candle Engine",
    "Daily Context",
    "Opening Range",
    "Structure",
    "Liquidity",
    "Structure Events",
    "Setup Qualification",
    "Option Feed",
    "Option Snapshot",
    "Option Analytics",
    "Option Confirmation",
    "Vision Method",
    "Validation",
    "Runtime Adapter",
    "TradeCandidate",
    "Risk",
    "Lifecycle",
    "Paper Position",
    "Paper Trade",
    "Journal",
    "AI Explanation",
}


def runtime_with_daily_context() -> SymbolRuntime:
    item = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    item.start()
    previous_day = NOW.date() - timedelta(days=1)
    item.process_daily_ohlc(
        DailyOHLC(previous_day, 100.0, 110.0, 90.0, 105.0),
        levels_trading_date=NOW.date(),
    )
    item.process_tick(tick(timestamp=NOW.replace(hour=9, minute=15, second=0), price=100.0))
    item.process_tick(tick(timestamp=NOW.replace(hour=9, minute=31, second=0), price=103.0))
    return item


def close_open_position(item: SymbolRuntime) -> None:
    view = item.snapshot()
    objective = view.trade_lifecycle_v1.risk_decision.objective_price
    item._process_paper_tick(tick(objective + 0.5, timestamp=view.trade_lifecycle_v1.timestamp + timedelta(seconds=1)))


def safe_text(value) -> str:
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(value, default=str, sort_keys=True)


def test_vm18_runtime_verification_report_covers_every_stage_with_owner_latency_and_recovery():
    item = runtime_with_daily_context()
    candidate, report = process(item, snapshot())
    close_open_position(item)

    view = item.snapshot()
    stages = {stage.stage: stage for stage in view.runtime_verification_report}

    assert PRODUCTION_STAGES <= set(stages)
    for stage in stages.values():
        assert stage.owner
        assert stage.producer
        assert stage.consumer
        assert stage.session is view.runtime_session
        assert stage.status in {"READY", "WAITING", "BLOCKED", "FAILED"}
        assert stage.latency_ms is None or stage.latency_ms >= 0.0
        assert stage.recovery_state in {"NO_POSITION", "RESTORED", "CHECKPOINT_ACTIVE"}
        assert isinstance(stage.prerequisites, tuple)
        assert isinstance(stage.readiness_conditions, tuple)
        assert isinstance(stage.blocking_conditions, tuple)
        assert stage.readiness_conditions
        assert stage.blocking_conditions
    assert stages["Vision Method"].timestamp == item._vision_method_snapshot.timestamp
    assert "Option Confirmation" in stages["Vision Method"].prerequisites
    assert stages["TradeCandidate"].prerequisites == ("Runtime Adapter",)
    assert stages["Risk"].prerequisites == ("Strategy",)
    assert stages["Validation"].timestamp == report.timestamp
    assert stages["TradeCandidate"].timestamp == candidate.timestamp
    assert stages["Journal"].status == "READY"


def test_vm18_event_bus_prevents_duplicate_subscribers_and_cleans_up_listeners():
    bus = EventBus()
    events = []

    def listener(payload):
        events.append(payload)

    bus.subscribe("runtime", listener)
    bus.subscribe("runtime", listener)
    bus.publish("runtime", {"sequence": 1})
    bus.unsubscribe("runtime", listener)
    bus.publish("runtime", {"sequence": 2})
    bus.subscribe("runtime", listener)
    bus.clear()
    bus.publish("runtime", {"sequence": 3})

    assert events == [{"sequence": 1}]
    assert all(not callbacks for callbacks in bus._subscribers.values())


def test_vm18_event_bus_nested_publish_order_is_deterministic_without_duplicate_delivery():
    bus = EventBus()
    delivered = []

    def first(payload):
        delivered.append(("first", payload))
        if payload == 1:
            bus.publish("runtime", 2)

    def second(payload):
        delivered.append(("second", payload))

    bus.subscribe("runtime", first)
    bus.subscribe("runtime", second)
    bus.publish("runtime", 1)

    assert delivered == [("first", 1), ("first", 2), ("second", 2), ("second", 1)]


def test_vm18_long_session_snapshot_stress_has_bounded_memory_and_no_duplicate_runtime_objects():
    item = runtime_with_daily_context()
    method_snapshot = snapshot()
    process(item, method_snapshot)
    initial_runtime_ids = {
        id(item.candle_engine),
        id(item.trade_lifecycle_v1),
        id(item.trade_journal_v1_engine),
        id(item.risk_management_v2_engine),
    }

    gc.collect()
    tracemalloc.start()
    start_current, start_peak = tracemalloc.get_traced_memory()
    for index in range(120):
        ts = NOW.replace(hour=10, minute=0, second=0) + timedelta(seconds=index)
        item.process_tick(tick(100.0 + (index % 5) * 0.05, timestamp=ts))
        process(item, method_snapshot)
        item.snapshot()
    end_current, end_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    final_runtime_ids = {
        id(item.candle_engine),
        id(item.trade_lifecycle_v1),
        id(item.trade_journal_v1_engine),
        id(item.risk_management_v2_engine),
    }

    assert final_runtime_ids == initial_runtime_ids
    assert end_current - start_current < 8_000_000
    assert end_peak - start_peak < 16_000_000
    assert item.snapshot().trade_lifecycle_v1.position_open_count == 1
    assert item.snapshot().runtime_diagnostics.current_candidate == "long"


def test_vm18_cpu_latency_stress_remains_within_production_guardrails():
    item = runtime_with_daily_context()
    method_snapshot = snapshot()
    samples = []

    for index in range(40):
        ts = NOW.replace(hour=10, minute=15, second=0) + timedelta(seconds=index)
        started = time.perf_counter()
        item.process_tick(tick(101.0 + (index % 3) * 0.1, timestamp=ts))
        process(item, method_snapshot)
        build_runtime_view(lifecycle(item.snapshot()))
        samples.append((time.perf_counter() - started) * 1000.0)

    average_ms = sum(samples) / len(samples)
    maximum_ms = max(samples)

    assert average_ms < 250.0
    assert maximum_ms < 1000.0


def test_vm18_thread_audit_runtime_work_does_not_spawn_orphan_threads():
    before = {thread.ident for thread in threading.enumerate() if thread.ident is not None}
    item = runtime_with_daily_context()
    method_snapshot = snapshot()

    for index in range(25):
        item.process_tick(tick(100.0 + index * 0.01, timestamp=NOW + timedelta(seconds=index)))
        process(item, method_snapshot)
        item.snapshot()
    item.stop()

    after = {thread.ident for thread in threading.enumerate() if thread.ident is not None}
    assert after <= before | {threading.current_thread().ident}


def test_vm18_reconnect_and_shutdown_do_not_duplicate_candidates_positions_or_journal_entries():
    item = runtime_with_daily_context()
    method_snapshot = snapshot()
    process(item, method_snapshot)
    first = item.snapshot()
    close_open_position(item)
    closed_once = item.snapshot()

    item.stop()
    item.start()
    item.process_tick(tick(timestamp=NOW + timedelta(minutes=1), price=100.0))
    process(item, method_snapshot)
    close_open_position(item)
    recovered = item.snapshot()

    assert recovered.vision_trade_candidate == first.vision_trade_candidate
    assert recovered.trade_journal_v1.trade_count == closed_once.trade_journal_v1.trade_count == 1
    assert recovered.canonical_paper_position.trade_id == first.canonical_paper_position.trade_id
    assert recovered.trade_lifecycle_v1.position_open_count == 1


def test_vm18_session_rollover_keeps_daily_context_and_snapshot_timestamps_synchronized():
    item = runtime_with_daily_context()
    day_one = NOW.date()
    day_two = day_one + timedelta(days=1)

    item.process_tick(tick(timestamp=NOW.replace(hour=15, minute=30, second=0), price=101.0))
    item.process_tick(tick(timestamp=NOW.replace(day=NOW.day + 1, hour=9, minute=15, second=0), price=102.0))

    view = item.snapshot()
    stages = {stage.stage: stage for stage in view.runtime_verification_report}

    assert view.runtime_session.trading_date == day_two
    assert view.runtime_session.cpr_trading_date == day_two
    assert view.runtime_session.camarilla_trading_date == day_two
    assert view.snapshot_created_at == view.runtime_session.market_timestamp
    assert stages["Daily Context"].status == "READY"
    assert "Stale" not in stages["Daily Context"].blocking_reason


def test_vm18_dashboard_large_state_rendering_is_snapshot_only_and_fast():
    item = runtime_with_daily_context()
    process(item, snapshot())
    close_open_position(item)
    lifecycle_snapshot = lifecycle(item.snapshot())

    started = time.perf_counter()
    for _ in range(50):
        dashboard = build_dashboard_view(lifecycle_snapshot)
        runtime_view = dashboard.runtime
        assert runtime_view.component_health
        assert any(row.name == "Vision Method Calculator" for row in runtime_view.component_health)
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert elapsed_ms < 1500.0


def test_vm18_runtime_dashboard_journal_and_snapshots_do_not_expose_secret_material():
    item = runtime_with_daily_context()
    process(item, snapshot())
    close_open_position(item)
    runtime_snapshot = item.snapshot()
    dashboard = build_dashboard_view(lifecycle(runtime_snapshot))

    payload = "\n".join(
        (
            safe_text(runtime_snapshot),
            safe_text(dashboard),
            safe_text(runtime_snapshot.trade_journal_v1),
            safe_text(runtime_snapshot.journal_persistence),
            safe_text(runtime_snapshot.runtime_verification_report),
        )
    )

    lowered = payload.casefold()
    for token in FORBIDDEN_SECRET_TOKENS:
        assert token.casefold() not in lowered


def test_vm18_production_source_audit_has_no_forbidden_runtime_mutation_or_unbounded_debug_output():
    source_files = [
        Path("application/symbol_runtime.py"),
        Path("application/orchestrator.py"),
        Path("dashboard/presenters.py"),
        Path("application/broker_account_sync/coordinator.py"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)

    trading_runtime_source = Path("application/symbol_runtime.py").read_text(encoding="utf-8")
    assert "datetime.now" not in trading_runtime_source
    assert "datetime.utcnow" not in trading_runtime_source
    assert "print(" not in combined
    assert "logging.basicConfig" not in combined
    assert "place_order(" not in combined
    assert "modify_order(" not in combined
    assert "cancel_order(" not in combined
    assert "exit_position(" not in combined


def test_vm18_runtime_verification_report_has_no_duplicate_stage_rows():
    item = runtime_with_daily_context()
    process(item, snapshot())
    rows = item.snapshot().runtime_verification_report
    counts = Counter(row.stage for row in rows)

    assert all(count == 1 for count in counts.values())
    assert len(rows) == len(counts)



