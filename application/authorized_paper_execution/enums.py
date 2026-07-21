"""
Authorized Paper Execution Handoff V1 enumerations.
"""

from enum import Enum


class AuthorizedPaperHandoffDecision(str, Enum):
    EXECUTE = "execute"
    HOLD_REDUCTION_REQUIRED = "hold_reduction_required"
    REJECT = "reject"


class AuthorizedPaperHandoffReason(str, Enum):
    AUTHORIZED = "authorized"
    AUTHORIZATION_REDUCED = "authorization_reduced"
    AUTHORIZATION_BLOCKED = "authorization_blocked"
    INVALID_INPUT = "invalid_input"
    INSTRUMENT_MISMATCH = "instrument_mismatch"
    DIRECTION_MISMATCH = "direction_mismatch"
    PLAN_MISMATCH = "plan_mismatch"
    STALE_AUTHORIZATION = "stale_authorization"
    STALE_EXECUTION_PLAN = "stale_execution_plan"
    PLAN_NOT_PAPER = "plan_not_paper"
    PLAN_NOT_EXECUTABLE = "plan_not_executable"
    DUPLICATE_EXECUTION = "duplicate_execution"
    PAPER_EXECUTION_FAILED = "paper_execution_failed"


class AuthorizedPaperHandoffLifecycle(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"
