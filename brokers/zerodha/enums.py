"""
Zerodha Broker Adapter V1 enumerations.
"""

from enum import Enum


class BrokerExecutionMode(str, Enum):
    DRY_RUN = "dry_run"
    CLIENT = "client"


class BrokerAction(str, Enum):
    PLACE = "place"
    MODIFY = "modify"
    CANCEL = "cancel"


class BrokerResultStatus(str, Enum):
    DRY_RUN = "dry_run"
    ACCEPTED = "accepted"
    FAILED = "failed"


class ZerodhaOrderStatus(str, Enum):
    PUT_ORDER_REQ_RECEIVED = "PUT ORDER REQ RECEIVED"
    VALIDATION_PENDING = "VALIDATION PENDING"
    OPEN_PENDING = "OPEN PENDING"
    OPEN = "OPEN"
    TRIGGER_PENDING = "TRIGGER PENDING"
    MODIFY_VALIDATION_PENDING = "MODIFY VALIDATION PENDING"
    MODIFY_PENDING = "MODIFY PENDING"
    MODIFIED = "MODIFIED"
    CANCEL_PENDING = "CANCEL PENDING"
    CANCELLED = "CANCELLED"
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
