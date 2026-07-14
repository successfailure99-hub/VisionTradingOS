import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "application" / "trade_lifecycle_v1"
APPROVED = {
    PACKAGE / "__init__.py",
    PACKAGE / "enums.py",
    PACKAGE / "models.py",
    PACKAGE / "configuration.py",
    PACKAGE / "coordinator.py",
    PACKAGE / "factory.py",
}
FORBIDDEN_IMPORTS = {
    "kiteconnect",
    "requests",
    "httpx",
    "urllib",
    "websocket",
    "websockets",
    "selenium",
    "playwright",
    "pyotp",
    "asyncio",
    "multiprocessing",
    "queue",
    "sqlite3",
    "PySide6",
    "openai",
    "transformers",
    "torch",
    "tensorflow",
    "langchain",
}
FORBIDDEN_CALLS = {
    "place_order",
    "submit_order",
    "modify_order",
    "cancel_order",
    "connect",
    "disconnect",
    "authenticate",
    "fetch_margin",
    "get_margin",
    "process_raw_ticks",
    "calculate",
    "calculate_position_size",
    "open",
    "write_text",
    "write_bytes",
    "getenv",
    "sleep",
    "Thread",
    "create_task",
}


def test_only_approved_files_no_forbidden_imports_calls_or_private_dependency_access():
    assert set(PACKAGE.glob("*.py")) == APPROVED
    violations = []
    for path in APPROVED:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name.split(".")[0] for alias in getattr(node, "names", [])]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module.split(".")[0])
                for name in names:
                    if name in FORBIDDEN_IMPORTS:
                        violations.append(f"{path}:{node.lineno}: import {name}")
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                if name in FORBIDDEN_CALLS:
                    violations.append(f"{path}:{node.lineno}: call {name}")
            if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not (node.attr.startswith("__") and node.attr.endswith("__")):
                if not isinstance(node.value, ast.Name) or node.value.id != "self":
                    violations.append(f"{path}:{node.lineno}: private dependency access {node.attr}")
    assert violations == []


def test_architecture_text_has_no_broker_network_persistence_or_duplicate_calculation_terms():
    combined = "\n".join(path.read_text().lower() for path in APPROVED)
    for term in ("api_key", "access_token", "kite", "websocket", "database", "margin"):
        assert term not in combined
    assert "process(" in combined
    assert "riskmanagementv2input" in combined
    assert "positionpriceupdate" in combined
