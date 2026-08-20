from __future__ import annotations

from pathlib import Path
import subprocess

from application.enums import ExecutionSafetyMode
from application.models import RuntimeConfiguration
from engines.option_paper_execution.enums import OptionPaperExecutionStyle


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_AI_PATHS = (
    ROOT / "application" / "symbol_runtime.py",
    ROOT / "engines" / "ai_reasoning_v2",
    ROOT / "engines" / "strategy_decision_v2",
    ROOT / "engines" / "risk_management_v2",
    ROOT / "application" / "trade_lifecycle_v1",
    ROOT / "engines" / "trade_journal_v1",
)
FORBIDDEN_RUNTIME_IMPORTS = (
    "engines.market_context_v2",
    "from engines.market_context_v2",
)
FORBIDDEN_MUTATIONS = (
    "place_order(",
    "modify_order(",
    "cancel_order(",
    "exit_position(",
)


def _tracked_files() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(
        line.strip().replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.strip()
    )


def _python_files(path: Path) -> tuple[Path, ...]:
    if path.is_file():
        return (path,)
    return tuple(sorted(path.rglob("*.py")))


def test_vm19_release_documents_are_present_and_consistent():
    master_plan = (ROOT / "docs" / "VISION_MASTER_PLAN.md").read_text(encoding="utf-8")
    boundary = (ROOT / "docs" / "V1_RELEASE_BOUNDARY.md").read_text(encoding="utf-8")
    changelog = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Version: 1.0.0" in readme
    assert "## Current Release Boundary" in master_plan
    assert "VM-18 Production Hardening & Stress Validation" in master_plan
    assert "VM-19 Version 1.0 Final Certification" in master_plan
    assert "Live broker order placement | DISABLED BY DESIGN" in boundary
    assert "Dashboard | PARTIAL" in boundary
    assert "Voice | PARTIAL / LEGACY" in boundary
    assert "## VM-19 Version 1.0 Final Certification" in changelog


def test_vm19_protected_execution_defaults_remain_intact():
    configuration = RuntimeConfiguration()
    assert configuration.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert configuration.directional_option_selling_configuration.execution_style is OptionPaperExecutionStyle.UNDERLYING_PAPER


def test_vm19_directional_option_selling_environment_contract_is_explicit():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "OPTION_PAPER_EXECUTION_STYLE=directional_option_selling_paper" in env_example
    assert "LIVE_MARKET_DATA_ENABLED=false" in env_example
    assert "LIVE_OPTION_CHAIN_ENABLED=false" in env_example
    assert "HISTORICAL_REPLAY_ENABLED=false" in env_example
    assert "BACKTEST_ENABLED=false" in env_example


def test_vm19_generated_artifacts_and_local_secrets_are_not_tracked():
    tracked = _tracked_files()
    forbidden_suffixes = (".pyc", ".pyo", ".coverage", "coverage.xml")
    forbidden_names = {".env", "repository_tree.txt", "price_action_engine_v1.patch"}
    offenders = [
        path
        for path in tracked
        if "__pycache__/" in path
        or path.endswith(forbidden_suffixes)
        or path in forbidden_names
        or path.startswith(".pytest_cache/")
        or path.startswith("htmlcov/")
        or path.startswith("logs/")
    ]
    assert offenders == []


def test_vm19_active_ai_chain_has_no_legacy_market_context_dependency():
    offenders: list[str] = []
    for target in ACTIVE_AI_PATHS:
        for path in _python_files(target):
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in FORBIDDEN_RUNTIME_IMPORTS):
                offenders.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    assert offenders == []


def test_vm19_active_runtime_has_no_direct_broker_mutation_calls():
    source_files = (
        ROOT / "application" / "symbol_runtime.py",
        ROOT / "application" / "orchestrator.py",
        ROOT / "application" / "broker_account_sync" / "coordinator.py",
        ROOT / "dashboard" / "presenters.py",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    assert all(token not in combined for token in FORBIDDEN_MUTATIONS)


def test_vm19_active_chain_is_documented_in_the_release_boundary():
    text = (ROOT / "docs" / "V1_RELEASE_BOUNDARY.md").read_text(encoding="utf-8")
    required = (
        "Evidence Engines",
        "Multi-Timeframe Evidence Fusion",
        "Market State",
        "Expert Setup Classification",
        "Chart Explanation",
        "AI Reasoning V2",
        "StrategyDecisionV2",
        "RiskManagementV2",
        "TradeLifecycleV1",
        "TradeJournalV1",
    )
    assert all(item in text for item in required)


def test_vm19_no_secret_material_is_present_in_example_configuration():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "ZERODHA_API_KEY=" in env_example
    assert "ZERODHA_API_SECRET=" in env_example
    assert "ZERODHA_ACCESS_TOKEN=" in env_example
    for marker in ("api_key=", "api_secret=", "access_token=", "request_token="):
        assert marker not in env_example
