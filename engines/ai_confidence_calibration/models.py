"""
Immutable AI Confidence Calibration Engine V1 models.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real
from typing import Any

from application.enums import RuntimeInstrument
from engines.ai_confidence_calibration.enums import (
    CalibrationDecision,
    ConfidenceBand,
    ConfidenceCalibrationLifecycle,
    EvidenceAlignment,
    EvidenceCategory,
)
from engines.ai_reasoning.models import AIReasoningState
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context.models import MarketContextState
from engines.option_chain.models import OptionChainState
from engines.price_action.models import PriceActionState
from engines.strategy.models import StrategyDecisionState
from engines.vwap.levels import VWAPLevels


SUPPORTED_CONFIDENCE_INSTRUMENTS = (
    RuntimeInstrument.NIFTY,
    RuntimeInstrument.BANKNIFTY,
    RuntimeInstrument.SENSEX,
)


@dataclass(frozen=True, slots=True)
class ConfidenceEvidence:
    category: EvidenceCategory
    alignment: EvidenceAlignment
    maximum_weight: int
    contribution: float
    reason_code: str
    explanation: str
    source_timestamp: datetime | None
    age_seconds: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.category, EvidenceCategory):
            raise TypeError("category must be EvidenceCategory")
        if not isinstance(self.alignment, EvidenceAlignment):
            raise TypeError("alignment must be EvidenceAlignment")
        _non_negative_int(self.maximum_weight, "maximum_weight")
        object.__setattr__(self, "contribution", _finite_real(self.contribution, "contribution"))
        object.__setattr__(self, "reason_code", _safe_text(self.reason_code, "reason_code"))
        object.__setattr__(self, "explanation", _safe_text(self.explanation, "explanation"))
        if self.source_timestamp is not None:
            _aware_datetime(self.source_timestamp, "source_timestamp")
        if self.age_seconds is not None:
            object.__setattr__(self, "age_seconds", _finite_real(self.age_seconds, "age_seconds"))
            if self.age_seconds < 0:
                raise ValueError("age_seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class ConfidenceCalibrationRequest:
    calibration_id: str
    timestamp: datetime
    instrument: str | RuntimeInstrument
    ai_reasoning: AIReasoningState
    strategy_decision: StrategyDecisionState
    price_action: PriceActionState | object | None = None
    option_chain: OptionChainState | object | None = None
    market_context: MarketContextState | object | None = None
    cpr: CPRLevels | object | None = None
    camarilla: CamarillaLevels | object | None = None
    vwap: VWAPLevels | object | None = None
    supporting_indicators: tuple[object, ...] = ()
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "calibration_id", _safe_text(self.calibration_id, "calibration_id"))
        _aware_datetime(self.timestamp, "timestamp")
        instrument = normalize_instrument(self.instrument)
        object.__setattr__(self, "instrument", instrument)
        if not isinstance(self.ai_reasoning, AIReasoningState):
            raise TypeError("ai_reasoning must be AIReasoningState")
        if not isinstance(self.strategy_decision, StrategyDecisionState):
            raise TypeError("strategy_decision must be StrategyDecisionState")
        for name, value in (
            ("ai_reasoning", self.ai_reasoning),
            ("strategy_decision", self.strategy_decision),
            ("price_action", self.price_action),
            ("option_chain", self.option_chain),
            ("market_context", self.market_context),
            ("vwap", self.vwap),
        ):
            _validate_model_instrument(name, value, instrument.value)
            timestamp = evidence_timestamp(value, self.timestamp)
            if timestamp is not None and timestamp > self.timestamp:
                raise ValueError(f"{name} timestamp cannot be in the future")
        for name, value in (("cpr", self.cpr), ("camarilla", self.camarilla)):
            _validate_daily_evidence(name, value, self.timestamp)
        indicators = tuple(self.supporting_indicators)
        for item in indicators:
            _validate_model_instrument("supporting_indicator", item, instrument.value)
            timestamp = evidence_timestamp(item, self.timestamp)
            if timestamp is not None and timestamp > self.timestamp:
                raise ValueError("supporting indicator timestamp cannot be in the future")
        object.__setattr__(self, "supporting_indicators", indicators)
        if self.correlation_id is not None:
            object.__setattr__(self, "correlation_id", _safe_text(self.correlation_id, "correlation_id"))

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


@dataclass(frozen=True, slots=True)
class ConfidenceCalibrationResult:
    calibration_id: str
    timestamp: datetime
    instrument: RuntimeInstrument
    direction: object
    raw_score: float
    penalty_score: float
    final_score: float
    confidence_band: ConfidenceBand
    calibration_decision: CalibrationDecision
    primary_reason: str
    evidence: tuple[ConfidenceEvidence, ...]
    supporting_categories: tuple[EvidenceCategory, ...]
    conflicting_categories: tuple[EvidenceCategory, ...]
    missing_categories: tuple[EvidenceCategory, ...]
    stale_categories: tuple[EvidenceCategory, ...]
    invalid_categories: tuple[EvidenceCategory, ...]
    blocked_reasons: tuple[str, ...]
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "calibration_id", _safe_text(self.calibration_id, "calibration_id"))
        _aware_datetime(self.timestamp, "timestamp")
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        object.__setattr__(self, "raw_score", _score(self.raw_score, "raw_score"))
        object.__setattr__(self, "penalty_score", _finite_real(self.penalty_score, "penalty_score"))
        object.__setattr__(self, "final_score", _score(self.final_score, "final_score"))
        if not isinstance(self.confidence_band, ConfidenceBand):
            raise TypeError("confidence_band must be ConfidenceBand")
        if not isinstance(self.calibration_decision, CalibrationDecision):
            raise TypeError("calibration_decision must be CalibrationDecision")
        object.__setattr__(self, "primary_reason", _safe_text(self.primary_reason, "primary_reason"))
        evidence = tuple(self.evidence)
        if any(not isinstance(item, ConfidenceEvidence) for item in evidence):
            raise TypeError("evidence must contain ConfidenceEvidence values")
        object.__setattr__(self, "evidence", evidence)
        for name in (
            "supporting_categories",
            "conflicting_categories",
            "missing_categories",
            "stale_categories",
            "invalid_categories",
        ):
            object.__setattr__(self, name, _category_tuple(getattr(self, name), name))
        object.__setattr__(self, "blocked_reasons", tuple(_safe_text(item, "blocked_reason") for item in self.blocked_reasons))
        if self.correlation_id is not None:
            object.__setattr__(self, "correlation_id", _safe_text(self.correlation_id, "correlation_id"))


@dataclass(frozen=True, slots=True)
class ConfidenceCalibrationSnapshot:
    enabled: bool
    lifecycle_state: ConfidenceCalibrationLifecycle
    calibration_count: int
    trusted_count: int
    reduced_count: int
    blocked_count: int
    last_result: ConfidenceCalibrationResult | None
    broker_order_calls: int = 0
    mutation_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be bool")
        if not isinstance(self.lifecycle_state, ConfidenceCalibrationLifecycle):
            raise TypeError("lifecycle_state must be ConfidenceCalibrationLifecycle")
        for name in ("calibration_count", "trusted_count", "reduced_count", "blocked_count"):
            _non_negative_int(getattr(self, name), name)
        if self.last_result is not None and not isinstance(self.last_result, ConfidenceCalibrationResult):
            raise TypeError("last_result must be ConfidenceCalibrationResult or None")
        if self.broker_order_calls != 0:
            raise ValueError("broker_order_calls must remain zero")
        if self.mutation_calls != 0:
            raise ValueError("mutation_calls must remain zero")
        if self.live_order_submission_enabled is not False:
            raise ValueError("live_order_submission_enabled must remain False")


def normalize_instrument(value: str | RuntimeInstrument) -> RuntimeInstrument:
    if isinstance(value, RuntimeInstrument):
        instrument = value
    elif isinstance(value, str):
        try:
            instrument = RuntimeInstrument(value.strip().upper())
        except ValueError as exc:
            raise ValueError("unsupported instrument") from exc
    else:
        raise TypeError("instrument must be RuntimeInstrument or text")
    if instrument not in SUPPORTED_CONFIDENCE_INSTRUMENTS:
        raise ValueError("unsupported instrument")
    return instrument


def evidence_timestamp(value: object, request_time: datetime) -> datetime | None:
    if value is None:
        return None
    for name in ("timestamp", "updated_at", "created_at"):
        timestamp = getattr(value, name, None)
        if isinstance(timestamp, datetime):
            return timestamp
    last_candle = getattr(value, "last_candle", None)
    end_time = getattr(last_candle, "end_time", None)
    if isinstance(end_time, datetime):
        return end_time
    trading_date = getattr(value, "trading_date", None)
    if isinstance(trading_date, date) and not isinstance(trading_date, datetime):
        return datetime.combine(trading_date, datetime.min.time(), tzinfo=request_time.tzinfo)
    return None


def _validate_model_instrument(name: str, value: object, instrument: str) -> None:
    if value is None:
        return
    raw = getattr(value, "symbol", getattr(value, "instrument", None))
    if raw is None:
        return
    observed = raw.value if hasattr(raw, "value") else str(raw)
    if observed.strip().upper() != instrument:
        raise ValueError(f"{name} instrument does not match request")


def _validate_daily_evidence(name: str, value: object, request_time: datetime) -> None:
    if value is None:
        return
    trading_date = getattr(value, "trading_date", None)
    if isinstance(trading_date, date) and not isinstance(trading_date, datetime):
        if trading_date > request_time.date():
            raise ValueError(f"{name} trading date cannot be in the future")


def _category_tuple(values: tuple[EvidenceCategory, ...], name: str) -> tuple[EvidenceCategory, ...]:
    result = tuple(values)
    if any(not isinstance(item, EvidenceCategory) for item in result):
        raise TypeError(f"{name} must contain EvidenceCategory values")
    return result


def _aware_datetime(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")
    return value


def _finite_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _score(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number < 0 or number > 100:
        raise ValueError(f"{name} must be between 0 and 100")
    return number


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _safe_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must be non-empty text")
    for token in ("api_key", "api_secret", "access_token", "request_token"):
        text = text.replace(token, "[REDACTED]")
    return text[:500]


def _model_payload(value: Any):
    if hasattr(value, "__dataclass_fields__"):
        return {
            key: _model_payload(getattr(value, key))
            for key in sorted(value.__dataclass_fields__)
        }
    if isinstance(value, dict):
        return {str(key): _model_payload(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_model_payload(item) for item in value]
    if isinstance(value, list):
        return [_model_payload(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _fingerprint(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
