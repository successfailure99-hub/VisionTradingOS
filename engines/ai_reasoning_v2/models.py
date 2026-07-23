"""
Immutable AI Reasoning Engine V2 models.

The V2 model contract consumes deterministic intelligence snapshots only. It
does not depend on Market Context V2 or raw indicator evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real
from typing import Any

from core.enums.instrument import Instrument
from engines.ai_reasoning_v2.enums import (
    AICautionSeverity,
    AIConviction,
    AIReasoningChange,
    AIReasoningDirection,
    AIReasoningEvidenceRole,
    AIReasoningImpact,
    AIReasoningState,
)
_FUSION_SNAPSHOT = "engines.multi_timeframe_evidence_fusion.models.MultiTimeframeEvidenceSnapshot"
_MARKET_STATE_SNAPSHOT = "engines.market_state.models.MarketStateSnapshot"
_SETUP_SNAPSHOT = "engines.expert_setup_classification.models.ExpertSetupClassificationSnapshot"
_EXPLANATION_SNAPSHOT = "engines.chart_explanation.models.ChartExplanationSnapshot"


@dataclass(frozen=True, slots=True)
class AIReasoningEvidence:
    source: str
    role: AIReasoningEvidenceRole
    impact: AIReasoningImpact
    direction: str
    strength: str
    score: int
    explanation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _non_empty(self.source, "source"))
        if not isinstance(self.role, AIReasoningEvidenceRole):
            raise TypeError("role must be AIReasoningEvidenceRole")
        if not isinstance(self.impact, AIReasoningImpact):
            raise TypeError("impact must be AIReasoningImpact")
        object.__setattr__(self, "direction", _non_empty(self.direction, "direction"))
        object.__setattr__(self, "strength", _non_empty(self.strength, "strength"))
        if isinstance(self.score, bool) or not isinstance(self.score, int):
            raise TypeError("score must be integer")
        object.__setattr__(self, "explanation", _non_empty(self.explanation, "explanation"))
        if self.role is AIReasoningEvidenceRole.CONFLICT and self.impact not in {
            AIReasoningImpact.CREATES_CONFLICT,
            AIReasoningImpact.REDUCES_CONFIDENCE,
        }:
            raise ValueError("conflict role must use conflict impact")
        if self.role is AIReasoningEvidenceRole.UNAVAILABLE and self.impact is not AIReasoningImpact.NO_IMPACT:
            raise ValueError("unavailable role requires no impact")


@dataclass(frozen=True, slots=True)
class AIReasoningCaution:
    severity: AICautionSeverity
    category: str
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.severity, AICautionSeverity):
            raise TypeError("severity must be AICautionSeverity")
        object.__setattr__(self, "category", _non_empty(self.category, "category"))
        object.__setattr__(self, "message", _non_empty(self.message, "message"))


@dataclass(frozen=True, slots=True)
class AIWatchCondition:
    priority: int
    condition: str
    reason: str

    def __post_init__(self) -> None:
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be positive integer")
        if self.priority <= 0:
            raise ValueError("priority must be positive")
        object.__setattr__(self, "condition", _non_empty(self.condition, "condition"))
        object.__setattr__(self, "reason", _non_empty(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class AIReasoningV2Input:
    multi_timeframe_evidence: Any
    market_state: Any
    setup_classification: Any
    chart_explanation: Any
    previous_reasoning: "AIReasoningV2Snapshot | None" = None

    def __post_init__(self) -> None:
        _validate_intelligence_contract(
            self.multi_timeframe_evidence,
            self.market_state,
            self.setup_classification,
            self.chart_explanation,
        )
        if self.previous_reasoning is not None:
            if not isinstance(self.previous_reasoning, AIReasoningV2Snapshot):
                raise TypeError("previous_reasoning must be AIReasoningV2Snapshot or None")
            if self.previous_reasoning.instrument.value != self.multi_timeframe_evidence.instrument.value:
                raise ValueError("previous reasoning instrument must match deterministic intelligence")
            if self.previous_reasoning.timestamp > self.chart_explanation.timestamp:
                raise ValueError("previous reasoning cannot be from the future")


@dataclass(frozen=True, slots=True)
class AIReasoningV2Snapshot:
    trading_date: date
    instrument: Instrument
    timestamp: datetime
    direction: AIReasoningDirection
    conviction: AIConviction
    reasoning_state: AIReasoningState
    change: AIReasoningChange
    caution_severity: AICautionSeverity
    multi_timeframe_evidence: Any
    market_state: Any
    setup_classification: Any
    chart_explanation: Any
    headline: str
    summary: str
    primary_thesis: str
    evidence: tuple[AIReasoningEvidence, ...]
    supporting_points: tuple[str, ...]
    conflicting_points: tuple[str, ...]
    cautions: tuple[AIReasoningCaution, ...]
    watch_conditions: tuple[AIWatchCondition, ...]
    confidence: float
    actionable_context: bool
    previous_direction: AIReasoningDirection | None
    previous_confidence: float | None
    rationale: tuple[str, ...]
    source_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be a date")
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be Instrument")
        _aware(self.timestamp, "timestamp")
        _validate_intelligence_contract(
            self.multi_timeframe_evidence,
            self.market_state,
            self.setup_classification,
            self.chart_explanation,
        )
        if self.multi_timeframe_evidence.instrument.value != self.instrument.value:
            raise ValueError("instrument must match deterministic intelligence")
        if self.multi_timeframe_evidence.trading_date != self.trading_date:
            raise ValueError("trading_date must match deterministic intelligence")
        if self.chart_explanation.timestamp != self.timestamp:
            raise ValueError("timestamp must match chart explanation")
        for name, enum_type in (
            ("direction", AIReasoningDirection),
            ("conviction", AIConviction),
            ("reasoning_state", AIReasoningState),
            ("change", AIReasoningChange),
            ("caution_severity", AICautionSeverity),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be {enum_type.__name__}")
        object.__setattr__(self, "headline", _non_empty(self.headline, "headline"))
        object.__setattr__(self, "summary", _non_empty(self.summary, "summary"))
        object.__setattr__(self, "primary_thesis", _non_empty(self.primary_thesis, "primary_thesis"))
        object.__setattr__(self, "evidence", _tuple_of(self.evidence, AIReasoningEvidence, "evidence"))
        object.__setattr__(self, "supporting_points", _strings(self.supporting_points, "supporting_points"))
        object.__setattr__(self, "conflicting_points", _strings(self.conflicting_points, "conflicting_points"))
        object.__setattr__(self, "cautions", _tuple_of(self.cautions, AIReasoningCaution, "cautions"))
        object.__setattr__(self, "watch_conditions", _tuple_of(self.watch_conditions, AIWatchCondition, "watch_conditions"))
        object.__setattr__(self, "rationale", _strings(self.rationale, "rationale"))
        object.__setattr__(self, "confidence", _bounded(self.confidence, "confidence"))
        if type(self.actionable_context) is not bool:
            raise TypeError("actionable_context must be bool")
        if self.previous_direction is not None and not isinstance(
            self.previous_direction,
            AIReasoningDirection,
        ):
            raise TypeError("previous_direction must be AIReasoningDirection or None")
        if self.previous_confidence is not None:
            object.__setattr__(
                self,
                "previous_confidence",
                _bounded(self.previous_confidence, "previous_confidence"),
            )
        object.__setattr__(self, "source_fingerprint", _non_empty(self.source_fingerprint, "source_fingerprint"))


def _validate_intelligence_contract(
    multi_timeframe_evidence: Any,
    market_state: Any,
    setup_classification: Any,
    chart_explanation: Any,
) -> None:
    if not _is_expected_snapshot(multi_timeframe_evidence, _FUSION_SNAPSHOT):
        raise TypeError("multi_timeframe_evidence must be MultiTimeframeEvidenceSnapshot")
    if not _is_expected_snapshot(market_state, _MARKET_STATE_SNAPSHOT):
        raise TypeError("market_state must be MarketStateSnapshot")
    if not _is_expected_snapshot(setup_classification, _SETUP_SNAPSHOT):
        raise TypeError("setup_classification must be ExpertSetupClassificationSnapshot")
    if not _is_expected_snapshot(chart_explanation, _EXPLANATION_SNAPSHOT):
        raise TypeError("chart_explanation must be ChartExplanationSnapshot")
    instrument = multi_timeframe_evidence.instrument
    trading_date = multi_timeframe_evidence.trading_date
    timestamp = multi_timeframe_evidence.timestamp
    for name, snapshot in (
        ("market_state", market_state),
        ("setup_classification", setup_classification),
        ("chart_explanation", chart_explanation),
    ):
        if snapshot.instrument is not instrument:
            raise ValueError(f"{name} instrument must match multi_timeframe_evidence")
        if snapshot.trading_date != trading_date:
            raise ValueError(f"{name} trading_date must match multi_timeframe_evidence")
        if snapshot.timestamp != timestamp:
            raise ValueError(f"{name} timestamp must match multi_timeframe_evidence")


def _is_expected_snapshot(value: Any, expected_path: str) -> bool:
    if value is None:
        return False
    actual_path = f"{value.__class__.__module__}.{value.__class__.__name__}"
    return actual_path == expected_path


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _bounded(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return number


def _non_empty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _strings(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    items = tuple(values)
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError(f"{name} must contain non-empty strings")
    return items


def _tuple_of(values, item_type, name: str):
    items = tuple(values)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain {item_type.__name__}")
    return items
