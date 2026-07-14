"""
Immutable Market Context Engine V2 models.
"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from core.enums.instrument import Instrument
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context_v2.enums import (
    EvidenceDirection,
    EvidenceStrength,
    MarketConflictSeverity,
    MarketContextReadiness,
    MarketDirection,
    MarketEvidenceSource,
    MarketRegime,
    TradePosture,
)
from engines.option_chain_analytics.models import OptionChainAnalyticsSnapshot
from engines.price_action.models import PriceActionState
from engines.vwap.levels import VWAPLevels


SUPPORTED_INSTRUMENTS = {
    Instrument.NIFTY,
    Instrument.BANKNIFTY,
    Instrument.SENSEX,
}
PRIMARY_SOURCES = {
    MarketEvidenceSource.PRICE_ACTION,
    MarketEvidenceSource.OPTION_CHAIN,
}
EVIDENCE_ORDER = (
    MarketEvidenceSource.PRICE_ACTION,
    MarketEvidenceSource.OPTION_CHAIN,
    MarketEvidenceSource.CAMARILLA,
    MarketEvidenceSource.CPR,
    MarketEvidenceSource.VWAP,
)


@dataclass(frozen=True, slots=True)
class MarketEvidence:
    source: MarketEvidenceSource
    direction: EvidenceDirection
    strength: EvidenceStrength
    weight: int
    score: int
    available: bool
    primary: bool
    timestamp: datetime
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source, MarketEvidenceSource):
            raise TypeError("source must be MarketEvidenceSource")
        if not isinstance(self.direction, EvidenceDirection):
            raise TypeError("direction must be EvidenceDirection")
        if not isinstance(self.strength, EvidenceStrength):
            raise TypeError("strength must be EvidenceStrength")
        if isinstance(self.weight, bool) or not isinstance(self.weight, int):
            raise TypeError("weight must be a positive integer")
        if self.weight <= 0:
            raise ValueError("weight must be positive")
        if isinstance(self.score, bool) or not isinstance(self.score, int):
            raise TypeError("score must be an integer")
        if type(self.available) is not bool:
            raise TypeError("available must be bool")
        if type(self.primary) is not bool:
            raise TypeError("primary must be bool")
        _aware(self.timestamp, "timestamp")
        reasons = _strings(self.reasons, "reasons")
        object.__setattr__(self, "reasons", reasons)
        if self.direction is EvidenceDirection.BULLISH and self.score <= 0:
            raise ValueError("bullish evidence requires a positive score")
        if self.direction is EvidenceDirection.BEARISH and self.score >= 0:
            raise ValueError("bearish evidence requires a negative score")
        if self.direction in {
            EvidenceDirection.NEUTRAL,
            EvidenceDirection.CONFLICTED,
            EvidenceDirection.UNAVAILABLE,
        } and self.score != 0:
            raise ValueError(
                "neutral, conflicted and unavailable evidence require zero score"
            )
        if not self.available and self.direction is not EvidenceDirection.UNAVAILABLE:
            raise ValueError(
                "unavailable evidence requires UNAVAILABLE direction"
            )
        if self.direction is EvidenceDirection.UNAVAILABLE and self.available:
            raise ValueError(
                "UNAVAILABLE direction requires available=False"
            )
        if self.primary and self.source not in PRIMARY_SOURCES:
            raise ValueError(
                "only Price Action and Option Chain evidence may be primary"
            )


@dataclass(frozen=True, slots=True)
class MarketEvidenceConflict:
    source_a: MarketEvidenceSource
    direction_a: EvidenceDirection
    source_b: MarketEvidenceSource
    direction_b: EvidenceDirection
    severity: MarketConflictSeverity
    primary_conflict: bool
    rationale: str

    def __post_init__(self) -> None:
        for name in ("source_a", "source_b"):
            if not isinstance(getattr(self, name), MarketEvidenceSource):
                raise TypeError(f"{name} must be MarketEvidenceSource")
        for name in ("direction_a", "direction_b"):
            if not isinstance(getattr(self, name), EvidenceDirection):
                raise TypeError(f"{name} must be EvidenceDirection")
        if self.source_a == self.source_b:
            raise ValueError("conflict sources must differ")
        if not _opposite(self.direction_a, self.direction_b):
            raise ValueError("conflicts require opposite bullish/bearish evidence")
        if not isinstance(self.severity, MarketConflictSeverity):
            raise TypeError("severity must be MarketConflictSeverity")
        if not isinstance(self.primary_conflict, bool):
            raise TypeError("primary_conflict must be bool")
        if not isinstance(self.rationale, str) or not self.rationale:
            raise ValueError("rationale must be non-empty string")


@dataclass(frozen=True, slots=True)
class MarketContextV2Input:
    instrument: Instrument
    timestamp: datetime
    current_price: float
    price_action: PriceActionState | None
    option_chain_analytics: OptionChainAnalyticsSnapshot | None
    camarilla: CamarillaLevels | None
    cpr: CPRLevels | None
    vwap: VWAPLevels | None

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.timestamp, "timestamp")
        object.__setattr__(
            self,
            "current_price",
            _positive_real(self.current_price, "current_price"),
        )
        if self.price_action is not None:
            if not isinstance(self.price_action, PriceActionState):
                raise TypeError("price_action must be PriceActionState or None")
            if self.price_action.symbol != self.instrument.value:
                raise ValueError("price_action instrument mismatch")
            if self.price_action.last_candle.end_time > self.timestamp:
                raise ValueError("price_action timestamp cannot be in the future")
        if self.option_chain_analytics is not None:
            if not isinstance(
                self.option_chain_analytics,
                OptionChainAnalyticsSnapshot,
            ):
                raise TypeError(
                    "option_chain_analytics must be OptionChainAnalyticsSnapshot or None"
                )
            if self.option_chain_analytics.underlying is not self.instrument:
                raise ValueError("option_chain_analytics instrument mismatch")
            if self.option_chain_analytics.timestamp > self.timestamp:
                raise ValueError("option_chain_analytics timestamp cannot be in the future")
        if self.camarilla is not None and not isinstance(self.camarilla, CamarillaLevels):
            raise TypeError("camarilla must be CamarillaLevels or None")
        if self.cpr is not None and not isinstance(self.cpr, CPRLevels):
            raise TypeError("cpr must be CPRLevels or None")
        if self.vwap is not None:
            if not isinstance(self.vwap, VWAPLevels):
                raise TypeError("vwap must be VWAPLevels or None")
            if self.vwap.symbol is not self.instrument:
                raise ValueError("vwap instrument mismatch")
            if self.vwap.timestamp > self.timestamp:
                raise ValueError("vwap timestamp cannot be in the future")
        for name in ("camarilla", "cpr"):
            value = getattr(self, name)
            if value is not None and value.trading_date > self.timestamp.date():
                raise ValueError(f"{name} trading_date cannot be in the future")


@dataclass(frozen=True, slots=True)
class MarketContextV2Snapshot:
    instrument: Instrument
    timestamp: datetime
    readiness: MarketContextReadiness
    direction: MarketDirection
    regime: MarketRegime
    trade_posture: TradePosture
    conflict_severity: MarketConflictSeverity
    bullish_score: int
    bearish_score: int
    net_score: int
    confidence: float
    evidence: tuple[MarketEvidence, ...]
    conflicts: tuple[MarketEvidenceConflict, ...]
    price_action_evidence: MarketEvidence
    option_chain_evidence: MarketEvidence
    camarilla_evidence: MarketEvidence
    cpr_evidence: MarketEvidence
    vwap_evidence: MarketEvidence
    current_price: float
    reference_vwap: float | None
    primary_sources_available: int
    secondary_sources_available: int
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.timestamp, "timestamp")
        for name, enum_type in (
            ("readiness", MarketContextReadiness),
            ("direction", MarketDirection),
            ("regime", MarketRegime),
            ("trade_posture", TradePosture),
            ("conflict_severity", MarketConflictSeverity),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be {enum_type.__name__}")
        for name in ("bullish_score", "bearish_score"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative integer")
        if not isinstance(self.net_score, int) or isinstance(self.net_score, bool):
            raise TypeError("net_score must be integer")
        if self.net_score != self.bullish_score - self.bearish_score:
            raise ValueError("net_score must equal bullish_score - bearish_score")
        object.__setattr__(self, "confidence", _bounded(self.confidence, "confidence"))
        evidence = tuple(self.evidence)
        if tuple(item.source for item in evidence) != EVIDENCE_ORDER:
            raise ValueError("evidence must be in deterministic source order")
        object.__setattr__(self, "evidence", evidence)
        named = (
            self.price_action_evidence,
            self.option_chain_evidence,
            self.camarilla_evidence,
            self.cpr_evidence,
            self.vwap_evidence,
        )
        if named != evidence:
            raise ValueError("named evidence fields must match evidence tuple")
        conflicts = tuple(self.conflicts)
        for conflict in conflicts:
            if not isinstance(conflict, MarketEvidenceConflict):
                raise TypeError("conflicts must contain MarketEvidenceConflict")
        object.__setattr__(self, "conflicts", conflicts)
        object.__setattr__(
            self,
            "current_price",
            _positive_real(self.current_price, "current_price"),
        )
        if self.reference_vwap is not None:
            object.__setattr__(
                self,
                "reference_vwap",
                _positive_real(self.reference_vwap, "reference_vwap"),
            )
        for name in ("primary_sources_available", "secondary_sources_available"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative integer")
        object.__setattr__(self, "rationale", _strings(self.rationale, "rationale"))
        object.__setattr__(self, "warnings", _strings(self.warnings, "warnings"))


def _opposite(a: EvidenceDirection, b: EvidenceDirection) -> bool:
    return {a, b} == {EvidenceDirection.BULLISH, EvidenceDirection.BEARISH}


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _positive_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be positive finite number")
    return number


def _bounded(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return number


def _strings(value: tuple[str, ...], name: str) -> tuple[str, ...]:
    items = tuple(value)
    if any(not isinstance(item, str) or not item for item in items):
        raise TypeError(f"{name} must contain non-empty strings")
    return items
