"""
Order Management Engine V1 enumerations.
"""

from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


class ProductType(str, Enum):
    INTRADAY = "intraday"


class OrderStatus(str, Enum):
    PENDING_SUBMISSION = "pending_submission"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderCommandType(str, Enum):
    CREATE = "create"
    ACKNOWLEDGE = "acknowledge"
    MODIFY = "modify"
    FILL = "fill"
    CANCEL = "cancel"
    REJECT = "reject"


class OrderRejectionReason(str, Enum):
    NONE = "none"
    RISK_NOT_APPROVED = "risk_not_approved"
    INVALID_DIRECTION = "invalid_direction"
    QUANTITY_MISMATCH = "quantity_mismatch"
    PRICE_MISMATCH = "price_mismatch"
    INVALID_ORDER_TYPE_FIELDS = "invalid_order_type_fields"
    INVALID_TRANSITION = "invalid_transition"
    DUPLICATE_ORDER_ID = "duplicate_order_id"
    OVERFILL = "overfill"
    TERMINAL_ORDER = "terminal_order"
    BROKER_REJECTED = "broker_rejected"
