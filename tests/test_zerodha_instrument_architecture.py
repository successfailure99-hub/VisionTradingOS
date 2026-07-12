"""
Architecture checks for Zerodha instrument discovery.
"""

import ast
from pathlib import Path


PACKAGE = Path("brokers/zerodha/instruments")
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
    "process_tick",
    "place_order",
    "submit_order",
}


def production_trees():
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in PACKAGE.rglob("*.py")]


def test_no_forbidden_imports_threads_persistence_or_runtime_calls():
    imports = set()
    calls = set()
    for _, tree in production_trees():
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


def test_no_dashboard_engine_order_websocket_runtime_or_auth_construction_imports():
    forbidden_text = (
        "dashboard",
        "engines.",
        "order_management",
        "ZerodhaWebSocketManager",
        "LiveMarketDataRuntime(",
        "ZerodhaSessionManager",
        "os.environ",
        "fuzzy",
    )
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert all(value not in text for value in forbidden_text)


def test_no_private_auth_client_state_or_raw_mapping_retained_and_core_enums_unchanged():
    private_attrs = {"_session", "_access_token", "_api_secret"}
    for _, tree in production_trees():
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert attrs.isdisjoint(private_attrs)
    model_text = (PACKAGE / "models.py").read_text(encoding="utf-8")
    assert "raw_record" not in model_text
    assert "raw_mapping" not in model_text
    assert "class Instrument" in Path("core/enums/instrument.py").read_text(encoding="utf-8")
    assert "class Exchange" in Path("core/enums/exchange.py").read_text(encoding="utf-8")
