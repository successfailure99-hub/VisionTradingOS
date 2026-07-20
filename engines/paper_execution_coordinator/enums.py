"""
Paper Execution Coordinator V1 enumerations.
"""

from enum import Enum


class CoordinatorLifecycleState(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    LOCKED = "locked"
    FAILED = "failed"
    STOPPED = "stopped"


class PaperExecutionStatus(str, Enum):
    ACCEPTED = "accepted"
    ENTRY_ORDER_CREATED = "entry_order_created"
    ENTRY_SUBMITTED = "entry_submitted"
    ENTRY_PARTIALLY_FILLED = "entry_partially_filled"
    ENTRY_FILLED = "entry_filled"
    PROTECTIVE_ORDERS_CREATED = "protective_orders_created"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


class PaperExecutionDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    INVALID = "invalid"
    LOCKED = "locked"
    EXPIRED = "expired"
    DUPLICATE = "duplicate"


class PaperExecutionReasonCode(str, Enum):
    APPROVED = "approved"
    COORDINATOR_STOPPED = "coordinator_stopped"
    COORDINATOR_LOCKED = "coordinator_locked"
    INVALID_REQUEST = "invalid_request"
    INVALID_EXECUTION_PLAN = "invalid_execution_plan"
    PLAN_NOT_APPROVED = "plan_not_approved"
    PLAN_NOT_READY_FOR_PAPER = "plan_not_ready_for_paper"
    PLAN_EXPIRED = "plan_expired"
    PLAN_INSTRUMENT_MISMATCH = "plan_instrument_mismatch"
    UNSUPPORTED_INSTRUMENT = "unsupported_instrument"
    UNSUPPORTED_ROUTING_TARGET = "unsupported_routing_target"
    UNSUPPORTED_EXECUTION_MODE = "unsupported_execution_mode"
    BROKER_SUBMISSION_BLOCKED = "broker_submission_blocked"
    DUPLICATE_EXECUTION = "duplicate_execution"
    ORDER_CREATION_FAILED = "order_creation_failed"
    PAPER_SUBMISSION_FAILED = "paper_submission_failed"
    ENTRY_ORDER_NOT_FOUND = "entry_order_not_found"
    ENTRY_NOT_FILLED = "entry_not_filled"
    INVALID_PROTECTIVE_PLAN = "invalid_protective_plan"
    PROTECTIVE_ORDER_CREATION_FAILED = "protective_order_creation_failed"
    PROTECTIVE_PAPER_SUBMISSION_FAILED = "protective_paper_submission_failed"
    INCONSISTENT_ORDER_STATE = "inconsistent_order_state"
    INTERNAL_COORDINATION_ERROR = "internal_coordination_error"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class PaperExecutionSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CoordinatedOrderPurpose(str, Enum):
    ENTRY = "entry"
    STOP_LOSS = "stop_loss"
    TARGET = "target"
