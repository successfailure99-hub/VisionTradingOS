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


class OptionContractSelectionStatus(str, Enum):
    VALID = "valid"
    REJECTED = "rejected"


class OptionContractRejectionReason(str, Enum):
    OUTSIDE_UNIVERSE = "outside_universe"
    MISSING_MARKET_STRIKE = "missing_market_strike"
    MISSING_OPTION_LEG = "missing_option_leg"
    INVALID_PREMIUM = "invalid_premium"
    OI_BELOW_MINIMUM = "oi_below_minimum"
    VOLUME_BELOW_MINIMUM = "volume_below_minimum"
    SPREAD_TOO_WIDE = "spread_too_wide"
    VALID = "valid"


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
