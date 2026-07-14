import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "engines" / "option_chain_analytics"


def test_architecture_has_no_forbidden_imports_or_calls():
    forbidden_imports = {"asyncio", "multiprocessing", "queue", "sqlite3", "PySide6", "requests", "selenium", "playwright", "pyotp", "websocket", "websockets", "kiteconnect"}
    forbidden_calls = {"Thread", "start_new_thread", "create_task", "run_until_complete", "sleep", "open", "write_text", "write_bytes", "getenv", "connect", "disconnect", "subscribe", "unsubscribe", "authenticate", "process_raw_ticks", "set_underlying_price", "run_strategy", "run_risk", "place_order", "submit_order", "create_order"}
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


def test_runtime_relative_oi_wording_and_no_runtime_ownership():
    text = "\n".join(path.read_text() for path in PACKAGE.glob("*.py"))
    assert "runtime_change_open_interest" in text
    assert "previous-close" not in text.lower()
    assert "official day-change" not in text.lower()
    assert "LiveOptionChainRuntime(" not in text
    assert "OptionChainCalculator.calculate" not in text
