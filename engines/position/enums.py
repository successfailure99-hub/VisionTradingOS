"""
Position Management Engine V1 enumerations.
"""

from enum import Enum


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class PositionUpdateType(str, Enum):
    OPEN = "open"
    ADD = "add"
    REDUCE = "reduce"
    CLOSE = "close"
    REVERSE = "reverse"
    MARK = "mark"
