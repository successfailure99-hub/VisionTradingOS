"""
Immutable Trade Decision Authorization Gate V1 models.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from application.enums import RuntimeInstrument
from engines.ai_confidence_calibration.models import ConfidenceCalibrationResult
from engines.risk.models import RiskDecisionState
from engines.strategy.enums import TradeDirection
from engines.strategy.models import StrategyDecisionState
from engines.trade_decision_authorization.enums import (
    TradeAuthorizationDecision,
    TradeAuthorizationLifecycle,
    TradeAuthorizationReason,
)
from engines.trade_execution_policy.models import TradeExecutionPlan


SUPPORTED_AUTHORIZATION_INSTRUMENTS = (
    RuntimeInstrument.NIFTY,
    RuntimeInstrument.BANKNIFTY,
    RuntimeInstrument.SENSEX,
)


@dataclass(frozen=True, slots=True)
class TradeAuthorizationRequest:
    authorization_id: str
    timestamp: datetime
    instrument: str | RuntimeInstrument
    strategy_decision: StrategyDecisionState | object | None
    confidence_result: ConfidenceCalibrationResult | object | None
    risk_result: RiskDecisionState | object | None
    execution_policy_result: TradeExecutionPlan | object | None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "authorization_id", _safe_text(self.authorization_id, "authorization_id"))
        _aware_datetime(self.timestamp, "timestamp")
        object.__setattr__(self, "instrument", normalize_instrument(self.instrument))
        for name, value in (
            ("strategy_decision", self.strategy_decision),
            ("confidence_result", self.confidence_result),
            ("risk_result", self.risk_result),
            ("execution_policy_result", self.execution_policy_result),
        ):
            timestamp = source_timestamp(value)
            if timestamp is not None and timestamp > self.timestamp:
                raise ValueError(f"{name} timestamp cannot be in the future")
        if self.correlation_id is not None:
            object.__setattr__(self, "correlation_id", _safe_text(self.correlation_id, "correlation_id"))

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


@dataclass(frozen=True, slots=True)
class TradeAuthorizationResult:
    authorization_id: str
    timestamp: datetime
    instrument: RuntimeInstrument
    direction: TradeDirection
    decision: TradeAuthorizationDecision
    primary_reason: TradeAuthorizationReason
    reasons: tuple[TradeAuthorizationReason, ...]
    authorization_multiplier: float
    stale_inputs: tuple[str, ...]
    invalid_inputs: tuple[str, ...]
    source_strategy_id: str | None
    source_confidence_id: str | None
    source_risk_id: str | None
    source_policy_id: str | None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "authorization_id", _safe_text(self.authorization_id, "authorization_id"))
        _aware_datetime(self.timestamp, "timestamp")
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        if not isinstance(self.direction, TradeDirection):
            raise TypeError("direction must be TradeDirection")
        if not isinstance(self.decision, TradeAuthorizationDecision):
            raise TypeError("decision must be TradeAuthorizationDecision")
        if not isinstance(self.primary_reason, TradeAuthorizationReason):
            raise TypeError("primary_reason must be TradeAuthorizationReason")
        reasons = tuple(self.reasons)
        if not reasons or any(not isinstance(item, TradeAuthorizationReason) for item in reasons):
            raise TypeError("reasons must contain TradeAuthorizationReason values")
        object.__setattr__(self, "reasons", reasons)
        if self.authorization_multiplier not in {0.0, 0.5, 1.0}:
            raise ValueError("authorization_multiplier must be 0.0, 0.5 or 1.0")
        object.__setattr__(self, "authorization_multiplier", float(self.authorization_multiplier))
        object.__setattr__(self, "stale_inputs", tuple(_safe_text(item, "stale_input") for item in self.stale_inputs))
        object.__setattr__(self, "invalid_inputs", tuple(_safe_text(item, "invalid_input") for item in self.invalid_inputs))
        for name in ("source_strategy_id", "source_confidence_id", "source_risk_id", "source_policy_id", "correlation_id"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _safe_text(value, name))


@dataclass(frozen=True, slots=True)
class TradeAuthorizationSnapshot:
    enabled: bool
    lifecycle_state: TradeAuthorizationLifecycle
    authorization_count: int
    authorized_count: int
    reduced_count: int
    blocked_count: int
    last_result: TradeAuthorizationResult | None
    broker_order_calls: int = 0
    mutation_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be bool")
        if not isinstance(self.lifecycle_state, TradeAuthorizationLifecycle):
            raise TypeError("lifecycle_state must be TradeAuthorizationLifecycle")
        for name in ("authorization_count", "authorized_count", "reduced_count", "blocked_count"):
            _non_negative_int(getattr(self, name), name)
        if self.last_result is not None and not isinstance(self.last_result, TradeAuthorizationResult):
            raise TypeError("last_result must be TradeAuthorizationResult or None")
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
    if instrument not in SUPPORTED_AUTHORIZATION_INSTRUMENTS:
        raise ValueError("unsupported instrument")
    return instrument


def source_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    for name in ("timestamp", "created_at", "updated_at"):
        timestamp = getattr(value, name, None)
        if isinstance(timestamp, datetime):
            return timestamp
    return None


def source_instrument(value: object) -> str | None:
    raw = getattr(value, "instrument", getattr(value, "symbol", None))
    if raw is None:
        return None
    text = raw.value if hasattr(raw, "value") else str(raw)
    return text.strip().upper()


def _aware_datetime(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _safe_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must be non-empty text")
    for token in ("api_key", "api_secret", "access_token", "request_token"):
        text = text.replace(token, "[REDACTED]")
    return text[:500]


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _model_payload(value: Any):
    if hasattr(value, "__dataclass_fields__"):
        return {key: _model_payload(getattr(value, key)) for key in sorted(value.__dataclass_fields__)}
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
    return value


def _fingerprint(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
