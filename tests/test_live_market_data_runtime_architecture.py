"""
Architecture checks for live market-data runtime integration.
"""

import ast
from dataclasses import fields
from pathlib import Path

from application.live_market_data import LiveMarketDataRuntimeSnapshot


ROOT = Path("application/live_market_data")


def source_files():
    return sorted(ROOT.glob("*.py"))


def parse(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def test_forbidden_imports_and_calls_absent():
    forbidden_imports = {
        "asyncio",
        "multiprocessing",
        "queue",
        "sqlite3",
        "PySide6",
        "requests",
        "selenium",
        "playwright",
        "pyotp",
        "websocket",
        "websockets",
    }
    forbidden_calls = {
        "Thread",
        "start_new_thread",
        "create_task",
        "run_until_complete",
        "sleep",
        "place_order",
        "submit_order",
        "authenticate",
        "restore_session",
        "create_login_request",
        "login",
        "open",
        "write_text",
        "write_bytes",
        "getenv",
        "environ",
    }
    imports = set()
    calls = set()
    modules = set()
    for path in source_files():
        tree = parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
                modules.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)

    assert imports.isdisjoint(forbidden_imports)
    assert calls.isdisjoint(forbidden_calls)
    assert not any(module.startswith("dashboard") for module in modules)
    assert not any(module.startswith("engines") for module in modules)
    assert not any("order_management" in module for module in modules)


def test_snapshot_has_no_secret_fields():
    names = {field.name for field in fields(LiveMarketDataRuntimeSnapshot)}

    assert "api_key" not in names
    assert "access_token" not in names
    assert "api_secret" not in names
    assert "session" not in names
