from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_AI_CHAIN = (
    ROOT / "application" / "symbol_runtime.py",
    ROOT / "engines" / "ai_reasoning_v2",
    ROOT / "engines" / "strategy_decision_v2",
    ROOT / "engines" / "risk_management_v2",
    ROOT / "engines" / "trade_lifecycle_v1",
    ROOT / "engines" / "trade_journal_v1",
    ROOT / "application" / "trade_lifecycle_runtime_integration_v1",
    ROOT / "application" / "trade_journal_runtime_integration_v1",
)


def _tracked_files() -> tuple[str, ...]:
    head = ROOT / ".git" / "HEAD"
    assert head.exists(), "release hardening guard expects a git checkout"
    import subprocess

    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip())


def _python_files(path: Path) -> tuple[Path, ...]:
    if path.is_file():
        return (path,)
    return tuple(sorted(path.glob("*.py")))


def test_generated_artifacts_are_not_tracked():
    tracked = _tracked_files()
    forbidden_suffixes = (".pyc", ".pyo", ".coverage", "coverage.xml")
    forbidden_names = {
        ".env",
        "repository_tree.txt",
        "price_action_engine_v1.patch",
    }
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


def test_legacy_market_context_v2_is_classified_and_not_used_by_active_ai_chain():
    boundary = (ROOT / "docs" / "V1_RELEASE_BOUNDARY.md").read_text(encoding="utf-8")
    assert "`engines/market_context_v2/` | LEGACY-TESTED" in boundary
    offenders = []
    for target in ACTIVE_AI_CHAIN:
        for path in _python_files(target):
            text = path.read_text(encoding="utf-8")
            if "engines.market_context_v2" in text or "MarketContextV2" in text:
                offenders.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    assert offenders == []


def test_release_boundary_documents_active_chain_and_known_v1_statuses():
    text = (ROOT / "docs" / "V1_RELEASE_BOUNDARY.md").read_text(encoding="utf-8")
    for required in (
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
        "Live broker order placement | DISABLED BY DESIGN",
        "Dashboard | PARTIAL",
        "Voice | PARTIAL / LEGACY",
    ):
        assert required in text
