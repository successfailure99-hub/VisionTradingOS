import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "application" / "live_option_chain_integration"


def test_integration_package_has_no_forbidden_imports_or_calls():
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
        "set_callbacks",
        "process_option_chain",
        "run_strategy",
        "run_risk",
        "place_order",
        "submit_order",
        "create_order",
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


def test_integration_does_not_rebuild_existing_owners_or_expose_raw_backend_state():
    text = "\n".join(path.read_text() for path in PACKAGE.glob("*.py"))
    assert "LiveOptionChainIntegrationCoordinator" in text
    assert "LiveOptionChainRuntime(" not in text
    assert "ZerodhaOptionMarketDataSubscriptionManager(" not in text
    assert "OptionChainEngine(" not in text
    assert "self._raw_ticks" not in text
    assert "api_key" not in text
    assert "_runtimes" not in text
