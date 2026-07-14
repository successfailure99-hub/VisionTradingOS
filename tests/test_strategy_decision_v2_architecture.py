import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "engines" / "strategy_decision_v2"


def _root_name(node):
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def test_architecture_guardrails():
    forbidden_imports = {
        "asyncio", "multiprocessing", "queue", "sqlite3", "PySide6", "requests", "httpx", "urllib",
        "selenium", "playwright", "pyotp", "websocket", "websockets", "kiteconnect", "openai",
        "transformers", "torch", "tensorflow", "langchain", "brokers", "dashboard", "application",
    }
    forbidden_calls = {
        "Thread", "start_new_thread", "create_task", "run_until_complete", "sleep", "open",
        "write_text", "write_bytes", "getenv", "connect", "disconnect", "subscribe", "unsubscribe",
        "authenticate", "process_raw_ticks", "set_underlying_price", "place_order", "submit_order",
        "create_order", "modify_order", "cancel_order", "calculate_position_size", "approve_risk",
        "run_risk", "send_order",
    }
    violations = []
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] not in forbidden_imports for alias in node.names)
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


def test_v1_and_upstream_v2_packages_remain_separate():
    assert (ROOT / "engines" / "strategy").exists()
    assert (ROOT / "engines" / "ai_reasoning_v2").exists()
    assert (ROOT / "engines" / "market_context_v2").exists()
    assert PACKAGE.exists()
