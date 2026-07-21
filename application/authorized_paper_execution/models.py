"""
Immutable Authorized Paper Execution Handoff V1 models.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from application.enums import RuntimeInstrument
from engines.paper_execution_coordinator.models import PaperExecutionReceipt
from engines.strategy.enums import TradeDirection
from engines.trade_decision_authorization.models import TradeAuthorizationResult
from engines.trade_execution_policy.models import TradeExecutionPlan

from .enums import (
    AuthorizedPaperHandoffDecision,
    AuthorizedPaperHandoffLifecycle,
    AuthorizedPaperHandoffReason,
)


SUPPORTED_HANDOFF_INSTRUMENTS = (
    RuntimeInstrument.NIFTY,
    RuntimeInstrument.BANKNIFTY,
    RuntimeInstrument.SENSEX,
)


@dataclass(frozen=True, slots=True)
class AuthorizedPaperHandoffRequest:
    handoff_id: str
    timestamp: datetime
    instrument: str | RuntimeInstrument
    authorization_result: TradeAuthorizationResult | object
    execution_plan: TradeExecutionPlan | object
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "handoff_id", _text(self.handoff_id, "handoff_id"))
        _aware(self.timestamp, "timestamp")
        object.__setattr__(self, "instrument", normalize_instrument(self.instrument))
        for timestamp in _authorization_timestamps(self.authorization_result):
            if timestamp > self.timestamp:
                raise ValueError("authorization_result timestamp cannot be in the future")
        object.__setattr__(self, "correlation_id", _optional_text(self.correlation_id))

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


@dataclass(frozen=True, slots=True)
class AuthorizedPaperHandoffResult:
    handoff_id: str
    timestamp: datetime
    instrument: RuntimeInstrument
    direction: TradeDirection
    decision: AuthorizedPaperHandoffDecision
    primary_reason: AuthorizedPaperHandoffReason
    reasons: tuple[AuthorizedPaperHandoffReason, ...]
    paper_execution_invoked: bool
    paper_execution_call_count: int
    paper_execution_result: PaperExecutionReceipt | None
    authorization_id: str | None
    execution_plan_id: str | None
    correlation_id: str | None = None
    broker_order_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "handoff_id", _text(self.handoff_id, "handoff_id"))
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        if not isinstance(self.direction, TradeDirection):
            raise TypeError("direction must be TradeDirection")
        if not isinstance(self.decision, AuthorizedPaperHandoffDecision):
            raise TypeError("decision must be AuthorizedPaperHandoffDecision")
        if not isinstance(self.primary_reason, AuthorizedPaperHandoffReason):
            raise TypeError("primary_reason must be AuthorizedPaperHandoffReason")
        reasons = tuple(self.reasons)
        if not reasons or any(not isinstance(reason, AuthorizedPaperHandoffReason) for reason in reasons):
            raise TypeError("reasons must contain AuthorizedPaperHandoffReason values")
        object.__setattr__(self, "reasons", reasons)
        if type(self.paper_execution_invoked) is not bool:
            raise TypeError("paper_execution_invoked must be bool")
        if self.paper_execution_call_count not in {0, 1}:
            raise ValueError("paper_execution_call_count must be zero or one")
        if self.paper_execution_invoked != (self.paper_execution_call_count == 1):
            raise ValueError("paper_execution_invoked must match paper_execution_call_count")
        if self.paper_execution_result is not None and not isinstance(self.paper_execution_result, PaperExecutionReceipt):
            raise TypeError("paper_execution_result must be PaperExecutionReceipt or None")
        object.__setattr__(self, "authorization_id", _optional_text(self.authorization_id))
        object.__setattr__(self, "execution_plan_id", _optional_text(self.execution_plan_id))
        object.__setattr__(self, "correlation_id", _optional_text(self.correlation_id))
        if self.broker_order_calls != 0:
            raise ValueError("broker_order_calls must remain zero")
        if self.live_order_submission_enabled is not False:
            raise ValueError("live_order_submission_enabled must remain False")


@dataclass(frozen=True, slots=True)
class AuthorizedPaperHandoffSnapshot:
    enabled: bool
    lifecycle_state: AuthorizedPaperHandoffLifecycle
    handoff_count: int
    executed_count: int
    held_count: int
    rejected_count: int
    failed_paper_execution_count: int
    last_result: AuthorizedPaperHandoffResult | None
    paper_execution_call_count: int
    broker_order_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be bool")
        if not isinstance(self.lifecycle_state, AuthorizedPaperHandoffLifecycle):
            raise TypeError("lifecycle_state must be AuthorizedPaperHandoffLifecycle")
        for name in (
            "handoff_count",
            "executed_count",
            "held_count",
            "rejected_count",
            "failed_paper_execution_count",
            "paper_execution_call_count",
        ):
            _non_negative_int(getattr(self, name), name)
        if self.last_result is not None and not isinstance(self.last_result, AuthorizedPaperHandoffResult):
            raise TypeError("last_result must be AuthorizedPaperHandoffResult or None")
        if self.broker_order_calls != 0:
            raise ValueError("broker_order_calls must remain zero")
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
    if instrument not in SUPPORTED_HANDOFF_INSTRUMENTS:
        raise ValueError("unsupported instrument")
    return instrument


def _authorization_timestamps(value: object) -> tuple[datetime, ...]:
    timestamps = []
    for name in ("timestamp",):
        timestamp = getattr(value, name, None)
        if isinstance(timestamp, datetime):
            _aware(timestamp, name)
            timestamps.append(timestamp)
    return tuple(timestamps)


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must be non-empty text")
    return text[:500]


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _text(value, "optional text")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _model_payload(value: Any):
    if hasattr(value, "__dataclass_fields__"):
        return {key: _model_payload(getattr(value, key)) for key in sorted(value.__dataclass_fields__)}
    if isinstance(value, dict):
        return {str(key): _model_payload(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_model_payload(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _fingerprint(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
