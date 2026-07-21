"""
Trade Decision Authorization Gate V1 enumerations.
"""

from enum import Enum


class TradeAuthorizationDecision(str, Enum):
    AUTHORIZE = "authorize"
    REDUCE = "reduce"
    BLOCK = "block"


class TradeAuthorizationLifecycle(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"


class TradeAuthorizationReason(str, Enum):
    AUTHORIZED = "authorized"
    CONFIDENCE_REDUCED = "confidence_reduced"
    CONFIDENCE_BLOCKED = "confidence_blocked"
    RISK_REDUCED = "risk_reduced"
    RISK_BLOCKED = "risk_blocked"
    POLICY_REDUCED = "policy_reduced"
    POLICY_BLOCKED = "policy_blocked"
    DIRECTION_MISMATCH = "direction_mismatch"
    INSTRUMENT_MISMATCH = "instrument_mismatch"
    STALE_INPUT = "stale_input"
    INVALID_INPUT = "invalid_input"
