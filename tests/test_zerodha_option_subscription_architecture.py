import ast
from pathlib import Path


PACKAGE = Path("brokers/zerodha/option_market_data")
FORBIDDEN_IMPORTS = {"asyncio", "multiprocessing", "queue", "sqlite3", "PySide6", "requests", "selenium", "playwright", "pyotp", "websocket", "websockets"}
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
    "set_callbacks",
    "process_tick",
    "process_raw_ticks",
    "process_option_chain",
    "place_order",
    "submit_order",
    "create_order",
}


def trees():
    for path in PACKAGE.glob("*.py"):
        yield path, ast.parse(path.read_text())


def test_option_subscription_architecture_boundaries():
    assert Path("brokers/zerodha/market_data/subscription_registry.py").exists()
    assert Path("brokers/zerodha/market_data/websocket_manager.py").exists()
    assert Path("brokers/zerodha/market_data/normalizer.py").exists()
    for path, tree in trees():
        text = path.read_text()
        imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        assert not (imports & FORBIDDEN_IMPORTS), path
        assert "application" not in text
        assert "dashboard" not in text
        assert "engines" not in text
        assert "OptionChain" not in text
        assert "last_price" not in text
        assert "open_interest" not in text
        assert "KiteTickerClient(" not in text
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                assert name not in FORBIDDEN_CALLS, f"{path}: {name}"
