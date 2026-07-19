from __future__ import annotations

import json
import os
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from application import ApplicationOrchestrator
from application.deterministic_backtest_driver import DeterministicBacktestDriver
from application.desktop_live_data import (
    DesktopLiveDataConfigurationError,
    _backtest_is_active,
    create_dashboard_application,
    create_desktop_live_runtime,
    create_zerodha_session_manager,
    load_desktop_live_configuration,
)
from application.enums import ExecutionSafetyMode, RuntimeInstrument
from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data import LiveMarketDataRuntimeFactory
from application.models import RuntimeConfiguration
from brokers.zerodha.enums import BrokerExecutionMode
from core.event_bus import EventBus
from core.events import BACKTEST_COMPLETED, NEW_TICK, PAPER_TRADE_RECORDED
from engines.deterministic_backtest import (
    BacktestConfiguration,
    BacktestLifecycleError,
    BacktestLifecycleState,
    BacktestMode,
    BacktestOutcome,
    ReproducibilityStatus,
)
from engines.historical_market_replay import ReplayConfiguration, ReplayMode
from engines.paper_trading.enums import PaperExitType
from engines.paper_trading.models import PaperTradeRecord
from engines.strategy.enums import TradeDirection


IST = timezone(timedelta(hours=5, minutes=30))
TS = datetime(2026, 7, 17, 9, 15, tzinfo=IST)


class FakeAuthClient:
    def __init__(self, api_key):
        self.api_key = api_key

    def set_access_token(self, access_token):
        self.access_token = access_token

    def profile(self):
        return {"user_id": "AB1234"}


class FakeTickerClient:
    def __init__(self):
        self.connect_calls = 0
        self.close_calls = 0

    def set_callbacks(self, **callbacks):
        self.callbacks = callbacks

    def connect(self, *, threaded=True):
        self.connect_calls += 1

    def close(self):
        self.close_calls += 1

    def subscribe(self, instrument_tokens):
        pass

    def unsubscribe(self, instrument_tokens):
        pass

    def set_mode(self, mode, instrument_tokens):
        pass


def manifest(record_count=3, session_id="nifty-20260717", instruments=("NIFTY",)):
    return {
        "schema_version": 1,
        "session_id": session_id,
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


def write_session(tmp_path, name="session.jsonl", *, rows=None, header=None):
    items = rows if rows is not None else (tick_record(1), tick_record(2, 100), tick_record(3, 200))
    head = header if header is not None else manifest(len(items), session_id=name.replace(".jsonl", ""))
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(item) for item in (head, *items)), encoding="utf-8")
    return path


def config(tmp_path, *paths, **overrides):
    return BacktestConfiguration(
        enabled=True,
        mode=BacktestMode.SINGLE_SESSION if len(paths) == 1 else BacktestMode.BATCH,
        session_paths=paths,
        output_directory=tmp_path / "backtest_reports",
        **overrides,
    )


def orchestrator(tmp_path, *paths, **overrides):
    configuration = RuntimeConfiguration(
        instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX),
        deterministic_backtest_configuration=config(tmp_path, *paths, **overrides),
    )
    return ApplicationOrchestrator(EventBus(), configuration)


def auth_factory(api_key):
    return FakeAuthClient(api_key)


def live_env(**overrides):
    env = {
        "LIVE_MARKET_DATA_ENABLED": "true",
        "LIVE_MARKET_DATA_AUTO_CONNECT": "true",
        "ZERODHA_API_KEY": "desktop_api_key",
        "ZERODHA_API_SECRET": "desktop_api_secret",
        "ZERODHA_ACCESS_TOKEN": "desktop_access_token",
        "NIFTY_INSTRUMENT_TOKEN": "101",
        "BANKNIFTY_INSTRUMENT_TOKEN": "102",
        "SENSEX_INSTRUMENT_TOKEN": "103",
        "LIVE_FUTURES_VWAP_ENABLED": "false",
        "REFERENCE_DATA_BOOTSTRAP_ENABLED": "false",
    }
    env.update(overrides)
    return env


def backtest_env(path, **overrides):
    env = {
        "LIVE_MARKET_DATA_ENABLED": "false",
        "BACKTEST_ENABLED": "true",
        "BACKTEST_MODE": "SINGLE_SESSION",
        "BACKTEST_SESSION_PATHS": str(path),
        "BACKTEST_OUTPUT_DIRECTORY": str(path.parent / "backtests"),
    }
    env.update(overrides)
    return env


