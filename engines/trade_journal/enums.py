"""
Trade Journal Engine V1 enumerations.
"""

from enum import Enum


class TradeOutcome(str, Enum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"


class TradeCompliance(str, Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"


class TradeExitType(str, Enum):
    TARGET = "target"
    STOP = "stop"
    MANUAL = "manual"
    REVERSAL = "reversal"
    UNKNOWN = "unknown"


class JournalFilter(str, Enum):
    ALL = "all"
    WINNERS = "winners"
    LOSERS = "losers"
    BREAKEVEN = "breakeven"
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
