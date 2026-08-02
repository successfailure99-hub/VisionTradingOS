"""
Read-only broker account synchronization enums.
"""

from enum import Enum


class BrokerSessionState(str, Enum):
    UNAUTHENTICATED = "unauthenticated"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    TOKEN_EXPIRED = "token_expired"
    SESSION_INVALID = "session_invalid"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class BrokerConnectionState(str, Enum):
    DISABLED = "disabled"
    WAITING = "waiting"
    READY = "ready"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class BrokerRuntimeStatus(str, Enum):
    READY = "READY"
    WAITING = "WAITING"
    STALE = "STALE"
    RECONNECTING = "RECONNECTING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class BrokerMutationMode(str, Enum):
    DISABLED = "DISABLED"


class BrokerReconciliationStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    MATCHED = "matched"
    MISMATCHED = "mismatched"
    BROKER_UNAVAILABLE = "broker_unavailable"
    PAPER_ONLY = "paper_only"
    BROKER_ONLY = "broker_only"