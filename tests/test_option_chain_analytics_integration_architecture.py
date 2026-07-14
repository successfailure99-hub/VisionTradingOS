import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "application" / "option_chain_analytics_integration"
FORBIDDEN_PRIVATE_ATTRIBUTES = {
    "_history",
    "_source_snapshot",
    "_source_analysis",
    "_previous_distinct_snapshot",
    "_previous_distinct_analysis",
    "_live_option_chain_runtime",
    "_option_chain_engine",
    "_runtimes",
}


def _root_name(node: ast.AST) -> str | None:
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _attribute_chain(node: ast.Attribute) -> str:
    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    return ".".join(parts)


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


def test_no_private_state_or_runtime_ownership():
    violations: list[str] = []
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py")
    )

    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue

            attribute = node.attr
            if attribute.startswith("__") and attribute.endswith("__"):
                continue
            if not attribute.startswith("_"):
                continue

            root = _root_name(node)
            if root == "self":
                continue

            if attribute.startswith("_") or attribute in FORBIDDEN_PRIVATE_ATTRIBUTES:
                violations.append(
                    f"{path}:{getattr(node, 'lineno', '?')} "
                    f"private attribute access: {_attribute_chain(node)}"
                )

    assert violations == []
    assert "LiveOptionChainRuntime(" not in text
    assert "OptionChainAnalyticsEngine(" not in text
    assert "OptionChainCalculator" not in text
