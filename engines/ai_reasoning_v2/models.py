"""
Immutable AI Reasoning Engine V2 models.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real

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
from engines.market_context_v2.enums import (
    EvidenceDirection,
    EvidenceStrength,
    MarketEvidenceSource,
)
from engines.market_context_v2.models import (
    PRIMARY_SOURCES,
    SUPPORTED_INSTRUMENTS,
    MarketContextV2Snapshot,
)


@dataclass(frozen=True, slots=True)
class AIReasoningEvidence:
    source: MarketEvidenceSource
    role: AIReasoningEvidenceRole
    impact: AIReasoningImpact
    direction: EvidenceDirection
    strength: EvidenceStrength
    score: int
    explanation: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, MarketEvidenceSource):
            raise TypeError("source must be MarketEvidenceSource")
        if not isinstance(self.role, AIReasoningEvidenceRole):
            raise TypeError("role must be AIReasoningEvidenceRole")
        if not isinstance(self.impact, AIReasoningImpact):
            raise TypeError("impact must be AIReasoningImpact")
        if not isinstance(self.direction, EvidenceDirection):
            raise TypeError("direction must be EvidenceDirection")
        if not isinstance(self.strength, EvidenceStrength):
            raise TypeError("strength must be EvidenceStrength")
        if isinstance(self.score, bool) or not isinstance(self.score, int):
            raise TypeError("score must be integer")
        _non_empty(self.explanation, "explanation")
        if self.role is AIReasoningEvidenceRole.PRIMARY and self.source not in PRIMARY_SOURCES:
            raise ValueError("primary role is only allowed for Price Action and Option Chain")
        if self.role is AIReasoningEvidenceRole.CONFIRMATION and self.source in PRIMARY_SOURCES:
            raise ValueError("primary sources cannot be confirmation evidence")
        if self.role is AIReasoningEvidenceRole.CONFLICT and self.impact not in {
            AIReasoningImpact.CREATES_CONFLICT,
            AIReasoningImpact.REDUCES_CONFIDENCE,
        }:
            raise ValueError("conflict role must use conflict impact")
        if self.role is AIReasoningEvidenceRole.UNAVAILABLE:
            if self.direction is not EvidenceDirection.UNAVAILABLE:
                raise ValueError("unavailable role requires unavailable direction")
            if self.impact is not AIReasoningImpact.NO_IMPACT:
                raise ValueError("unavailable role requires no impact")


@dataclass(frozen=True, slots=True)
class AIReasoningCaution:
    severity: AICautionSeverity
    category: str
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.severity, AICautionSeverity):
            raise TypeError("severity must be AICautionSeverity")
        _non_empty(self.category, "category")
        _non_empty(self.message, "message")


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
        _non_empty(self.condition, "condition")
        _non_empty(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class AIReasoningV2Input:
    context: MarketContextV2Snapshot
    previous_reasoning: "AIReasoningV2Snapshot | None" = None

    def __post_init__(self) -> None:
        if not isinstance(self.context, MarketContextV2Snapshot):
            raise TypeError("context must be MarketContextV2Snapshot")
        if self.previous_reasoning is not None:
            if not isinstance(self.previous_reasoning, AIReasoningV2Snapshot):
                raise TypeError("previous_reasoning must be AIReasoningV2Snapshot or None")
            if self.previous_reasoning.instrument is not self.context.instrument:
                raise ValueError("previous reasoning instrument must match context")
            if self.previous_reasoning.timestamp > self.context.timestamp:
                raise ValueError("previous reasoning cannot be from the future")


@dataclass(frozen=True, slots=True)
class AIReasoningV2Snapshot:
    instrument: Instrument
    timestamp: datetime
    direction: AIReasoningDirection
    conviction: AIConviction
    reasoning_state: AIReasoningState
    change: AIReasoningChange
    caution_severity: AICautionSeverity
    market_context: MarketContextV2Snapshot
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

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.market_context, MarketContextV2Snapshot):
            raise TypeError("market_context must be MarketContextV2Snapshot")
        if self.market_context.instrument is not self.instrument:
            raise ValueError("instrument must match market context")
        if self.market_context.timestamp != self.timestamp:
            raise ValueError("timestamp must match market context")
        for name, enum_type in (
            ("direction", AIReasoningDirection),
            ("conviction", AIConviction),
            ("reasoning_state", AIReasoningState),
            ("change", AIReasoningChange),
            ("caution_severity", AICautionSeverity),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be {enum_type.__name__}")
        _non_empty(self.headline, "headline")
        _non_empty(self.summary, "summary")
        _non_empty(self.primary_thesis, "primary_thesis")
        object.__setattr__(self, "evidence", _tuple_of(self.evidence, AIReasoningEvidence, "evidence"))
        object.__setattr__(self, "supporting_points", _strings(self.supporting_points, "supporting_points"))
        object.__setattr__(self, "conflicting_points", _strings(self.conflicting_points, "conflicting_points"))
        object.__setattr__(self, "cautions", _tuple_of(self.cautions, AIReasoningCaution, "cautions"))
        object.__setattr__(self, "watch_conditions", _tuple_of(self.watch_conditions, AIWatchCondition, "watch_conditions"))
        object.__setattr__(self, "rationale", _strings(self.rationale, "rationale"))
        object.__setattr__(self, "confidence", _bounded(self.confidence, "confidence"))
        if self.confidence != self.market_context.confidence:
            raise ValueError("confidence must equal market context confidence")
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


def _non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


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
