import ast
from pathlib import Path

PACKAGE = Path("engines/production_safety_v1")


def test_production_safety_v1_has_no_forbidden_imports_or_calls():
    forbidden_imports = {"kiteconnect", "requests", "httpx", "urllib", "websocket", "websockets", "pyotp", "PySide6", "sqlite3", "sqlalchemy", "pandas", "numpy", "asyncio", "multiprocessing", "queue", "openai", "transformers", "torch", "tensorflow"}
    forbidden_calls = {"place_order", "submit_order", "modify_order", "cancel_order", "connect", "disconnect", "authenticate", "fetch_margin", "get_margin", "open", "write_text", "write_bytes", "sleep", "Thread", "create_task", "getenv"}
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert forbidden_imports.isdisjoint({alias.name.split(".")[0] for alias in node.names})
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_imports
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                assert name not in forbidden_calls, f"{path}:{node.lineno}"
