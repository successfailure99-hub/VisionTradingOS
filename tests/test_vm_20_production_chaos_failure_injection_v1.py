from __future__ import annotations

import gc
import json
import os
import threading
import time
import tracemalloc
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from application import ApplicationBootstrap, RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from application.orchestrator import ApplicationOrchestrator
from application.broker_account_sync import BrokerAccountSyncCoordinator
from application.reference_data_bootstrap import run_reference_data_bootstrap
from brokers.zerodha.auth.enums import ZerodhaAuthStatus
from brokers.zerodha.auth.models import ZerodhaAuthSnapshot
from brokers.zerodha.instruments import ZerodhaInstrumentRecord, ZerodhaInstrumentResolution, ZerodhaInstrumentType
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from desktop.vision_method import VisionMethodInspector, VisionMethodLiveInspectorBridge
from dashboard.presenters import build_dashboard_view
from engines.vision_method import VisionCandidateState
from tests.test_dashboard_presenters import lifecycle
from tests.test_desktop_live_market_data import historical_factory_factory
from tests.test_vm_17_broker_account_sync_v1 import FakeReadOnlyBrokerClient, auth
from tests.test_vm_18_production_hardening_v1 import PRODUCTION_STAGES
from tests.test_vision_method_validation_v1 import NOW, snapshot
from tests.test_vision_paper_trading_integration_v1 import process, tick


IST = ZoneInfo("Asia/Kolkata")
SUNDAY = datetime(2026, 8, 2, 10, 0, tzinfo=IST)
FRIDAY_OPEN = datetime(2026, 7, 31, 9, 15, tzinfo=IST)


def qt_app():
    return QApplication.instance() or QApplication([])


def subscription(instrument=Instrument.NIFTY, token=101, exchange=Exchange.NSE):
    return ZerodhaInstrumentSubscription(token, instrument, exchange)


def raw_minute(offset: int, *, close: float = 101.0):
    at = FRIDAY_OPEN + timedelta(minutes=offset)
    return {"date": at, "open": 100.0, "high": 104.0, "low": 98.0, "close": close, "volume": 10}


class HistoricalClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def historical_data(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0) if self.responses else []


def runtime_with_context() -> SymbolRuntime:
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


def safe_text(value) -> str:
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(value, default=str, sort_keys=True)


def test_vm20_weekend_reference_bootstrap_seeds_previous_session_candles_and_moves_beyond_candle_gate():
    qt_app()
    lifecycle_manager = ApplicationBootstrap().create_application()
    lifecycle_manager.start()
    client = HistoricalClient([[raw_minute(0), raw_minute(1), raw_minute(2)]])

    run_reference_data_bootstrap(
        lifecycle=lifecycle_manager,
        historical_client=client,
        subscriptions=(subscription(),),
        clock=lambda: SUNDAY,
    )

    history = lifecycle_manager.orchestrator.get_candle_history("NIFTY")
    runtime = lifecycle_manager.orchestrator.get_runtime("NIFTY")
    view = runtime.snapshot()
    result = VisionMethodLiveInspectorBridge(lifecycle_manager, VisionMethodInspector()).refresh()

    assert len(history) == 3
    assert history[-1].start_time.date().isoformat() == "2026-07-31"
    assert view.latest_candle == history[-1]
    assert view.cpr is not None
    assert view.camarilla is not None
    assert view.cpr.trading_date == SUNDAY.date()
    assert view.camarilla.trading_date == SUNDAY.date()
    assert result.status.blocking_stage != "CANDLE_ENGINE"


def test_vm20_empty_and_corrupted_historical_warmup_fail_safe_without_crashing_runtime():
    qt_app()
    lifecycle_manager = ApplicationBootstrap().create_application()
    lifecycle_manager.start()
    client = HistoricalClient([[], [{"date": FRIDAY_OPEN, "open": "bad"}]])

    empty = run_reference_data_bootstrap(
        lifecycle=lifecycle_manager,
        historical_client=client,
        subscriptions=(subscription(),),
        clock=lambda: SUNDAY,
    )
    corrupted = run_reference_data_bootstrap(
        lifecycle=lifecycle_manager,
        historical_client=client,
        subscriptions=(subscription(),),
        clock=lambda: SUNDAY,
    )

    runtime = lifecycle_manager.orchestrator.get_runtime("NIFTY")
    result = VisionMethodLiveInspectorBridge(lifecycle_manager, VisionMethodInspector()).refresh()

    assert len(empty) == 1
    assert len(corrupted) == 1
    assert lifecycle_manager.orchestrator.get_candle_history("NIFTY") == ()
    assert runtime.snapshot().status.value == "running"
    assert result.status.blocking_stage in {"MARKET_DATA", "CANDLE_ENGINE"}


def test_vm20_market_data_timestamp_and_duplicate_tick_failures_preserve_deterministic_state():
    orchestrator = ApplicationOrchestrator(EventBus(), RuntimeConfiguration())
    orchestrator.start()
    first = tick(timestamp=NOW, price=100.0)
    duplicate = tick(timestamp=NOW, price=100.0)
    stale = tick(timestamp=NOW - timedelta(minutes=1), price=99.0)
    future = tick(timestamp=NOW + timedelta(days=10), price=101.0)

    first_view = orchestrator.process_tick(first)
    duplicate_view = orchestrator.process_tick(duplicate)
    with pytest.raises(ValueError, match="Stale tick received"):
        orchestrator.process_tick(stale)
    stale_view = orchestrator.get_runtime("NIFTY").snapshot()
    future_view = orchestrator.process_tick(future)

    assert duplicate_view.latest_tick_at == first_view.latest_tick_at
    assert stale_view.latest_tick_at == first_view.latest_tick_at
    assert future_view.latest_tick_at >= first_view.latest_tick_at
    assert len(orchestrator.get_candle_history("NIFTY")) <= 1


