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


class RiskDecisionStatus(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_REDUCED_SIZE = "approved_with_reduced_size"
    REJECTED = "rejected"
    LOCKED = "locked"
    INVALID = "invalid"


class RiskSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RiskLifecycleState(str, Enum):
    CREATED = "created"
    READY = "ready"
    ACTIVE = "active"
    LOCKED = "locked"
    STOPPED = "stopped"
    FAILED = "failed"


class RiskReasonCode(str, Enum):
    APPROVED = "approved"
    SIZE_REDUCED = "size_reduced"
    INVALID_PLAN = "invalid_plan"
    INVALID_STOP = "invalid_stop"
    STOP_TOO_WIDE = "stop_too_wide"
    STOP_TOO_TIGHT = "stop_too_tight"
    INSUFFICIENT_REWARD_RISK = "insufficient_reward_risk"
    RISK_PER_TRADE_EXCEEDED = "risk_per_trade_exceeded"
    DAILY_LOSS_LIMIT_REACHED = "daily_loss_limit_reached"
    DAILY_PROFIT_LOCK_ACTIVE = "daily_profit_lock_active"
    MAX_TRADES_REACHED = "max_trades_reached"
    CONSECUTIVE_LOSS_COOLDOWN = "consecutive_loss_cooldown"
    REVENGE_TRADING_LOCKOUT = "revenge_trading_lockout"
    MANUAL_LOCK_ACTIVE = "manual_lock_active"
    MANUAL_APPROVAL_REQUIRED = "manual_approval_required"
    EMERGENCY_LOCK_ACTIVE = "emergency_lock_active"
    OUTSIDE_TRADING_WINDOW = "outside_trading_window"
    LATE_ENTRY = "late_entry"
    FOMO_ENTRY = "fomo_entry"
    AVERAGING_DOWN_BLOCKED = "averaging_down_blocked"
    DUPLICATE_POSITION = "duplicate_position"
    INSTRUMENT_EXPOSURE_EXCEEDED = "instrument_exposure_exceeded"
    TOTAL_OPEN_RISK_EXCEEDED = "total_open_risk_exceeded"
    MAX_QUANTITY_EXCEEDED = "max_quantity_exceeded"
    MAX_LOTS_EXCEEDED = "max_lots_exceeded"
    INSUFFICIENT_CAPITAL = "insufficient_capital"
    MISSING_STOP_LOSS = "missing_stop_loss"
    MISSING_TARGET = "missing_target"
    INVALID_ENTRY_PRICE = "invalid_entry_price"
    INVALID_QUANTITY = "invalid_quantity"
    UNSUPPORTED_INSTRUMENT = "unsupported_instrument"
