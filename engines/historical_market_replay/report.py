from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from engines.historical_market_replay.enums import ReplayLifecycleState, ReplayOutcome, ReplaySeverity
from engines.historical_market_replay.models import ReplayReport, ReplaySessionSnapshot


def outcome_for(snapshot: ReplaySessionSnapshot) -> ReplayOutcome:
    if snapshot.lifecycle_state is ReplayLifecycleState.STOPPED:
        return ReplayOutcome.STOPPED
    if snapshot.lifecycle_state is ReplayLifecycleState.FAILED:
        return ReplayOutcome.FAIL
    if snapshot.lifecycle_state is not ReplayLifecycleState.COMPLETED:
        return ReplayOutcome.INCOMPLETE
    findings = snapshot.active_findings
    if any(item.severity in (ReplaySeverity.ERROR, ReplaySeverity.CRITICAL) for item in findings):
        return ReplayOutcome.FAIL
    if any(item.severity is ReplaySeverity.WARNING for item in findings):
        return ReplayOutcome.PASS_WITH_WARNINGS
    return ReplayOutcome.PASS


def build_report(snapshot: ReplaySessionSnapshot, manifest, *, created_at: datetime) -> ReplayReport:
    outcome = outcome_for(snapshot)
    return ReplayReport(
        session_id=snapshot.session_id,
        manifest=manifest,
        snapshot=replace(snapshot, final_outcome=outcome),
        outcome=outcome,
        created_at=created_at,
    )
