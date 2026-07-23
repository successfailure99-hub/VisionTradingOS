import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "engines" / "risk_management_v2"
APPROVED_FILES = {
    PACKAGE / "__init__.py",
    PACKAGE / "enums.py",
    PACKAGE / "models.py",
    PACKAGE / "configuration.py",
    PACKAGE / "validator.py",
    PACKAGE / "sizing.py",
    PACKAGE / "calculator.py",
    PACKAGE / "engine.py",
}
FORBIDDEN_IMPORTS = {
    "asyncio",
    "multiprocessing",
    "queue",
    "sqlite3",
    "PySide6",
    "requests",
    "httpx",
    "urllib",
    "selenium",
    "playwright",
    "pyotp",
    "websocket",
    "websockets",
    "kiteconnect",
    "openai",
    "transformers",
    "torch",
    "tensorflow",
    "langchain",
}
FORBIDDEN_CALLS = {
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
    "place_order",
    "submit_order",
    "create_order",
    "modify_order",
    "cancel_order",
    "send_order",
    "fetch_margin",
    "get_margin",
}


def parse(path):
    return ast.parse(path.read_text(), filename=str(path))


def test_only_approved_package_files_exist_and_v1_strategy_unchanged():
    assert set(PACKAGE.glob("*.py")) == APPROVED_FILES
    assert (ROOT / "engines" / "risk").exists()
    assert (ROOT / "engines" / "strategy_decision_v2").exists()


def test_no_forbidden_imports_calls_or_private_dependency_access():
    violations = []
    for path in APPROVED_FILES:
        tree = parse(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name.split(".")[0] for alias in getattr(node, "names", [])]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module.split(".")[0])
                for name in names:
                    if name in FORBIDDEN_IMPORTS:
                        violations.append(f"{path}:{node.lineno}: forbidden import {name}")
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name in FORBIDDEN_CALLS:
                    violations.append(f"{path}:{node.lineno}: forbidden call {name}")
            if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not (node.attr.startswith("__") and node.attr.endswith("__")):
                if not isinstance(node.value, ast.Name) or node.value.id != "self":
                    violations.append(f"{path}:{node.lineno}: private dependency access {node.attr}")
    assert violations == []


def test_architecture_text_rejects_broker_order_margin_and_unsafe_sizing_terms():
    combined = "\n".join(path.read_text().lower() for path in APPROVED_FILES)

    for term in ("kite", "margin", "dashboard", "martingale", "averaging down", "revenge"):
        assert term not in combined
    assert "submit_order" not in combined
    assert "place_order" not in combined
    assert "direction =" not in (PACKAGE / "calculator.py").read_text().lower()
    assert "floor(" in (PACKAGE / "sizing.py").read_text()


def test_risk_management_v2_consumes_strategy_decision_only_not_market_context_or_raw_indicators():
    combined = "\n".join(path.read_text() for path in APPROVED_FILES)

    assert "StrategyDecisionV2Snapshot" in combined
    for term in (
        "MarketContextV2",
        "market_context_v2",
        "AIReasoningV2Input",
        "Camarilla",
        "CPRLevels",
        "VWAP",
        "camarilla",
        "cpr",
        "vwap",
    ):
        assert term not in combined
