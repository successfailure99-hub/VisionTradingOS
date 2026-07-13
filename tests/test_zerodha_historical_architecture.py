"""
Architecture checks for Zerodha historical data package.
"""

import ast
from pathlib import Path


PACKAGE = Path("brokers/zerodha/historical")
FORBIDDEN_IMPORTS = {"asyncio", "multiprocessing", "queue", "sqlite3", "PySide6", "requests", "selenium", "playwright", "pyotp", "websocket", "websockets"}
FORBIDDEN_CALLS = {"Thread", "start_new_thread", "create_task", "run_until_complete", "sleep", "open", "write_text", "write_bytes", "getenv", "authenticate", "restore_session", "create_login_request", "connect", "disconnect", "subscribe", "unsubscribe", "process_tick", "place_order", "submit_order"}


def trees():
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in PACKAGE.rglob("*.py")]


def test_no_forbidden_imports_calls_or_runtime_ownership():
    imports = set()
    calls = set()
    for _, tree in trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
    assert imports.isdisjoint(FORBIDDEN_IMPORTS)
    assert calls.isdisjoint(FORBIDDEN_CALLS)


def test_no_dashboard_engine_application_auth_websocket_or_persistence_imports():
    forbidden = ("dashboard", "engines.", "application.", "ZerodhaSessionManager", "ZerodhaWebSocketManager", "order_management", "os.environ", "retry", "raw_payload")
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert all(item not in text for item in forbidden)
    assert "class Candle" in Path("core/models/candle.py").read_text(encoding="utf-8")
    assert "class TimeFrame" in Path("core/enums/timeframe.py").read_text(encoding="utf-8")
