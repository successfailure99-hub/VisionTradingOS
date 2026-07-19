from __future__ import annotations

from datetime import datetime

from engines.live_market_validation.enums import (
    FindingResolution,
    ValidationHealth,
    ValidationLifecycleState,
    ValidationOutcome,
    ValidationSeverity,
)
from engines.live_market_validation.models import LiveValidationReport, ValidationSessionSnapshot


def outcome_for(snapshot: ValidationSessionSnapshot) -> ValidationOutcome:
    if snapshot.lifecycle_state is ValidationLifecycleState.FAILED:
        return ValidationOutcome.FAIL
    if snapshot.lifecycle_state is not ValidationLifecycleState.COMPLETED:
        return ValidationOutcome.INCOMPLETE
    active = tuple(item for item in snapshot.active_findings if item.resolution is FindingResolution.ACTIVE)
    if any(item.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL) for item in active):
        return ValidationOutcome.FAIL
    if any(item.severity is ValidationSeverity.WARNING for item in active):
        return ValidationOutcome.PASS_WITH_WARNINGS
    return ValidationOutcome.PASS


def health_for_findings(findings) -> ValidationHealth:
    active = tuple(item for item in findings if item.resolution is FindingResolution.ACTIVE)
    if any(item.severity is ValidationSeverity.CRITICAL for item in active):
        return ValidationHealth.FAILED
    if any(item.severity is ValidationSeverity.ERROR for item in active):
        return ValidationHealth.UNHEALTHY
    if any(item.severity is ValidationSeverity.WARNING for item in active):
        return ValidationHealth.DEGRADED
    return ValidationHealth.HEALTHY


def build_report(snapshot: ValidationSessionSnapshot, *, ended_at: datetime) -> LiveValidationReport:
    started_at = snapshot.started_at
    duration = (ended_at - started_at).total_seconds() if started_at is not None else 0.0
    return LiveValidationReport(
        session_id=snapshot.session_id,
        mode=snapshot.mode,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=max(duration, 0.0),
        instruments=snapshot.instruments,
        lifecycle_result=snapshot.lifecycle_state,
        component_summaries=snapshot.component_freshness,
        instrument_summaries=snapshot.instrument_summaries,
        latency_summaries=snapshot.latency_summaries,
        reconnect_summary=snapshot.reconnect_summary,
        findings=snapshot.active_findings,
        counters=snapshot.counters,
        final_health=snapshot.overall_health,
        outcome=outcome_for(snapshot),
    )
