"""
Integration tests for Application Bootstrap startup flow.
"""

import ast
from datetime import datetime
from pathlib import Path

from application import ApplicationBootstrap, RuntimeStatus
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.models.tick import Tick


TS = datetime(2026, 7, 12, 9, 15)


def tick():
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=TS,
        last_price=100.0,
        volume=10,
        bid_price=99.5,
        ask_price=100.5,
        open_interest=100,
    )


def test_complete_application_startup_reset_stop_and_restart_flow():
    manager = ApplicationBootstrap().create_application()
    orchestrator = manager.orchestrator
    runtimes = manager.orchestrator.runtimes

    assert manager.status is RuntimeStatus.CREATED
    assert orchestrator.status is RuntimeStatus.CREATED

    manager.start()
    assert manager.status is RuntimeStatus.RUNNING
    assert orchestrator.status is RuntimeStatus.RUNNING
    assert all(runtime.status is RuntimeStatus.RUNNING for runtime in runtimes)

    runtime_snapshot = orchestrator.process_tick(tick())
    assert runtime_snapshot.symbol.value == "NIFTY"
    assert runtime_snapshot.latest_tick.last_price == 100.0
    assert runtime_snapshot.vwap is not None

    reset_snapshot = manager.reset()
    assert reset_snapshot.status is RuntimeStatus.RUNNING
    assert manager.orchestrator is orchestrator
    assert manager.orchestrator.runtimes == runtimes
    assert manager.orchestrator.snapshot().runtime_snapshots[0].latest_tick is None

    manager.stop()
    assert manager.status is RuntimeStatus.STOPPED
    assert all(runtime.status is RuntimeStatus.STOPPED for runtime in runtimes)

    manager.start()
    assert manager.status is RuntimeStatus.RUNNING
    assert manager.orchestrator is orchestrator
    assert manager.orchestrator.runtimes == runtimes

    manager.stop()
    assert manager.status is RuntimeStatus.STOPPED


def test_default_broker_remains_dry_run_without_credentials():
    manager = ApplicationBootstrap().create_application()
    assert manager.orchestrator.broker_adapter.mode is BrokerExecutionMode.DRY_RUN


def test_main_import_does_not_start_application():
    import main

    assert callable(main.main)


def test_no_forbidden_runtime_capabilities_added():
    paths = (
        Path("application/bootstrap.py"),
        Path("application/lifecycle_manager.py"),
        Path("main.py"),
    )
    forbidden_import_roots = {
        "asyncio",
        "kiteconnect",
        "requests",
        "sqlite3",
        "websocket",
        "websockets",
        "PySide6",
        "pyttsx3",
    }
    forbidden_call_names = {
        "connect",
        "create_task",
        "login",
        "run",
        "run_until_complete",
        "start_new_thread",
        "Thread",
        "WebSocketApp",
    }
    forbidden_attributes = {"_state", "_data", "_orders", "access_token"}

    imported_roots = set()
    called_names = set()
    accessed_attributes = set()

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called_names.add(node.func.attr)
            elif isinstance(node, ast.Attribute):
                accessed_attributes.add(node.attr)

    assert imported_roots.isdisjoint(forbidden_import_roots)
    assert called_names.isdisjoint(forbidden_call_names)
    assert accessed_attributes.isdisjoint(forbidden_attributes)
