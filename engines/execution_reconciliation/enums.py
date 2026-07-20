"""
Execution Reconciliation Engine V1 enumerations.
"""

from enum import Enum


class ReconciliationLifecycleState(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    LOCKED = "locked"
    FAILED = "failed"
    STOPPED = "stopped"


class ReconciliationStatus(str, Enum):
    CONSISTENT = "consistent"
    CONSISTENT_WITH_WARNINGS = "consistent_with_warnings"
    INCONSISTENT = "inconsistent"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    FAILED = "failed"


class ReconciliationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReconciliationBoundary(str, Enum):
    EXECUTION_PLAN = "execution_plan"
    COORDINATOR_RECEIPT = "coordinator_receipt"
    ORDER_MANAGEMENT = "order_management"
    PAPER_TRADING = "paper_trading"
    POSITION = "position"
    CROSS_BOUNDARY = "cross_boundary"


class ReconciliationReasonCode(str, Enum):
    CONSISTENT = "consistent"
    ENGINE_STOPPED = "engine_stopped"
    ENGINE_LOCKED = "engine_locked"
    INVALID_REQUEST = "invalid_request"
    INVALID_EXECUTION_PLAN = "invalid_execution_plan"
    INVALID_RECEIPT = "invalid_receipt"
    INVALID_ORDER_STATE = "invalid_order_state"
    INVALID_MANAGED_SUBMISSION = "invalid_managed_submission"
    INVALID_POSITION_STATE = "invalid_position_state"
    INSTRUMENT_MISMATCH = "instrument_mismatch"
    EXECUTION_PLAN_ID_MISMATCH = "execution_plan_id_mismatch"
    EXECUTION_PLAN_FINGERPRINT_MISMATCH = "execution_plan_fingerprint_mismatch"
    RECEIPT_NOT_FOUND = "receipt_not_found"
    ORDER_NOT_FOUND = "order_not_found"
    ENTRY_ORDER_NOT_FOUND = "entry_order_not_found"
    STOP_ORDER_NOT_FOUND = "stop_order_not_found"
    TARGET_ORDER_NOT_FOUND = "target_order_not_found"
    MANAGED_SUBMISSION_NOT_FOUND = "managed_submission_not_found"
    POSITION_NOT_FOUND = "position_not_found"
    ORPHANED_RECEIPT = "orphaned_receipt"
    ORPHANED_ORDER = "orphaned_order"
    ORPHANED_MANAGED_SUBMISSION = "orphaned_managed_submission"
    DUPLICATE_ORDER_IDENTITY = "duplicate_order_identity"
    DUPLICATE_SUBMISSION_IDENTITY = "duplicate_submission_identity"
    ORDER_PURPOSE_MISMATCH = "order_purpose_mismatch"
    ORDER_SIDE_MISMATCH = "order_side_mismatch"
    ORDER_TYPE_MISMATCH = "order_type_mismatch"
    ORDER_QUANTITY_MISMATCH = "order_quantity_mismatch"
    ORDER_LIMIT_PRICE_MISMATCH = "order_limit_price_mismatch"
    ORDER_TRIGGER_PRICE_MISMATCH = "order_trigger_price_mismatch"
    FILLED_QUANTITY_MISMATCH = "filled_quantity_mismatch"
    REMAINING_QUANTITY_MISMATCH = "remaining_quantity_mismatch"
    ORDER_STATUS_MISMATCH = "order_status_mismatch"
    MANAGED_STATUS_MISMATCH = "managed_status_mismatch"
    TERMINAL_STATE_REGRESSION = "terminal_state_regression"
    PROTECTION_CREATED_BEFORE_ENTRY_FILL = "protection_created_before_entry_fill"
    MISSING_STOP_PROTECTION = "missing_stop_protection"
    MISSING_TARGET_PROTECTION = "missing_target_protection"
    PROTECTIVE_QUANTITY_MISMATCH = "protective_quantity_mismatch"
    PROTECTIVE_REDUCE_ONLY_MISMATCH = "protective_reduce_only_mismatch"
    OPPOSITE_PROTECTION_NOT_CANCELLED = "opposite_protection_not_cancelled"
    CANCELLED_RECEIPT_HAS_ACTIVE_ORDER = "cancelled_receipt_has_active_order"
    COMPLETED_RECEIPT_HAS_OPEN_POSITION = "completed_receipt_has_open_position"
    ACTIVE_RECEIPT_HAS_CLOSED_POSITION = "active_receipt_has_closed_position"
    FILLED_ENTRY_WITHOUT_POSITION = "filled_entry_without_position"
    POSITION_QUANTITY_MISMATCH = "position_quantity_mismatch"
    POSITION_INSTRUMENT_MISMATCH = "position_instrument_mismatch"
    STALE_RECONCILIATION_INPUT = "stale_reconciliation_input"
    INTERNAL_RECONCILIATION_ERROR = "internal_reconciliation_error"
