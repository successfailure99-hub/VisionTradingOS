import ast
from pathlib import Path

PACKAGE = Path("application/trade_lifecycle_runtime_integration_v1")


def _sources():
    return tuple(PACKAGE.glob("*.py"))


def test_integration_package_does_not_call_strategy_ai_risk_or_broker_directly():
    forbidden_names = {
        "AIReasoningV2Engine",
        "StrategyDecisionV2Engine",
        "RiskManagementV2Engine",
        "ZerodhaBrokerAdapter",
    }
    for path in _sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in forbidden_names, f"{path}:{node.lineno}"


def test_integration_package_uses_public_coordinator_contract_only():
    allowed_private_roots = {"self"}
    for path in _sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr.startswith("__") and node.attr.endswith("__"):
                continue
            if not node.attr.startswith("_"):
                continue
            root = node.value
            if isinstance(root, ast.Name) and root.id in allowed_private_roots:
                continue
            assert False, f"{path}:{node.lineno} private dependency access .{node.attr}"


def test_no_network_threads_asyncio_or_persistence_imports_are_introduced():
    forbidden_imports = {"asyncio", "socket", "websocket", "sqlite3", "requests"}
    for path in _sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
                assert forbidden_imports.isdisjoint(imported), f"{path}:{node.lineno}"
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root not in forbidden_imports, f"{path}:{node.lineno}"
