"""
Deterministic validation reports for assembled Vision Method snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame

from .enums import (
    VisionCandidateState,
    VisionLevelQuality,
    VisionOptionConfirmation,
    VisionSetupQuality,
)
from .models import VisionMethodSnapshot
from .validator import validate_vision_method_snapshot


class VisionMethodValidationResult(str, Enum):
    VALID = "valid"
    PARTIAL = "partial"
    INVALID = "invalid"
    CONFLICT = "conflict"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class VisionMethodValidationTraceStep:
    step_number: int | None
    stage: str
    observed: str
    status: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.step_number is not None:
            if isinstance(self.step_number, bool) or not isinstance(self.step_number, int):
                raise TypeError("step_number must be int or None.")
            if self.step_number <= 0:
                raise ValueError("step_number must be positive.")
        object.__setattr__(self, "stage", _normalize_text(self.stage, "stage"))
        object.__setattr__(self, "observed", _normalize_text(self.observed, "observed"))
        status = _normalize_text(self.status, "status")
        if status not in {"pass", "fail", "missing"}:
            raise ValueError("status must be pass, fail, or missing.")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "detail", _normalize_optional_text(self.detail, "detail"))


@dataclass(frozen=True, slots=True)
class VisionMethodValidationMetrics:
    completed_steps: int
    failed_steps: int
    missing_steps: int
    confidence_inputs: tuple[str, ...]
    blocking_stage: str | None

    def __post_init__(self) -> None:
        for field_name in ("completed_steps", "failed_steps", "missing_steps"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be int.")
            if value < 0:
                raise ValueError(f"{field_name} cannot be negative.")
        object.__setattr__(self, "confidence_inputs", _normalize_unique_text_tuple(self.confidence_inputs, "confidence_inputs"))
        if self.blocking_stage is not None:
            object.__setattr__(self, "blocking_stage", _normalize_text(self.blocking_stage, "blocking_stage"))


@dataclass(frozen=True, slots=True)
class VisionMethodValidationExportRecord:
    instrument: str
    timeframe: str
    timestamp: str
    candidate_state: str
    quality: str
    validation_result: str
    blocking_stage: str
    completed_steps: int
    failed_steps: int
    missing_steps: int
    supporting_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    trace: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "instrument",
            "timeframe",
            "timestamp",
            "candidate_state",
            "quality",
            "validation_result",
            "blocking_stage",
        ):
            object.__setattr__(self, field_name, _normalize_optional_text(getattr(self, field_name), field_name))
        for field_name in ("completed_steps", "failed_steps", "missing_steps"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be int.")
            if value < 0:
                raise ValueError(f"{field_name} cannot be negative.")
        object.__setattr__(self, "supporting_reasons", _normalize_unique_text_tuple(self.supporting_reasons, "supporting_reasons"))
        object.__setattr__(self, "blocking_reasons", _normalize_unique_text_tuple(self.blocking_reasons, "blocking_reasons"))
        object.__setattr__(self, "trace", _normalize_text_tuple(self.trace, "trace"))


@dataclass(frozen=True, slots=True)
class VisionMethodValidationReport:
    instrument: RuntimeInstrument
    timeframe: TimeFrame
    timestamp: datetime
    opening_context: str
    level_context: str
    opening_range: str
    structure: str
    liquidity: str
    structure_events: str
    setup: str
    option_confirmation: str
    candidate_state: VisionCandidateState
    quality: str
    supporting_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    validation_result: VisionMethodValidationResult
    trace: tuple[VisionMethodValidationTraceStep, ...]
    metrics: VisionMethodValidationMetrics
    export_record: VisionMethodValidationExportRecord

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        _validate_aware(self.timestamp, "timestamp")
        for field_name in (
            "opening_context",
            "level_context",
            "opening_range",
            "structure",
            "liquidity",
            "structure_events",
            "setup",
            "option_confirmation",
            "quality",
        ):
            object.__setattr__(self, field_name, _normalize_text(getattr(self, field_name), field_name))
        if not isinstance(self.candidate_state, VisionCandidateState):
            raise TypeError("candidate_state must be VisionCandidateState.")
        object.__setattr__(self, "supporting_reasons", _normalize_unique_text_tuple(self.supporting_reasons, "supporting_reasons"))
        object.__setattr__(self, "blocking_reasons", _normalize_unique_text_tuple(self.blocking_reasons, "blocking_reasons"))
        if not isinstance(self.validation_result, VisionMethodValidationResult):
            raise TypeError("validation_result must be VisionMethodValidationResult.")
        object.__setattr__(self, "trace", _normalize_trace(self.trace))
        if not isinstance(self.metrics, VisionMethodValidationMetrics):
            raise TypeError("metrics must be VisionMethodValidationMetrics.")
        if not isinstance(self.export_record, VisionMethodValidationExportRecord):
            raise TypeError("export_record must be VisionMethodValidationExportRecord.")


def validate_vision_method(snapshot: VisionMethodSnapshot) -> VisionMethodValidationReport:
    snapshot = validate_vision_method_snapshot(snapshot)
    trace = _trace(snapshot)
    metrics = _metrics(trace, snapshot)
    validation_result = _validation_result(snapshot, metrics)
    report = VisionMethodValidationReport(
        instrument=snapshot.instrument,
        timeframe=snapshot.timeframe,
        timestamp=snapshot.timestamp,
        opening_context=_opening_summary(snapshot),
        level_context=_level_summary(snapshot),
        opening_range=_opening_range_summary(snapshot),
        structure=_structure_summary(snapshot),
        liquidity=_liquidity_summary(snapshot),
        structure_events=_structure_events_summary(snapshot),
        setup=_setup_summary(snapshot),
        option_confirmation=_option_summary(snapshot),
        candidate_state=snapshot.candidate_state,
        quality=snapshot.quality,
        supporting_reasons=snapshot.supporting_reasons,
        blocking_reasons=snapshot.blocking_reasons,
        validation_result=validation_result,
        trace=trace,
        metrics=metrics,
        export_record=_export_record(snapshot, trace, metrics, validation_result),
    )
    return validate_vision_method_validation_report(report)


def validate_vision_method_validation_report(report: VisionMethodValidationReport) -> VisionMethodValidationReport:
    if not isinstance(report, VisionMethodValidationReport):
        raise TypeError("report must be VisionMethodValidationReport.")
    if report.instrument.value != report.export_record.instrument:
        raise ValueError("export instrument mismatch.")
    if report.timeframe.value != report.export_record.timeframe:
        raise ValueError("export timeframe mismatch.")
    if report.timestamp.isoformat() != report.export_record.timestamp:
        raise ValueError("export timestamp mismatch.")
    if report.validation_result.value != report.export_record.validation_result:
        raise ValueError("export validation_result mismatch.")
    return report


build_vision_method_validation_report = validate_vision_method


def _trace(snapshot: VisionMethodSnapshot) -> tuple[VisionMethodValidationTraceStep, ...]:
    level = snapshot.level_context
    opening_range = snapshot.opening_range_context
    structure = snapshot.structure_context
    liquidity = snapshot.liquidity_context
    events = snapshot.structure_event_context
    setup = snapshot.setup_qualification_context
    option = snapshot.option_confirmation_context
    failures = {failure.stage.casefold(): failure for failure in snapshot.assembly_failures}
    trace = (
        VisionMethodValidationTraceStep(1, "CPR", level.cpr_context.relation.value, _quality_status(level.quality)),
        VisionMethodValidationTraceStep(2, "Camarilla", level.camarilla_context.zone.value, _quality_status(level.quality)),
        VisionMethodValidationTraceStep(3, "Previous Day", _previous_day_summary(snapshot), "pass"),
        VisionMethodValidationTraceStep(4, "ADR", _adr_summary(snapshot), "missing" if level.adr_context is None else "pass"),
        VisionMethodValidationTraceStep(5, "VWAP", _vwap_summary(snapshot), "missing" if level.vwap_context is None else "pass"),
        VisionMethodValidationTraceStep(
            6,
            "Opening Range",
            opening_range.retest_state.value,
            "pass" if opening_range.range_complete and opening_range.quality is not VisionLevelQuality.INSUFFICIENT else "missing",
            "Opening range incomplete" if not opening_range.range_complete else "",
        ),
        _trace_step_with_failure(
            7,
            "Structure",
            structure.structure_state.value,
            _quality_status(structure.quality),
            failures,
        ),
        _trace_step_with_failure(
            8,
            "Liquidity",
            liquidity.liquidity_sweep.value,
            _quality_status(liquidity.quality),
            failures,
        ),
        VisionMethodValidationTraceStep(
            9,
            "Setup",
            setup.setup_type.value,
            "fail" if setup.setup_quality is VisionSetupQuality.INVALID or setup.blocking_reasons else "pass",
            _failure_detail("Setup", failures) or "; ".join(setup.blocking_reasons),
        ),
        VisionMethodValidationTraceStep(
            10,
            "Option Chain",
            option.confirmation_state.value,
            _option_status(option.confirmation_state),
            "; ".join(option.contradicting_factors or option.neutral_factors),
        ),
        VisionMethodValidationTraceStep(None, "FINAL", snapshot.candidate_state.value, "pass", snapshot.quality),
    )
    return trace


def _trace_step_with_failure(
    step_number: int,
    stage: str,
    observed: str,
    status: str,
    failures: dict[str, object],
) -> VisionMethodValidationTraceStep:
    detail = _failure_detail(stage, failures)
    if detail:
        return VisionMethodValidationTraceStep(step_number, stage, observed, "missing", detail)
    return VisionMethodValidationTraceStep(step_number, stage, observed, status)


def _failure_detail(stage: str, failures: dict[str, object]) -> str:
    failure = failures.get(stage.casefold())
    if failure is None:
        return ""
    return getattr(failure, "validation_message")


def _metrics(
    trace: tuple[VisionMethodValidationTraceStep, ...],
    snapshot: VisionMethodSnapshot,
) -> VisionMethodValidationMetrics:
    decision_steps = tuple(step for step in trace if step.step_number is not None)
    failed_steps = sum(1 for step in decision_steps if step.status == "fail")
    missing_steps = sum(1 for step in decision_steps if step.status == "missing")
    completed_steps = sum(1 for step in decision_steps if step.status == "pass")
    blocking_stage = next(
        (
            step.stage
            for step in decision_steps
            if step.status in {"fail", "missing"} and _trace_step_blocks(step)
        ),
        None,
    )
    return VisionMethodValidationMetrics(
        completed_steps=completed_steps,
        failed_steps=failed_steps,
        missing_steps=missing_steps,
        confidence_inputs=snapshot.supporting_reasons,
        blocking_stage=blocking_stage,
    )


def _validation_result(
    snapshot: VisionMethodSnapshot,
    metrics: VisionMethodValidationMetrics,
) -> VisionMethodValidationResult:
    if snapshot.candidate_state is VisionCandidateState.INSUFFICIENT_DATA:
        return VisionMethodValidationResult.INSUFFICIENT_DATA
    if snapshot.quality == "invalid" or metrics.failed_steps:
        return VisionMethodValidationResult.INVALID
    if metrics.missing_steps or snapshot.candidate_state in {
        VisionCandidateState.OBSERVE,
        VisionCandidateState.WAIT,
        VisionCandidateState.PREPARE_LONG,
        VisionCandidateState.PREPARE_SHORT,
    }:
        return VisionMethodValidationResult.PARTIAL
    return VisionMethodValidationResult.VALID


def _export_record(
    snapshot: VisionMethodSnapshot,
    trace: tuple[VisionMethodValidationTraceStep, ...],
    metrics: VisionMethodValidationMetrics,
    validation_result: VisionMethodValidationResult,
) -> VisionMethodValidationExportRecord:
    return VisionMethodValidationExportRecord(
        instrument=snapshot.instrument.value,
        timeframe=snapshot.timeframe.value,
        timestamp=snapshot.timestamp.isoformat(),
        candidate_state=snapshot.candidate_state.value,
        quality=snapshot.quality,
        validation_result=validation_result.value,
        blocking_stage=metrics.blocking_stage or "",
        completed_steps=metrics.completed_steps,
        failed_steps=metrics.failed_steps,
        missing_steps=metrics.missing_steps,
        supporting_reasons=snapshot.supporting_reasons,
        blocking_reasons=snapshot.blocking_reasons,
        trace=tuple(_trace_line(step) for step in trace),
    )


def _trace_line(step: VisionMethodValidationTraceStep) -> str:
    label = f"STEP {step.step_number}" if step.step_number is not None else "FINAL"
    parts = (label, step.stage, step.observed, step.status)
    if step.detail:
        return " | ".join((*parts, step.detail))
    return " | ".join(parts)


def _opening_summary(snapshot: VisionMethodSnapshot) -> str:
    opening = snapshot.opening_context
    return f"{opening.opening_location.value}; {opening.cpr_relation}; {opening.camarilla_relation}; {opening.gap_type}"


def _level_summary(snapshot: VisionMethodSnapshot) -> str:
    level = snapshot.level_context
    parts = [
        f"CPR {level.cpr_context.relation.value}",
        f"Camarilla {level.camarilla_context.zone.value}",
        _adr_summary(snapshot),
        _vwap_summary(snapshot),
        f"Quality {level.quality.value}",
    ]
    return "; ".join(parts)


def _previous_day_summary(snapshot: VisionMethodSnapshot) -> str:
    previous = snapshot.previous_day_context
    relation = previous.previous_day_relation.value if previous.previous_day_relation is not None else "unknown"
    gap = previous.gap_type.value if previous.gap_type is not None else "unknown"
    virgin = "virgin_cpr" if previous.virgin_cpr else "cpr_used"
    return f"{relation}; {gap}; {virgin}"


def _adr_summary(snapshot: VisionMethodSnapshot) -> str:
    adr = snapshot.level_context.adr_context
    if adr is None:
        return "missing"
    return f"{adr.range_consumed_pct:.0f}% used; {adr.range_remaining_pct:.0f}% remaining; {adr.expansion}; {adr.exhaustion}"


def _vwap_summary(snapshot: VisionMethodSnapshot) -> str:
    vwap = snapshot.level_context.vwap_context
    if vwap is None:
        return "missing"
    return f"{vwap.relation.value}; distance {vwap.distance_pct:.2f}%"


def _opening_range_summary(snapshot: VisionMethodSnapshot) -> str:
    opening = snapshot.opening_range_context
    return (
        f"{opening.opening_start_time.isoformat()} to {opening.opening_end_time.isoformat()}; "
        f"{opening.current_location.value}; {opening.retest_state.value}; complete={opening.range_complete}"
    )


def _structure_summary(snapshot: VisionMethodSnapshot) -> str:
    structure = snapshot.structure_context
    return f"{structure.trend.value}; {structure.structure_state.value}; {structure.quality.value}"


def _liquidity_summary(snapshot: VisionMethodSnapshot) -> str:
    liquidity = snapshot.liquidity_context
    return f"{liquidity.liquidity_pool.value}; {liquidity.liquidity_sweep.value}; {liquidity.quality.value}"


def _structure_events_summary(snapshot: VisionMethodSnapshot) -> str:
    events = snapshot.structure_event_context
    return f"{events.bos.value}; {events.choch.value}; {events.mss.value}; {events.continuation.value}; {events.break_strength.value}"


def _setup_summary(snapshot: VisionMethodSnapshot) -> str:
    setup = snapshot.setup_qualification_context
    return f"{setup.setup_type.value}; {setup.setup_quality.value}; eligible={setup.eligible_for_option_confirmation}"


def _option_summary(snapshot: VisionMethodSnapshot) -> str:
    option = snapshot.option_confirmation_context
    return f"{option.confirmation_state.value}; {option.quality.value}; {option.timestamp.isoformat()}"


def _quality_status(quality: VisionLevelQuality) -> str:
    if quality is VisionLevelQuality.INSUFFICIENT:
        return "missing"
    return "pass"


def _option_status(state: VisionOptionConfirmation) -> str:
    if state is VisionOptionConfirmation.UNAVAILABLE:
        return "missing"
    return "pass"


def _trace_step_blocks(step: VisionMethodValidationTraceStep) -> bool:
    return step.stage not in {"ADR", "VWAP", "Liquidity", "Option Chain"}


def _normalize_trace(values: tuple[VisionMethodValidationTraceStep, ...]) -> tuple[VisionMethodValidationTraceStep, ...]:
    if not isinstance(values, tuple):
        raise TypeError("trace must be tuple.")
    for value in values:
        if not isinstance(value, VisionMethodValidationTraceStep):
            raise TypeError("trace values must be VisionMethodValidationTraceStep.")
    return values


def _normalize_unique_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in _normalize_text_tuple(values, field_name):
        key = value.casefold()
        if key not in seen:
            result.append(value)
            seen.add(key)
    return tuple(result)


def _normalize_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple.")
    return tuple(_normalize_text(value, field_name) for value in values)


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty.")
    return normalized


def _normalize_optional_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str.")
    return value.strip()


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
