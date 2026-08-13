"""
Deterministic vocabulary for paper-only directional option selling.
"""

from enum import Enum


class OptionPaperExecutionStyle(str, Enum):
    UNDERLYING_PAPER = "underlying_paper"
    DIRECTIONAL_OPTION_SELLING_PAPER = "directional_option_selling_paper"


class OptionPaperUnderlyingDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class OptionPaperTransactionType(str, Enum):
    SELL = "sell"


class OptionPaperMoneyness(str, Enum):
    ATM = "atm"
    ITM = "itm"
    OTM = "otm"


class OptionPaperSelectionPolicy(str, Enum):
    ATM_FIRST = "atm_first"
    PREFERRED_ITM_DEPTH = "preferred_itm_depth"
    BEST_LIQUID_VALID = "best_liquid_valid"


class OptionPaperRiskDecision(str, Enum):
    APPROVED = "approved"
    APPROVED_REDUCED = "approved_reduced"
    REJECTED = "rejected"
    NOT_APPLICABLE = "not_applicable"


class OptionPaperPositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    TARGET_HIT = "target_hit"
    STOP_HIT = "stop_hit"
    INVALIDATED = "invalidated"
    NOT_OPEN = "not_open"