def trade(trade_id="t1", pnl=100.0):
    return PaperTradeRecord(
        trade_id=trade_id,
        position_id=f"p-{trade_id}",
        paper_order_id=f"o-{trade_id}",
        plan_id=f"plan-{trade_id}",
        instrument="NIFTY",
        direction=TradeDirection.BULLISH,
        quantity=50,
        lot_size=50,
        entry_time=TS,
        entry_price=100.0,
        exit_time=TS + timedelta(minutes=5),
        exit_price=102.0 if pnl >= 0 else 98.0,
        stop_price=99.0,
        target_price=102.0,
        exit_type=PaperExitType.TARGET if pnl >= 0 else PaperExitType.STOP_LOSS,
        gross_pnl=pnl,
        fees=0.0,
        net_pnl=pnl,
        reward_risk_planned=2.0,
        reward_risk_realized=2.0 if pnl >= 0 else -2.0,
        maximum_favourable_excursion=max(pnl, 0.0),
        maximum_adverse_excursion=max(-pnl, 0.0),
        holding_seconds=300,
        strategy_setup="test",
        strategy_confidence="high",
        strategy_reasoning=("deterministic",),
        trading_date=TS.date(),
    )


def test_configuration_defaults_validation_and_disabled_paths_do_not_open(tmp_path):
    missing = tmp_path / "missing.jsonl"
    disabled = BacktestConfiguration(session_paths=(missing,), output_directory=tmp_path / "reports")
    assert disabled.enabled is False
    assert disabled.mode is BacktestMode.SINGLE_SESSION
    assert disabled.session_paths == (missing.resolve(strict=False),)
    with pytest.raises(ValueError, match="requires at least one"):
        BacktestConfiguration(enabled=True, output_directory=tmp_path / "reports")
    with pytest.raises(ValueError, match="exactly one"):
        BacktestConfiguration(enabled=True, mode=BacktestMode.SINGLE_SESSION, session_paths=(tmp_path / "a", tmp_path / "b"), output_directory=tmp_path / "reports")
    with pytest.raises(ValueError, match="max_sessions"):
        BacktestConfiguration(enabled=True, mode=BacktestMode.BATCH, session_paths=(tmp_path / "a", tmp_path / "b"), max_sessions=1, output_directory=tmp_path / "reports")
    with pytest.raises(ValueError, match="duplicates"):
        BacktestConfiguration(enabled=True, session_paths=(tmp_path / "a", tmp_path / "a"), output_directory=tmp_path / "reports")
    with pytest.raises(ValueError, match="positive"):
        BacktestConfiguration(max_findings=0)
    with pytest.raises(ValueError, match="ANALYSIS_ONLY"):
        BacktestConfiguration(safety_mode=ExecutionSafetyMode.DRY_RUN)
    with pytest.raises(ValueError, match="DRY_RUN"):
        BacktestConfiguration(broker_mode=BrokerExecutionMode.CLIENT)
    source = tmp_path / "source.jsonl"
    with pytest.raises(ValueError, match="overlap"):
        BacktestConfiguration(enabled=True, session_paths=(source,), output_directory=tmp_path)


def test_environment_configuration_and_sanitized_errors(tmp_path):
    path = write_session(tmp_path)
    settings = load_desktop_live_configuration(backtest_env(path, BACKTEST_REPRODUCIBILITY_CHECK="true"))
    assert settings.backtest_configuration.enabled is True
    assert settings.backtest_configuration.session_paths == (path.resolve(strict=False),)
    assert settings.backtest_configuration.reproducibility_check_enabled is True
    with pytest.raises(DesktopLiveDataConfigurationError, match="BACKTEST_MODE"):
        load_desktop_live_configuration(backtest_env(path, BACKTEST_MODE="GRID"))
    with pytest.raises(DesktopLiveDataConfigurationError, match="LIVE_MARKET_DATA_AUTO_CONNECT"):
        load_desktop_live_configuration(live_env(BACKTEST_ENABLED="true", BACKTEST_SESSION_PATHS=str(path)))


