"""
Immutable Strategy Decision Engine V2 models.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real

from core.enums.instrument import Instrument
from engines.ai_reasoning_v2.models import AIReasoningV2Snapshot
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context_v2.models import SUPPORTED_INSTRUMENTS, MarketContextV2Snapshot
from engines.strategy_decision_v2.enums import (
    StrategyAction,
    StrategyDecisionChange,
    StrategyDecisionQuality,
    StrategyDirection,
    StrategyInvalidationType,
    StrategyReferenceType,
    StrategySetupFamily,
    StrategySetupStatus,
    StrategyTriggerType,
)
from engines.vwap.levels import VWAPLevels


@dataclass(frozen=True, slots=True)
class StrategyStructuralReference:
    reference_type: StrategyReferenceType
    price: float
    label: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.reference_type, StrategyReferenceType):
            raise TypeError("reference_type must be StrategyReferenceType")
        object.__setattr__(self, "price", _positive(self.price, "price"))
        _non_empty(self.label, "label")
        _non_empty(self.source, "source")


@dataclass(frozen=True, slots=True)
class StrategyEntryCondition:
    priority: int
    trigger_type: StrategyTriggerType
    description: str
    reference: StrategyStructuralReference | None
    mandatory: bool

    def __post_init__(self) -> None:
        _positive_int(self.priority, "priority")
        if not isinstance(self.trigger_type, StrategyTriggerType):
            raise TypeError("trigger_type must be StrategyTriggerType")
        _non_empty(self.description, "description")
        if self.reference is not None and not isinstance(self.reference, StrategyStructuralReference):
            raise TypeError("reference must be StrategyStructuralReference or None")
        if type(self.mandatory) is not bool:
            raise TypeError("mandatory must be bool")
        if self.trigger_type is StrategyTriggerType.NONE and self.mandatory:
            raise ValueError("NONE trigger cannot be mandatory")


@dataclass(frozen=True, slots=True)
class StrategyInvalidationRule:
    priority: int
    invalidation_type: StrategyInvalidationType
    description: str
    reference: StrategyStructuralReference | None

    def __post_init__(self) -> None:
        _positive_int(self.priority, "priority")
        if not isinstance(self.invalidation_type, StrategyInvalidationType):
            raise TypeError("invalidation_type must be StrategyInvalidationType")
        _non_empty(self.description, "description")
        if self.reference is not None and not isinstance(self.reference, StrategyStructuralReference):
            raise TypeError("reference must be StrategyStructuralReference or None")


@dataclass(frozen=True, slots=True)
class StrategyObjective:
    priority: int
    reference: StrategyStructuralReference
    description: str

    def __post_init__(self) -> None:
        _positive_int(self.priority, "priority")
        if not isinstance(self.reference, StrategyStructuralReference):
            raise TypeError("reference must be StrategyStructuralReference")
        _non_empty(self.description, "description")


@dataclass(frozen=True, slots=True)
class StrategyRiskHandoff:
    requires_risk_review: bool
    direction: StrategyDirection
    setup_status: StrategySetupStatus
    invalidation_reference: StrategyStructuralReference | None
    objective_count: int
    context_confidence: float
    reasoning_confidence: float
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.requires_risk_review) is not bool:
            raise TypeError("requires_risk_review must be bool")
        if not isinstance(self.direction, StrategyDirection):
            raise TypeError("direction must be StrategyDirection")
        if not isinstance(self.setup_status, StrategySetupStatus):
            raise TypeError("setup_status must be StrategySetupStatus")
        if self.invalidation_reference is not None and not isinstance(self.invalidation_reference, StrategyStructuralReference):
            raise TypeError("invalidation_reference must be StrategyStructuralReference or None")
        _non_negative_int(self.objective_count, "objective_count")
        object.__setattr__(self, "context_confidence", _bounded(self.context_confidence, "context_confidence"))
        object.__setattr__(self, "reasoning_confidence", _bounded(self.reasoning_confidence, "reasoning_confidence"))
        object.__setattr__(self, "notes", _strings(self.notes, "notes"))
        if self.requires_risk_review and self.setup_status is not StrategySetupStatus.READY_FOR_RISK_REVIEW:
            raise ValueError("risk review is only required for ready setups")


@dataclass(frozen=True, slots=True)
class StrategyDecisionV2Input:
    reasoning: AIReasoningV2Snapshot
    current_price: float
    camarilla: CamarillaLevels | None = None
    cpr: CPRLevels | None = None
    vwap: VWAPLevels | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reasoning, AIReasoningV2Snapshot):
            raise TypeError("reasoning must be AIReasoningV2Snapshot")
        object.__setattr__(self, "current_price", _positive(self.current_price, "current_price"))
        if self.camarilla is not None and not isinstance(self.camarilla, CamarillaLevels):
            raise TypeError("camarilla must be CamarillaLevels or None")
        if self.cpr is not None and not isinstance(self.cpr, CPRLevels):
            raise TypeError("cpr must be CPRLevels or None")
        if self.vwap is not None:
            if not isinstance(self.vwap, VWAPLevels):
                raise TypeError("vwap must be VWAPLevels or None")
            if self.vwap.symbol is not self.reasoning.instrument:
                raise ValueError("vwap instrument mismatch")


@dataclass(frozen=True, slots=True)
class StrategyDecisionV2Snapshot:
    instrument: Instrument
    timestamp: datetime
    action: StrategyAction
    direction: StrategyDirection
    setup_family: StrategySetupFamily
    setup_status: StrategySetupStatus
    quality: StrategyDecisionQuality
    change: StrategyDecisionChange
    market_context: MarketContextV2Snapshot
    ai_reasoning: AIReasoningV2Snapshot
    current_price: float
    setup_name: str
    thesis: str
    entry_conditions: tuple[StrategyEntryCondition, ...]
    invalidation_rules: tuple[StrategyInvalidationRule, ...]
    objectives: tuple[StrategyObjective, ...]
    primary_reference: StrategyStructuralReference | None
    invalidation_reference: StrategyStructuralReference | None
    context_confidence: float
    reasoning_confidence: float
    eligible: bool
    requires_retest: bool
    risk_handoff: StrategyRiskHandoff
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.timestamp, "timestamp")
        for name, enum_type in (
            ("action", StrategyAction),
            ("direction", StrategyDirection),
            ("setup_family", StrategySetupFamily),
            ("setup_status", StrategySetupStatus),
            ("quality", StrategyDecisionQuality),
            ("change", StrategyDecisionChange),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be {enum_type.__name__}")
        if self.market_context.instrument is not self.instrument or self.ai_reasoning.instrument is not self.instrument:
            raise ValueError("context, reasoning and decision instruments must match")
        if self.market_context.timestamp != self.timestamp or self.ai_reasoning.timestamp != self.timestamp:
            raise ValueError("context and reasoning timestamps must match decision timestamp")
        object.__setattr__(self, "current_price", _positive(self.current_price, "current_price"))
        _non_empty(self.setup_name, "setup_name")
        _non_empty(self.thesis, "thesis")
        object.__setattr__(self, "entry_conditions", _tuple_of(self.entry_conditions, StrategyEntryCondition, "entry_conditions"))
        object.__setattr__(self, "invalidation_rules", _tuple_of(self.invalidation_rules, StrategyInvalidationRule, "invalidation_rules"))
        object.__setattr__(self, "objectives", _tuple_of(self.objectives, StrategyObjective, "objectives"))
        for name in ("primary_reference", "invalidation_reference"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, StrategyStructuralReference):
                raise TypeError(f"{name} must be StrategyStructuralReference or None")
        object.__setattr__(self, "context_confidence", _bounded(self.context_confidence, "context_confidence"))
        object.__setattr__(self, "reasoning_confidence", _bounded(self.reasoning_confidence, "reasoning_confidence"))
        if type(self.eligible) is not bool or type(self.requires_retest) is not bool:
            raise TypeError("eligible and requires_retest must be bool")
        if self.eligible and (
            self.action not in {StrategyAction.CONSIDER_LONG, StrategyAction.CONSIDER_SHORT}
            or self.setup_status is not StrategySetupStatus.READY_FOR_RISK_REVIEW
        ):
            raise ValueError("eligible decisions must be ready long or short considerations")
        if self.setup_status is StrategySetupStatus.READY_FOR_RISK_REVIEW:
            if self.direction not in {StrategyDirection.LONG, StrategyDirection.SHORT}:
                raise ValueError("ready setups require directional context")
            if not self.entry_conditions or not self.invalidation_rules:
                raise ValueError("ready setups require conditions and invalidations")
        if not isinstance(self.risk_handoff, StrategyRiskHandoff):
            raise TypeError("risk_handoff must be StrategyRiskHandoff")
        object.__setattr__(self, "rationale", _strings(self.rationale, "rationale"))
        object.__setattr__(self, "warnings", _strings(self.warnings, "warnings"))


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _positive(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def _bounded(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return number


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")


def _non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty string")


def _strings(values, name: str) -> tuple[str, ...]:
    items = tuple(values)
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError(f"{name} must contain non-empty strings")
    return items


def _tuple_of(values, item_type, name: str):
    items = tuple(values)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain {item_type.__name__}")
    return items
