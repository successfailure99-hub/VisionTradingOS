"""
Immutable Trade Execution Policy Engine V1 models.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import isfinite
from numbers import Real

from application.enums import RuntimeInstrument
from engines.order_management.enums import OrderSide, OrderType, ProductType
from engines.strategy.enums import TradeDirection
from engines.trade_execution_policy.enums import (
    ExecutionDecisionStatus,
    ExecutionLifecycleState,
    ExecutionMode,
    ExecutionPlanStatus,
    ExecutionReasonCode,
    ExecutionRoutingTarget,
    ExecutionSeverity,
    ProtectiveOrderPurpose,
    ProtectiveOrderStatus,
)


SUPPORTED_INSTRUMENTS = ("BANKNIFTY", "NIFTY", "SENSEX")


@dataclass(frozen=True, slots=True)
class InstrumentTickSize:
    instrument: str
    tick_size: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        object.__setattr__(self, "tick_size", _positive_real(self.tick_size, "tick_size"))


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    enabled: bool = True
    allowed_instruments: tuple[str, ...] = SUPPORTED_INSTRUMENTS
    allowed_execution_modes: tuple[ExecutionMode, ...] = (ExecutionMode.PLAN_ONLY, ExecutionMode.PAPER)
    default_execution_mode: ExecutionMode = ExecutionMode.PLAN_ONLY
    allowed_entry_order_types: tuple[OrderType, ...] = (OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT)
    allow_market_orders: bool = False
    allow_limit_orders: bool = True
    allow_stop_limit_orders: bool = True
    require_manual_approval: bool = True
    require_risk_approval: bool = True
    require_stop_order: bool = True
    require_target_order: bool = True
    maximum_decision_age_seconds: int = 60
    maximum_plan_validity_seconds: int = 120
    maximum_entry_slippage_points: float | None = None
    maximum_entry_slippage_percentage: float | None = 0.10
    minimum_limit_offset_points: float = 0.0
    maximum_limit_offset_points: float | None = None
    price_tick_by_instrument: tuple[InstrumentTickSize, ...] | dict[str, float] = field(
        default_factory=lambda: (
            InstrumentTickSize("BANKNIFTY", 0.05),
            InstrumentTickSize("NIFTY", 0.05),
            InstrumentTickSize("SENSEX", 0.05),
        )
    )
    quantity_must_match_risk_decision: bool = True
    allow_quantity_reduction: bool = False
    allow_quantity_increase: bool = False
    allow_duplicate_plan: bool = False
    one_active_plan_per_signal: bool = True
    one_active_plan_per_risk_decision: bool = True
    paper_only: bool = True

    def __post_init__(self) -> None:
        for name in (
            "enabled",
            "allow_market_orders",
            "allow_limit_orders",
            "allow_stop_limit_orders",
            "require_manual_approval",
            "require_risk_approval",
            "require_stop_order",
            "require_target_order",
            "quantity_must_match_risk_decision",
            "allow_quantity_reduction",
            "allow_quantity_increase",
            "allow_duplicate_plan",
            "one_active_plan_per_signal",
            "one_active_plan_per_risk_decision",
            "paper_only",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        instruments = tuple(_instrument(item) for item in self.allowed_instruments)
        if not instruments or any(item not in SUPPORTED_INSTRUMENTS for item in instruments):
            raise ValueError("allowed_instruments must contain supported instruments")
        if len(set(instruments)) != len(instruments):
            raise ValueError("allowed_instruments must be unique")
        object.__setattr__(self, "allowed_instruments", tuple(sorted(instruments)))
        modes = tuple(_execution_mode(item) for item in self.allowed_execution_modes)
        if not modes:
            raise ValueError("allowed_execution_modes cannot be empty")
        if len(set(modes)) != len(modes):
            raise ValueError("allowed_execution_modes must be unique")
        object.__setattr__(self, "allowed_execution_modes", modes)
        default = _execution_mode(self.default_execution_mode)
        if default not in modes:
            raise ValueError("default_execution_mode must be allowed")
        object.__setattr__(self, "default_execution_mode", default)
        order_types = tuple(_order_type(item) for item in self.allowed_entry_order_types)
        if not order_types:
            raise ValueError("allowed_entry_order_types cannot be empty")
        if any(item not in {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT} for item in order_types):
            raise ValueError("allowed_entry_order_types supports MARKET, LIMIT and STOP_LIMIT only")
        object.__setattr__(self, "allowed_entry_order_types", order_types)
        _positive_int(self.maximum_decision_age_seconds, "maximum_decision_age_seconds")
        _positive_int(self.maximum_plan_validity_seconds, "maximum_plan_validity_seconds")
        for name in ("maximum_entry_slippage_points", "maximum_entry_slippage_percentage", "maximum_limit_offset_points"):
            value = getattr(self, name)
            if value is not None:
                _non_negative_real(value, name)
        object.__setattr__(self, "minimum_limit_offset_points", _non_negative_real(self.minimum_limit_offset_points, "minimum_limit_offset_points"))
        object.__setattr__(self, "price_tick_by_instrument", _canonical_ticks(self.price_tick_by_instrument))
        if self.allow_quantity_increase:
            raise ValueError("Trade Execution Policy V1 does not allow quantity increases")
        if self.paper_only and any(str(item).strip().lower() == "live" for item in modes):
            raise ValueError("paper_only policy cannot allow live execution")

    def tick_size_for(self, instrument: str) -> float | None:
        normalized = _instrument(instrument)
        for item in self.price_tick_by_instrument:
            if item.instrument == normalized:
                return item.tick_size
        return None

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    instrument: str
    timestamp: datetime
    risk_decision: object
    execution_mode: ExecutionMode | str | None = None
    requested_order_type: OrderType | str = OrderType.LIMIT
    requested_entry_price: float | None = None
    market_reference_price: float | None = None
    requested_quantity: int | None = None
    manual_approval: bool = False
    signal_id: str | None = None
    strategy_id: str | None = None
    client_request_id: str | None = None
    existing_active_plan_ids: tuple[str, ...] = ()
    limit_offset_points: float | None = None
    trigger_price: float | None = None
    valid_until: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY
    time_in_force: str = "DAY"
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        _aware(self.timestamp, "timestamp")
        if self.execution_mode is not None:
            object.__setattr__(self, "execution_mode", _request_execution_mode(self.execution_mode))
        object.__setattr__(self, "requested_order_type", _order_type(self.requested_order_type))
        for name in ("requested_entry_price", "market_reference_price", "limit_offset_points", "trigger_price"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive_real(value, name) if name != "limit_offset_points" else _non_negative_real(value, name))
        if self.requested_quantity is not None:
            _positive_int(self.requested_quantity, "requested_quantity")
        if type(self.manual_approval) is not bool:
            raise TypeError("manual_approval must be bool")
        object.__setattr__(self, "signal_id", _optional_text(self.signal_id))
        object.__setattr__(self, "strategy_id", _optional_text(self.strategy_id))
        object.__setattr__(self, "client_request_id", _optional_text(self.client_request_id))
        object.__setattr__(self, "existing_active_plan_ids", tuple(_text(item, "existing_active_plan_id") for item in self.existing_active_plan_ids))
        if self.valid_until is not None:
            _aware(self.valid_until, "valid_until")
            if self.valid_until <= self.timestamp:
                raise ValueError("valid_until must be after timestamp")
        if self.product_type is not ProductType.INTRADAY:
            raise ValueError("Trade Execution Policy V1 supports only intraday product type")
        object.__setattr__(self, "time_in_force", _text(self.time_in_force, "time_in_force").upper())
        object.__setattr__(self, "notes", _optional_text(self.notes))

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


@dataclass(frozen=True, slots=True)
class ProtectiveOrderPlan:
    purpose: ProtectiveOrderPurpose
    side: OrderSide
    order_type: OrderType
    quantity: int
    trigger_price: float | None
    limit_price: float | None
    reduce_only: bool
    parent_execution_plan_id: str
    status: ProtectiveOrderStatus = ProtectiveOrderStatus.PLANNED

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, ProtectiveOrderPurpose):
            raise TypeError("purpose must be ProtectiveOrderPurpose")
        if not isinstance(self.side, OrderSide):
            raise TypeError("side must be OrderSide")
        if self.order_type not in {OrderType.LIMIT, OrderType.STOP_LIMIT}:
            raise ValueError("protective order_type must be LIMIT or STOP_LIMIT")
        _positive_int(self.quantity, "quantity")
        if self.trigger_price is not None:
            object.__setattr__(self, "trigger_price", _positive_real(self.trigger_price, "trigger_price"))
        if self.limit_price is not None:
            object.__setattr__(self, "limit_price", _positive_real(self.limit_price, "limit_price"))
        if type(self.reduce_only) is not bool or not self.reduce_only:
            raise ValueError("protective plans must be reduce_only")
        _text(self.parent_execution_plan_id, "parent_execution_plan_id")
        if not isinstance(self.status, ProtectiveOrderStatus):
            raise TypeError("status must be ProtectiveOrderStatus")


@dataclass(frozen=True, slots=True)
class ExecutionFinding:
    finding_id: str
    timestamp: datetime
    severity: ExecutionSeverity
    reason_code: ExecutionReasonCode
    message: str
    field_name: str | None = None
    observed_value: str | None = None
    limit_value: str | None = None
    occurrence_count: int = 1

    def __post_init__(self) -> None:
        _text(self.finding_id, "finding_id")
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.severity, ExecutionSeverity):
            raise TypeError("severity must be ExecutionSeverity")
        if not isinstance(self.reason_code, ExecutionReasonCode):
            raise TypeError("reason_code must be ExecutionReasonCode")
        object.__setattr__(self, "message", _text(self.message, "message"))
        for name in ("field_name", "observed_value", "limit_value"):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))
        _positive_int(self.occurrence_count, "occurrence_count")


@dataclass(frozen=True, slots=True)
class TradeExecutionPlan:
    execution_plan_id: str
    created_at: datetime
    valid_from: datetime
    valid_until: datetime
    instrument: str
    direction: TradeDirection
    entry_side: OrderSide
    execution_mode: ExecutionMode
    entry_order_type: OrderType
    entry_quantity: int
    entry_limit_price: float | None
    entry_trigger_price: float | None
    market_reference_price: float
    risk_decision_id: str
    risk_decision_fingerprint: str
    signal_id: str
    strategy_id: str
    client_request_id: str
    stop_plan: ProtectiveOrderPlan | None
    target_plan: ProtectiveOrderPlan | None
    manual_approval_required: bool
    manual_approval_present: bool
    routing_target: ExecutionRoutingTarget
    status: ExecutionPlanStatus
    decision_status: ExecutionDecisionStatus
    primary_reason: ExecutionReasonCode
    findings: tuple[ExecutionFinding, ...]
    policy_fingerprint: str
    request_fingerprint: str
    input_fingerprint: str
    broker_submission_allowed: bool = False
    broker_order_calls: int = 0

    def __post_init__(self) -> None:
        _text(self.execution_plan_id, "execution_plan_id")
        for name in ("created_at", "valid_from", "valid_until"):
            _aware(getattr(self, name), name)
        if not (self.valid_from <= self.created_at < self.valid_until):
            raise ValueError("valid_from <= created_at < valid_until is required")
        object.__setattr__(self, "instrument", _instrument(self.instrument))
        if not isinstance(self.direction, TradeDirection) or self.direction is TradeDirection.NONE:
            raise ValueError("direction must be bullish or bearish")
        if not isinstance(self.entry_side, OrderSide):
            raise TypeError("entry_side must be OrderSide")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be ExecutionMode")
        if not isinstance(self.entry_order_type, OrderType):
            raise TypeError("entry_order_type must be OrderType")
        _positive_int(self.entry_quantity, "entry_quantity")
        for name in ("entry_limit_price", "entry_trigger_price"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive_real(value, name))
        object.__setattr__(self, "market_reference_price", _positive_real(self.market_reference_price, "market_reference_price"))
        for name in ("risk_decision_id", "risk_decision_fingerprint", "signal_id", "strategy_id", "client_request_id", "policy_fingerprint", "request_fingerprint", "input_fingerprint"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.stop_plan is not None and not isinstance(self.stop_plan, ProtectiveOrderPlan):
            raise TypeError("stop_plan must be ProtectiveOrderPlan or None")
        if self.target_plan is not None and not isinstance(self.target_plan, ProtectiveOrderPlan):
            raise TypeError("target_plan must be ProtectiveOrderPlan or None")
        if type(self.manual_approval_required) is not bool or type(self.manual_approval_present) is not bool:
            raise TypeError("manual approval fields must be bool")
        if not isinstance(self.routing_target, ExecutionRoutingTarget):
            raise TypeError("routing_target must be ExecutionRoutingTarget")
        if not isinstance(self.status, ExecutionPlanStatus):
            raise TypeError("status must be ExecutionPlanStatus")
        if not isinstance(self.decision_status, ExecutionDecisionStatus):
            raise TypeError("decision_status must be ExecutionDecisionStatus")
        if not isinstance(self.primary_reason, ExecutionReasonCode):
            raise TypeError("primary_reason must be ExecutionReasonCode")
        object.__setattr__(self, "findings", tuple(self.findings))
        if self.broker_submission_allowed is not False or self.broker_order_calls != 0:
            raise ValueError("broker submission is not allowed in Trade Execution Policy V1")


@dataclass(frozen=True, slots=True)
class ExecutionEngineSnapshot:
    enabled: bool
    lifecycle_state: ExecutionLifecycleState
    last_plan: TradeExecutionPlan | None
    evaluation_count: int
    approved_count: int
    rejected_count: int
    locked_count: int
    expired_count: int
    active_plan_ids: tuple[str, ...]
    findings: tuple[ExecutionFinding, ...]
    broker_order_calls: int = 0

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be bool")
        if not isinstance(self.lifecycle_state, ExecutionLifecycleState):
            raise TypeError("lifecycle_state must be ExecutionLifecycleState")
        if self.last_plan is not None and not isinstance(self.last_plan, TradeExecutionPlan):
            raise TypeError("last_plan must be TradeExecutionPlan or None")
        for name in ("evaluation_count", "approved_count", "rejected_count", "locked_count", "expired_count"):
            _non_negative_int(getattr(self, name), name)
        object.__setattr__(self, "active_plan_ids", tuple(_text(item, "active_plan_id") for item in self.active_plan_ids))
        object.__setattr__(self, "findings", tuple(self.findings[-50:]))
        if self.broker_order_calls != 0:
            raise ValueError("broker_order_calls must remain zero")


def build_valid_until(timestamp: datetime, policy: ExecutionPolicy, requested: datetime | None = None) -> datetime:
    maximum = timestamp + timedelta(seconds=policy.maximum_plan_validity_seconds)
    return min(requested, maximum) if requested is not None else maximum


def _canonical_ticks(value) -> tuple[InstrumentTickSize, ...]:
    if isinstance(value, dict):
        items = tuple(InstrumentTickSize(str(key), tick) for key, tick in value.items())
    else:
        items = tuple(value)
        if any(not isinstance(item, InstrumentTickSize) for item in items):
            raise TypeError("price_tick_by_instrument must contain InstrumentTickSize values")
    names = [item.instrument for item in items]
    if len(set(names)) != len(names):
        raise ValueError("price_tick_by_instrument must be unique")
    return tuple(sorted(items, key=lambda item: item.instrument))


def _model_payload(value):
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
    return value


def _fingerprint(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _positive_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def _non_negative_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    text = value.strip()
    return text[:500]


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _text(value, "text")


def _instrument(value: str | RuntimeInstrument) -> str:
    raw = value.value if isinstance(value, RuntimeInstrument) else value
    if not isinstance(raw, str):
        raise TypeError("instrument must be text")
    normalized = raw.strip().upper()
    if normalized not in SUPPORTED_INSTRUMENTS:
        raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
    return normalized


def _execution_mode(value: ExecutionMode | str) -> ExecutionMode:
    if isinstance(value, ExecutionMode):
        return value
    if not isinstance(value, str):
        raise TypeError("execution_mode must be ExecutionMode or text")
    normalized = value.strip().lower()
    if normalized == "live":
        raise ValueError("live execution is blocked in Trade Execution Policy V1")
    try:
        return ExecutionMode(normalized)
    except ValueError as exc:
        raise ValueError("unsupported execution mode") from exc


def _request_execution_mode(value: ExecutionMode | str) -> ExecutionMode | str:
    if isinstance(value, ExecutionMode):
        return value
    if not isinstance(value, str):
        raise TypeError("execution_mode must be ExecutionMode or text")
    normalized = value.strip().lower()
    if normalized == "live":
        return "live"
    return _execution_mode(normalized)


def _order_type(value: OrderType | str) -> OrderType:
    if isinstance(value, OrderType):
        return value
    if not isinstance(value, str):
        raise TypeError("order_type must be OrderType or text")
    try:
        return OrderType(value.strip().lower())
    except ValueError as exc:
        raise ValueError("unsupported order type") from exc
