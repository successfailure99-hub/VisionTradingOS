from pathlib import Path

from dashboard.presenters import build_ai_view
from tests.test_vision_method_validation_v1 import snapshot
from tests.test_vision_paper_trading_integration_v1 import process, runtime


def test_fusion_path_no_longer_auto_invokes_legacy_execution_chain():
    source = Path("application/symbol_runtime.py").read_text(encoding="utf-8")
    fusion_body = source.split("def _fuse_multi_timeframe_evidence", 1)[1].split(
        "def _process_v2_execution_chain", 1
    )[0]

    assert "_process_v2_execution_chain" not in fusion_body


def test_dashboard_ai_view_explains_vision_method_candidate():
    item = runtime()
    candidate, report = process(item, snapshot())

    view = build_ai_view(item.snapshot())

    assert candidate.snapshot_reference
    assert report.validation_result.value == "valid"
    assert view.agreement == "Vision Method"
    assert view.market_summary == "Vision Method: Long"
    assert view.explanation.startswith("Vision Method produced a long candidate")


def test_runtime_diagnostics_expose_vision_chain_state():
    item = runtime()
    process(item, snapshot())

    diagnostics = item.snapshot().runtime_diagnostics

    assert diagnostics.current_candidate == "long"
    assert diagnostics.blocking_stage == "NONE"
    assert diagnostics.last_successful_snapshot != "-"
    assert diagnostics.last_validation == "valid"
