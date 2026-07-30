"""
Vision Method runtime adapter deterministic vocabulary.
"""

from enum import Enum


class TradeCandidateDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


class TradeCandidateState(str, Enum):
    LONG = "long"
    SHORT = "short"
    WAITING_LONG = "waiting_long"
    WAITING_SHORT = "waiting_short"
    NO_CANDIDATE = "no_candidate"
