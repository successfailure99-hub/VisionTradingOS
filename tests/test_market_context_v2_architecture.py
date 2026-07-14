import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "engines" / "market_context_v2"


def _root_name(node):
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def test_no_forbidden_imports_calls_or_private_dependency_access():
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
        "kiteconnect",
        "brokers",
        "dashboard",
        "application",
    }
    forbidden_calls = {
        "Thread",
        "start_new_thread",
        "create_task",
        "run_until_complete",
        "sleep",
        "open",
        "write_text",
        "write_bytes",
        "getenv",
        "connect",
        "disconnect",
        "subscribe",
        "unsubscribe",
        "authenticate",
        "process_raw_ticks",
        "set_underlying_price",
        "place_order",
        "submit_order",
        "create_order",
        "run_strategy",
        "run_risk",
    }
    violations = []
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_imports
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_imports
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                assert name not in forbidden_calls
            if isinstance(node, ast.Attribute):
                attr = node.attr
                if attr.startswith("__") and attr.endswith("__"):
                    continue
                if attr.startswith("_") and _root_name(node) != "self":
                    violations.append(f"{path}:{node.lineno} {attr}")
    assert violations == []


def test_existing_v1_packages_remain_present_and_v2_is_separate():
    assert (ROOT / "engines" / "market_context").exists()
    assert (ROOT / "engines" / "price_action").exists()
    assert (ROOT / "engines" / "option_chain_analytics").exists()
    assert (ROOT / "engines" / "cpr").exists()
    assert (ROOT / "engines" / "camarilla").exists()
    assert (ROOT / "engines" / "vwap").exists()
    assert PACKAGE.exists()
