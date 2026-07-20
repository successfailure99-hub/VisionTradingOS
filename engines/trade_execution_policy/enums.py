"""
Trade Execution Policy Engine V1 enumerations.
"""

from enum import Enum


class ExecutionDecisionStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    LOCKED = "locked"
    INVALID = "invalid"
    EXPIRED = "expired"


class ExecutionLifecycleState(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    LOCKED = "locked"
    STOPPED = "stopped"
    FAILED = "failed"


class ExecutionMode(str, Enum):
    PLAN_ONLY = "plan_only"
    PAPER = "paper"


class ExecutionPlanStatus(str, Enum):
    PREPARED = "prepared"
    AWAITING_MANUAL_APPROVAL = "awaiting_manual_approval"
    READY_FOR_PAPER = "ready_for_paper"
    LOCKED = "locked"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ExecutionRoutingTarget(str, Enum):
    PLAN_ONLY = "plan_only"
    PAPER_TRADING = "paper_trading"


class ProtectiveOrderPurpose(str, Enum):
    STOP_LOSS = "stop_loss"
    TARGET = "target"


class ProtectiveOrderStatus(str, Enum):
    PLANNED = "planned"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ExecutionSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ExecutionReasonCode(str, Enum):
    APPROVED = "approved"
    POLICY_DISABLED = "policy_disabled"
    INVALID_REQUEST = "invalid_request"
    INVALID_RISK_DECISION = "invalid_risk_decision"
    RISK_NOT_APPROVED = "risk_not_approved"
    RISK_DECISION_EXPIRED = "risk_decision_expired"
    RISK_DECISION_MISMATCH = "risk_decision_mismatch"
    UNSUPPORTED_INSTRUMENT = "unsupported_instrument"
    UNSUPPORTED_EXECUTION_MODE = "unsupported_execution_mode"
    LIVE_EXECUTION_BLOCKED = "live_execution_blocked"
    UNSUPPORTED_ORDER_TYPE = "unsupported_order_type"
    MARKET_ORDER_BLOCKED = "market_order_blocked"
    MISSING_MANUAL_APPROVAL = "missing_manual_approval"
    INVALID_QUANTITY = "invalid_quantity"
    QUANTITY_MISMATCH = "quantity_mismatch"
    QUANTITY_INCREASE_BLOCKED = "quantity_increase_blocked"
    ZERO_QUANTITY = "zero_quantity"
    INVALID_ENTRY_PRICE = "invalid_entry_price"
    INVALID_TRIGGER_PRICE = "invalid_trigger_price"
    INVALID_LIMIT_PRICE = "invalid_limit_price"
    INVALID_STOP_PRICE = "invalid_stop_price"
    INVALID_TARGET_PRICE = "invalid_target_price"
    PRICE_NOT_TICK_ALIGNED = "price_not_tick_aligned"
    SLIPPAGE_LIMIT_EXCEEDED = "slippage_limit_exceeded"
    MISSING_STOP_PLAN = "missing_stop_plan"
    MISSING_TARGET_PLAN = "missing_target_plan"
    INVALID_STOP_GEOMETRY = "invalid_stop_geometry"
    INVALID_TARGET_GEOMETRY = "invalid_target_geometry"
    DUPLICATE_EXECUTION_PLAN = "duplicate_execution_plan"
    SIGNAL_ALREADY_HAS_PLAN = "signal_already_has_plan"
    RISK_DECISION_ALREADY_HAS_PLAN = "risk_decision_already_has_plan"
    REQUEST_EXPIRED = "request_expired"
    PLAN_VALIDITY_INVALID = "plan_validity_invalid"
    PAPER_ROUTING_REQUIRED = "paper_routing_required"
    ENGINE_LOCKED = "engine_locked"
    ENGINE_STOPPED = "engine_stopped"
    INTERNAL_VALIDATION_ERROR = "internal_validation_error"
