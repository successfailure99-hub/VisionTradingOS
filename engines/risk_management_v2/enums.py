"""
Risk Management Engine V2 enumerations.
"""

from enum import Enum


class RiskDecision(str, Enum):
    APPROVED = "approved"
    APPROVED_REDUCED = "approved_reduced"
    REJECTED = "rejected"
    WAIT = "wait"
    INSUFFICIENT_DATA = "insufficient_data"


class RiskStatus(str, Enum):
    READY_FOR_EXECUTION_REVIEW = "ready_for_execution_review"
    REDUCED_FOR_EXECUTION_REVIEW = "reduced_for_execution_review"
    BLOCKED_BY_STRATEGY = "blocked_by_strategy"
    BLOCKED_BY_DAILY_LOSS = "blocked_by_daily_loss"
    BLOCKED_BY_DRAWDOWN = "blocked_by_drawdown"
    BLOCKED_BY_EXPOSURE = "blocked_by_exposure"
    BLOCKED_BY_POSITION_LIMIT = "blocked_by_position_limit"
    BLOCKED_BY_TRADE_LIMIT = "blocked_by_trade_limit"
    BLOCKED_BY_INVALIDATION = "blocked_by_invalidation"
    BLOCKED_BY_CAPITAL = "blocked_by_capital"
    BLOCKED_BY_DATA = "blocked_by_data"


class RiskSeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class RiskRuleType(str, Enum):
    STRATEGY_ELIGIBILITY = "strategy_eligibility"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    ACCOUNT_DRAWDOWN_LIMIT = "account_drawdown_limit"
    PER_TRADE_RISK_LIMIT = "per_trade_risk_limit"
    TOTAL_EXPOSURE_LIMIT = "total_exposure_limit"
    INSTRUMENT_EXPOSURE_LIMIT = "instrument_exposure_limit"
    MAX_POSITION_QUANTITY = "max_position_quantity"
    MAX_TRADES_PER_DAY = "max_trades_per_day"
    CONSECUTIVE_LOSS_LIMIT = "consecutive_loss_limit"
    INVALIDATION_REQUIRED = "invalidation_required"
    OBJECTIVE_REQUIRED = "objective_required"
    MINIMUM_REWARD_RISK = "minimum_reward_risk"
    CAPITAL_AVAILABLE = "capital_available"


class RiskRuleResult(str, Enum):
    PASSED = "passed"
    REDUCED = "reduced"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class PositionSizingMode(str, Enum):
    FIXED_FRACTIONAL = "fixed_fractional"
    FIXED_QUANTITY_CAP = "fixed_quantity_cap"
    MINIMUM_OF_LIMITS = "minimum_of_limits"


class RiskDecisionChange(str, Enum):
    INITIAL = "initial"
    BECAME_APPROVED = "became_approved"
    BECAME_REDUCED = "became_reduced"
    BECAME_REJECTED = "became_rejected"
    BECAME_WAIT = "became_wait"
    RISK_INCREASED = "risk_increased"
    RISK_DECREASED = "risk_decreased"
    UNCHANGED = "unchanged"