def test_vm20_daily_context_and_vision_context_failures_are_visible_without_hidden_fallbacks():
    qt_app()
    item = runtime_with_context()
    stale_day = NOW.date() - timedelta(days=2)
    with pytest.raises(ValueError, match="Stale CPR DailyOHLC"):
        item.process_daily_ohlc(DailyOHLC(stale_day, 100.0, 110.0, 90.0, 105.0), levels_trading_date=stale_day)
    lifecycle_manager = ApplicationBootstrap().create_application()
    object.__setattr__(lifecycle_manager.orchestrator, "_runtimes", {RuntimeInstrument.NIFTY: item})

    result = VisionMethodLiveInspectorBridge(lifecycle_manager, VisionMethodInspector()).refresh()
    stages = {stage.stage: stage for stage in item.snapshot().runtime_verification_report}

    assert result.rendered is True
    assert result.status.blocking_stage in {"CPR", "Camarilla", "LEVEL_CONTEXT", "OPENING_RANGE", "Setup", "VISION_METHOD"}
    assert stages["Daily Context"].status in {"READY", "BLOCKED"}
    assert result.status.blocking_reason != "-"


def test_vm20_runtime_adapter_risk_lifecycle_paper_and_journal_failures_do_not_duplicate_state():
    item = runtime_with_context()
    method_snapshot = snapshot()
    candidate, report = process(item, method_snapshot)
    first = item.snapshot()
    process(item, method_snapshot)
    duplicate = item.snapshot()

    objective = duplicate.trade_lifecycle_v1.risk_decision.objective_price
    close_tick = tick(objective + 0.5, timestamp=duplicate.trade_lifecycle_v1.timestamp + timedelta(seconds=1))
    item._process_paper_tick(close_tick)
    closed_once = item.snapshot()
    item._process_paper_tick(close_tick)
    closed_twice = item.snapshot()

    assert duplicate.vision_trade_candidate == candidate
    assert duplicate.risk_management_v2 is first.risk_management_v2
    assert duplicate.trade_lifecycle_v1.processing_count == first.trade_lifecycle_v1.processing_count
    assert closed_once.trade_journal_v1.trade_count == 1
    assert closed_twice.trade_journal_v1.trade_count == 1
    assert closed_twice.canonical_paper_position.trade_id == closed_once.canonical_paper_position.trade_id
    assert report == item.snapshot().vision_method_validation_report


def test_vm20_non_actionable_and_risk_rejected_candidates_stop_before_lifecycle_and_paper_trade():
    for state in (VisionCandidateState.WAIT, VisionCandidateState.OBSERVE, VisionCandidateState.AVOID, VisionCandidateState.INSUFFICIENT_DATA):
        item = runtime_with_context()
        process(item, replace(snapshot(), candidate_state=state))
        view = item.snapshot()
        assert view.risk_management_v2 is None
        assert view.trade_lifecycle_v1.processing_count == 0
        assert view.canonical_paper_position is None
        assert view.decision_audit.rejected is True


def test_vm20_broker_failure_retains_last_valid_read_only_snapshot_and_never_mutates():
    coordinator = BrokerAccountSyncCoordinator()
    client = FakeReadOnlyBrokerClient()
    coordinator.configure_client(client)
    coordinator.observe_authentication(auth())
    first = coordinator.refresh(timestamp=NOW, force=True)
    client.fail_next = True

    stale = coordinator.refresh(timestamp=NOW + timedelta(seconds=30), force=True)
    expired = coordinator.observe_authentication(
        ZerodhaAuthSnapshot(
            status=ZerodhaAuthStatus.AUTHENTICATED,
            user_id="ABCD123456",
            api_key_hint="****1234",
            authenticated_at=NOW,
            expires_at=NOW - timedelta(seconds=1),
            last_error=None,
            login_url=None,
        )
    )

    assert stale.is_stale is True
    assert stale.positions == first.positions
    assert stale.holdings == first.holdings
    assert stale.orders == first.orders
    assert first.mutation_mode.value == "DISABLED"
    assert expired.authentication_state.value == "token_expired"
    assert not any(call in client.calls for call in ("place_order", "modify_order", "cancel_order", "exit_position"))


def test_vm20_dashboard_ai_security_memory_thread_and_event_bus_survive_failure_pressure():
    before_threads = {thread.ident for thread in threading.enumerate() if thread.ident is not None}
    item = runtime_with_context()
    process(item, snapshot())
    lifecycle_snapshot = lifecycle(item.snapshot())

    gc.collect()
    tracemalloc.start()
    start_current, start_peak = tracemalloc.get_traced_memory()
    for _ in range(25):
        dashboard = build_dashboard_view(lifecycle_snapshot)
        assert dashboard.runtime.component_health
        assert dashboard.ai[0].market_summary.startswith("Vision Method")
    end_current, end_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    bus = EventBus()
    delivered = []

    def listener(payload):
        delivered.append(payload)
        bus.unsubscribe("chaos", listener)

    bus.subscribe("chaos", listener)
    bus.subscribe("chaos", listener)
    bus.publish("chaos", "first")
    bus.publish("chaos", "second")

    after_threads = {thread.ident for thread in threading.enumerate() if thread.ident is not None}
    payload = safe_text(item.snapshot()) + safe_text(dashboard)

    assert delivered == ["first"]
    assert after_threads <= before_threads | {threading.current_thread().ident}
    assert end_current - start_current < 8_000_000
    assert end_peak - start_peak < 16_000_000
    assert "access_token" not in payload.lower()
    assert "api_secret" not in payload.lower()
