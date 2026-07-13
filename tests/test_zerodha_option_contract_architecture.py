import ast
from pathlib import Path

from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


PACKAGE = Path("brokers/zerodha/options")
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
    "subscribe",
    "unsubscribe",
    "process_tick",
    "process_option_chain",
    "place_order",
    "submit_order",
    "create_order",
}


def trees():
    for path in PACKAGE.glob("*.py"):
        yield path, ast.parse(path.read_text())


def test_architecture_has_no_forbidden_imports_calls_or_side_effect_boundaries():
    assert not hasattr(Exchange, "NFO")
    assert not hasattr(Exchange, "BFO")
    assert Instrument.NIFTY.value == "NIFTY"
    for path, tree in trees():
        imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        assert not (imports & FORBIDDEN_IMPORTS), path
        imported_text = path.read_text()
        assert "dashboard" not in imported_text
        assert "engines.option_chain" not in imported_text
        assert "OptionChain" not in imported_text
        assert "last_price" not in imported_text
        assert "implied" not in imported_text.lower()
        assert "delta" not in imported_text.lower()
        assert "NFO = " not in Path("core/enums/exchange.py").read_text()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                assert name not in FORBIDDEN_CALLS, f"{path}: {name}"