def test_lifecycle_bounded_processing_pause_resume_stop_completion_once_and_report(tmp_path):
    path = write_session(tmp_path)
    app = orchestrator(tmp_path, path)
    engine = app.deterministic_backtest_engine
    completed = []
    app._event_bus.subscribe(BACKTEST_COMPLETED, lambda payload: completed.append(payload.outcome))
    assert engine.prepare().lifecycle_state is BacktestLifecycleState.READY
    with pytest.raises(BacktestLifecycleError):
        engine.prepare()
    started = engine.start()
    assert started.lifecycle_state is BacktestLifecycleState.RUNNING
    assert engine.process_next().current_progress.current_record_index == 0
    assert engine.process_next().current_progress.current_record_index == 1
    assert engine.pause().lifecycle_state is BacktestLifecycleState.PAUSED
    assert engine.process_next().lifecycle_state is BacktestLifecycleState.PAUSED
    assert engine.resume().lifecycle_state is BacktestLifecycleState.RUNNING
    while engine.snapshot().lifecycle_state is BacktestLifecycleState.RUNNING:
        engine.process_batch()
    snapshot = engine.snapshot()
    assert snapshot.lifecycle_state is BacktestLifecycleState.COMPLETED
    assert snapshot.latest_result is not None
    assert snapshot.latest_result.report_path.exists()
    assert engine.repository.writes == 1
    assert completed == [BacktestOutcome.PASSED]
    assert engine.process_next().latest_result.report_path == snapshot.latest_result.report_path
    assert engine.repository.writes == 1


def test_replay_integration_routes_records_through_application_and_preserves_order(tmp_path):
    path = write_session(tmp_path)
    app = orchestrator(tmp_path, path)
    observed = []
    app._event_bus.subscribe(NEW_TICK, lambda payload: observed.append(payload.last_price))
    engine = app.deterministic_backtest_engine
    engine.start()
    engine.process_next()
    engine.process_batch(3)
    assert observed[::2] == [100.0, 100.0, 100.0]
    runtime = app.get_runtime(RuntimeInstrument.NIFTY).snapshot()
    assert runtime.latest_tick.last_price == 100.0
    assert app.snapshot().historical_replay.counters.broker_order_calls == 0


def test_batch_sessions_are_sequential_bounded_and_aggregate_analytics(tmp_path):
    first = write_session(tmp_path, "first.jsonl")
    second = write_session(tmp_path, "second.jsonl", rows=(tick_record(1),), header=manifest(1, session_id="second"))
    app = orchestrator(tmp_path, first, second)

    def record_on_first_tick(payload):
        if payload.last_price == 100.0:
            app._event_bus.publish(PAPER_TRADE_RECORDED, trade(f"trade-{len(app.performance_analytics_engine.records())}", 100.0))

    app._event_bus.subscribe(NEW_TICK, record_on_first_tick)
    engine = app.deterministic_backtest_engine
    engine.start()
    while engine.snapshot().lifecycle_state is BacktestLifecycleState.RUNNING:
        engine.process_batch()
    result = engine.snapshot().latest_result
    assert [item.session_identity for item in result.session_results] == ["first", "second"]
    assert result.total_sessions == 2
    assert result.aggregate_analytics.trade_count >= 1
    assert result.aggregate_analytics.net_pnl >= 100.0
    assert result.aggregate_analytics.win_rate == 100.0


def test_state_isolation_equivalent_runs_fingerprints_and_digests_match(tmp_path):
    path = write_session(tmp_path)
    app = orchestrator(tmp_path, path, reproducibility_check_enabled=True)
    engine = app.deterministic_backtest_engine

    def run_once():
        engine.reset()
        engine.start()
        while engine.snapshot().lifecycle_state is BacktestLifecycleState.RUNNING:
            engine.process_batch()
        result = engine.snapshot().latest_result
        return result.deterministic_run_fingerprint, result.result_digest, result.session_results[0].trades_closed

    assert run_once() == run_once()
    assert engine.snapshot().reproducibility_status is ReproducibilityStatus.MATCH
    changed = write_session(tmp_path, "changed.jsonl", rows=(tick_record(1, price=101.0),), header=manifest(1, session_id="changed"))
    other = orchestrator(tmp_path, changed).deterministic_backtest_engine
    other.start()
    while other.snapshot().lifecycle_state is BacktestLifecycleState.RUNNING:
        other.process_batch()
    assert other.snapshot().deterministic_run_fingerprint != engine.snapshot().deterministic_run_fingerprint


