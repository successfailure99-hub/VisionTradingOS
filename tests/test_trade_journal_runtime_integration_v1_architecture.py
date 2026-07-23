import ast
from pathlib import Path

PACKAGE = Path("application/trade_journal_runtime_integration_v1")


def test_trade_journal_runtime_integration_has_no_forbidden_imports():
    forbidden = {"sqlite3", "sqlalchemy", "pandas", "numpy", "requests", "httpx", "urllib", "kiteconnect", "websocket", "websockets", "pyotp", "PySide6", "asyncio", "multiprocessing", "queue", "openai", "transformers", "torch", "tensorflow"}
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert forbidden.isdisjoint({alias.name.split(".")[0] for alias in node.names})
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden


def test_integration_does_not_call_builder_registry_or_analytics_directly():
    source = (PACKAGE / "integration.py").read_text()
    tree = ast.parse(source)
    forbidden_attrs = {"build", "add", "calculate"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_attrs, node.func.attr


def test_trade_journal_runtime_integration_has_no_legacy_intelligence_contract_dependency():
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
