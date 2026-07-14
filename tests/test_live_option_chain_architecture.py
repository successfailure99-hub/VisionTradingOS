import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "application" / "live_option_chain"


def test_live_option_chain_architecture_has_no_forbidden_imports_or_calls():
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
        "set_callbacks",
        "place_order",
        "submit_order",
        "create_order",
        "run_strategy",
        "run_risk",
    }
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] not in forbidden_imports for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_imports
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                assert name not in forbidden_calls


def test_existing_engine_and_subscription_packages_are_not_modified_by_runtime():
    text = "\n".join(path.read_text() for path in PACKAGE.glob("*.py"))
    assert "runtime_change_open_interest" in text
    assert "core.models.tick" not in text
    assert "CandleEngine" not in text
    assert "VWAPEngine" not in text
    assert "OptionChainEngine" in text
    assert "OptionChainSnapshot" in text
