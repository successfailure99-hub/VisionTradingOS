"""
ADR Engine V1 enums.
"""

from enum import Enum


class ADRExpansionState(Enum):
    NOT_STARTED = "not_started"
    NORMAL = "normal"
    EXPANDING = "expanding"
    ADR_REACHED = "adr_reached"
    ADR_EXCEEDED = "adr_exceeded"
    EXTREME_EXPANSION = "extreme_expansion"


class ADRExhaustionState(Enum):
    NOT_STARTED = "not_started"
    NOT_EXHAUSTED = "not_exhausted"
    EXHAUSTED = "exhausted"
    EXTREME = "extreme"

