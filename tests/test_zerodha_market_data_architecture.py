"""
Architecture checks for Zerodha market-data WebSocket V1.
"""

import ast
from dataclasses import fields
from pathlib import Path

from brokers.zerodha.market_data import ZerodhaWebSocketSnapshot


PRODUCTION_ROOT = Path("brokers/zerodha/market_data")


def source_files():
    return sorted(PRODUCTION_ROOT.glob("*.py"))


def parse(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def test_production_rejects_forbidden_imports():
    forbidden = {
        "asyncio",
        "multiprocessing",
        "queue",
        "requests",
        "selenium",
        "playwright",
        "pyotp",
        "sqlite3",
        "PySide6",
        "websocket",
        "websockets",
    }
    imports = set()
    for path in source_files():
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])

    assert imports.isdisjoint(forbidden)
    assert "dashboard" not in imports
    assert "application" not in imports


def test_production_rejects_forbidden_calls():
    forbidden = {
        "Thread",
        "start_new_thread",
        "create_task",
        "run_until_complete",
        "sleep",
        "place_order",
        "submit_order",
        "login",
        "generate_session",
        "open",
        "write_text",
        "write_bytes",
    }
    calls = set()
    for path in source_files():
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)

    assert calls.isdisjoint(forbidden)


def test_no_forbidden_project_imports_in_production_package():
    modules = set()
    for path in source_files():
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)

    assert not any(module.startswith("dashboard") for module in modules)
    assert not any(module.startswith("application") for module in modules)
    assert not any(module.startswith("engines") for module in modules)
    assert not any("order_management" in module for module in modules)


def test_websocket_snapshot_exposes_no_secrets_or_raw_payloads():
    names = {field.name for field in fields(ZerodhaWebSocketSnapshot)}

    assert "api_key" not in names
    assert "access_token" not in names
    assert "raw_tick" not in names
    assert "client" not in names
