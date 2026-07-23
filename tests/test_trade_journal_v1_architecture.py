import ast
from pathlib import Path

PACKAGE = Path("engines/trade_journal_v1")


def test_trade_journal_v1_has_no_network_persistence_or_broker_imports():
    forbidden = {
        "sqlite3",
        "sqlalchemy",
        "pandas",
        "numpy",
        "requests",
        "httpx",
        "urllib",
        "kiteconnect",
        "websocket",
        "websockets",
        "pyotp",
        "PySide6",
        "asyncio",
        "multiprocessing",
        "queue",
        "openai",
        "transformers",
        "torch",
        "tensorflow",
    }
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert forbidden.isdisjoint({alias.name.split(".")[0] for alias in node.names})
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden


def test_trade_journal_v1_does_not_call_live_or_persistence_functions():
    forbidden_calls = {
        "open",
        "write_text",
        "write_bytes",
        "place_order",
        "submit_order",
        "modify_order",
        "cancel_order",
        "connect",
        "disconnect",
        "authenticate",
        "sleep",
        "Thread",
        "create_task",
        "getenv",
    }
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                name = function.id if isinstance(function, ast.Name) else getattr(function, "attr", "")
                assert name not in forbidden_calls, f"{path}:{node.lineno}"


def test_trade_journal_v1_has_no_legacy_intelligence_contract_dependency():
    forbidden_text = {
        "MarketContextV2",
        "market_context_v2",
        "AIReasoningV2Input",
        "StrategyDecisionV2Input",
        "RiskManagementV2Input",
        "engines.ai_reasoning_v2",
        "engines.market_context_v2",
        "engines.market_state",
        "MultiTimeframeEvidenceSnapshot",
        "MarketStateSnapshot",
        "ChartExplanationSnapshot",
        "Fusion",
        "ChartExplanation",
    }
    for path in PACKAGE.glob("*.py"):
        source = path.read_text()
        assert not any(token in source for token in forbidden_text), path
