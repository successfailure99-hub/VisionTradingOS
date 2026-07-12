"""
Tests for dashboard application owner.
"""

import ast
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from application import ApplicationBootstrap, RuntimeStatus
from dashboard.application import DashboardApplication


def app():
    return QApplication.instance() or QApplication([])


def test_uses_supplied_lifecycle_and_does_not_create_another_orchestrator():
    app()
    lifecycle = ApplicationBootstrap().create_application()
    orchestrator = lifecycle.orchestrator
    dashboard = DashboardApplication(lifecycle)
    assert dashboard.lifecycle is lifecycle
    assert dashboard.lifecycle.orchestrator is orchestrator


def test_shutdown_is_idempotent_and_stops_timer_and_lifecycle():
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    dashboard = DashboardApplication(lifecycle)
    dashboard.main_window.start_refresh()
    dashboard.shutdown()
    dashboard.shutdown()
    assert not dashboard.main_window._timer.isActive()
    assert lifecycle.status is RuntimeStatus.STOPPED


def test_does_not_double_start_running_lifecycle(monkeypatch):
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    start_count = lifecycle.snapshot().start_count
    dashboard = DashboardApplication(lifecycle)
    monkeypatch.setattr(dashboard._qt_app, "exec", lambda: 0)
    assert dashboard.run() == 0
    assert lifecycle.snapshot().start_count == start_count


def test_starts_lifecycle_when_required(monkeypatch):
    lifecycle = ApplicationBootstrap().create_application()
    dashboard = DashboardApplication(lifecycle)
    monkeypatch.setattr(dashboard._qt_app, "exec", lambda: 0)
    assert dashboard.run() == 0
    assert lifecycle.snapshot().start_count == 1


def test_creates_one_main_window():
    lifecycle = ApplicationBootstrap().create_application()
    dashboard = DashboardApplication(lifecycle)
    assert dashboard.main_window is dashboard.main_window


def test_importing_desktop_main_does_not_launch_gui():
    import desktop_main

    assert callable(desktop_main.main)


def test_no_live_broker_login_or_connectivity_is_added():
    paths = tuple(Path("dashboard").rglob("*.py")) + (Path("desktop_main.py"),)
    forbidden_import_roots = {"asyncio", "kiteconnect", "requests", "sqlite3", "websocket", "websockets", "pyttsx3"}
    forbidden_calls = {
        "login",
        "connect",
        "place",
        "submit_order",
        "process_tick",
        "create_task",
        "run_until_complete",
        "start_new_thread",
        "Thread",
    }
    allowed_attribute_calls = {"connect", "start", "exec", "run"}
    forbidden_private = {"_state", "_data", "_orders"}

    imported_roots = set()
    called_names = set()
    private_attrs = set()
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
                elif isinstance(node.func, ast.Attribute) and node.func.attr not in allowed_attribute_calls:
                    called_names.add(node.func.attr)
            elif isinstance(node, ast.Attribute):
                private_attrs.add(node.attr)

    assert imported_roots.isdisjoint(forbidden_import_roots)
    assert called_names.isdisjoint(forbidden_calls)
    assert private_attrs.isdisjoint(forbidden_private)
