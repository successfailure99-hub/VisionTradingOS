import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "application" / "execution_runtime_v1"
APPROVED = {
    PACKAGE / "__init__.py",
    PACKAGE / "enums.py",
    PACKAGE / "models.py",
    PACKAGE / "configuration.py",
    PACKAGE / "validator.py",
    PACKAGE / "simulator.py",
    PACKAGE / "runtime.py",
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
}
FORBIDDEN_CALLS = {
    "place_order",
    "submit_order",
    "modify_order",
    "cancel_order",
    "connect",
    "disconnect",
    "authenticate",
    "get_margin",
    "fetch_margin",
    "sleep",
    "Thread",
    "create_task",
    "open",
    "write_text",
    "write_bytes",
    "getenv",
}


def test_only_approved_files_and_no_live_dependencies():
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
    assert violations == []


def test_architecture_text_has_no_credentials_live_order_or_persistence():
    combined = "\n".join(path.read_text().lower() for path in APPROVED)

    for term in ("credential", "access_token", "totp", "database", "sqlite", "websocket"):
        assert term not in combined
    assert "brokerexecutionmode.dry_run" in combined
    assert "executionsafetymode.analysis_only" in combined
    assert "approved_quantity" in combined
    assert "riskmanagementv2snapshot" in combined
