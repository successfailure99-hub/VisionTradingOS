"""
Risk Engine V1 enumerations.
"""

from enum import Enum


class RiskDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RiskTier(str, Enum):
    STANDARD = "standard"
    REDUCED = "reduced"
    BLOCKED = "blocked"


class RiskRejectionReason(str, Enum):
    NONE = "none"
    STRATEGY_NO_TRADE = "strategy_no_trade"
    INVALID_TRADE_DIRECTION = "invalid_trade_direction"
    INVALID_PRICE_STRUCTURE = "invalid_price_structure"
    DAILY_LOSS_LIMIT_REACHED = "daily_loss_limit_reached"
    CONSECUTIVE_LOSS_LIMIT_REACHED = "consecutive_loss_limit_reached"
    DAILY_TRADE_LIMIT_REACHED = "daily_trade_limit_reached"
    INSUFFICIENT_RISK_BUDGET = "insufficient_risk_budget"
    REQUESTED_SIZE_EXCEEDS_LIMIT = "requested_size_exceeds_limit"
    REWARD_RISK_BELOW_MINIMUM = "reward_risk_below_minimum"


class RiskReductionReason(str, Enum):
    NONE = "none"
    DAILY_DRAWDOWN = "daily_drawdown"
    RECENT_LOSSES = "recent_losses"
    BOTH = "both"
