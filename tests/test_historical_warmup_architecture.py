"""
Architecture checks for historical warm-up.
"""

import ast
from pathlib import Path


PACKAGE = Path("application/historical_warmup")
FORBIDDEN_IMPORTS = {
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
    "kiteconnect",
}
FORBIDDEN_CALLS = {
    "Thread",
    "start_new_thread",
    "create_task",
    "run_until_complete",
    "sleep",
    "open",
    "write_text",
    "write_bytes",
    "getenv",
    "authenticate",
    "restore_session",
    "create_login_request",
    "connect",
    "disconnect",
    "subscribe",
    "unsubscribe",
    "place_order",
    "submit_order",
    "create_order",
    "run_strategy",
    "run_risk",
    "run_ai_reasoning",
}


def trees():
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in PACKAGE.rglob("*.py")]


def test_no_forbidden_imports_or_calls():
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


def test_no_dashboard_websocket_market_data_tick_vwap_or_private_history_access():
    forbidden = (
        "dashboard",
        "WebSocket",
        "MarketDataEngine",
        "process_tick",
        "from core.models.tick",
        "Tick(",
        "vwap_engine",
        "run_strategy",
        "run_risk",
        "create_order",
        "os.environ",
        "api_key",
        "access_token",
        "class Candle",
        "class DailyOHLC",
        "._history",
    )
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert all(item not in text for item in forbidden)
    assert "TimeFrame.ONE_MINUTE" in Path("application/historical_warmup/configuration.py").read_text(encoding="utf-8")