def test_live_exclusion_and_live_autoconnect_block_without_mutation(tmp_path):
    path = write_session(tmp_path)
    app = orchestrator(tmp_path, path)
    engine = app.deterministic_backtest_engine
    engine.set_live_market_data_active(lambda: True)
    with pytest.raises(BacktestLifecycleError, match="live runtime"):
        engine.prepare()
    assert engine.snapshot().lifecycle_state is BacktestLifecycleState.IDLE
    assert app.historical_replay_engine.snapshot().published_records == 0

    engine.set_live_market_data_active(lambda: False)
    engine.start()
    assert _backtest_is_active(ApplicationLifecycleManager(app)) is True
    settings = load_desktop_live_configuration(live_env())
    session = create_zerodha_session_manager(settings, auth_client_factory=auth_factory, clock=lambda: TS)
    ticker = FakeTickerClient()
    with pytest.raises(DesktopLiveDataConfigurationError, match="backtest is active"):
        create_desktop_live_runtime(
            lifecycle=ApplicationLifecycleManager(app),
            settings=settings,
            session_manager=session,
            runtime_factory=LiveMarketDataRuntimeFactory(clock=lambda: TS),
            ticker_client=ticker,
        )
    assert ticker.connect_calls == 0
    assert ticker.close_calls == 0


def test_malformed_source_failure_stop_policy_and_reset(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{bad", encoding="utf-8")
    app = orchestrator(tmp_path, bad)
    engine = app.deterministic_backtest_engine
    engine.start()
    engine.process_next()
    assert engine.snapshot().lifecycle_state is BacktestLifecycleState.FAILED
    assert engine.snapshot().latest_result.outcome is BacktestOutcome.FAILED
    assert engine.repository.writes == 1
    assert engine.reset().lifecycle_state is BacktestLifecycleState.IDLE


def test_dashboard_projection_driver_controls_and_disabled_adds_no_work(tmp_path):
    path = write_session(tmp_path)
    dashboard = create_dashboard_application(environ=backtest_env(path))
    engine = dashboard.lifecycle.orchestrator.deterministic_backtest_engine
    assert dashboard.deterministic_backtest_driver is not None
    view = dashboard.main_window.refresh()
    assert view.backtest.enabled is True
    assert view.backtest.lifecycle_state == "Idle"
    engine.start()
    before = dashboard.deterministic_backtest_driver.poll_count
    dashboard.main_window.refresh()
    assert dashboard.deterministic_backtest_driver.poll_count == before + 1
    while engine.snapshot().lifecycle_state is BacktestLifecycleState.RUNNING:
        dashboard.main_window.refresh()
    final = dashboard.main_window.refresh()
    assert final.backtest.final_outcome in {"Completed With Findings", "Passed"}
    terminal_polls = dashboard.deterministic_backtest_driver.poll_count
    dashboard.main_window.refresh()
    assert dashboard.deterministic_backtest_driver.poll_count == terminal_polls
    dashboard.shutdown()

    disabled = create_dashboard_application(environ={"LIVE_MARKET_DATA_ENABLED": "false"})
    assert disabled.deterministic_backtest_driver is None
    disabled.shutdown()


def test_models_immutable_persistence_schema_and_broker_safety_search(tmp_path):
    path = write_session(tmp_path)
    app = orchestrator(tmp_path, path)
    engine = app.deterministic_backtest_engine
    snap = engine.snapshot()
    with pytest.raises(FrozenInstanceError):
        snap.run_id = "changed"
    engine.start()
    while engine.snapshot().lifecycle_state is BacktestLifecycleState.RUNNING:
        engine.process_batch()
    report_path = engine.snapshot().latest_result.report_path
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("engines/deterministic_backtest").glob("*.py"))
    assert "place_order" not in text
    assert "modify_order" not in text
    assert "cancel_order" not in text
    assert "threading" not in text
    assert "asyncio" not in text
    assert "time.sleep" not in text
    assert "EventBus(" not in text
    assert app.snapshot().deterministic_backtest.broker_order_calls == 0
