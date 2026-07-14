"""
Strategy Decision Engine V2 enumerations.
"""

from enum import Enum


class StrategyAction(str, Enum):
    CONSIDER_LONG = "consider_long"
    CONSIDER_SHORT = "consider_short"
    WAIT = "wait"
    NO_TRADE = "no_trade"
    INSUFFICIENT_DATA = "insufficient_data"


class StrategySetupFamily(str, Enum):
    TREND_CONTINUATION = "trend_continuation"
    BREAKOUT_RETEST = "breakout_retest"
    BREAKDOWN_RETEST = "breakdown_retest"
    RANGE_BREAKOUT_WATCH = "range_breakout_watch"
    RANGE_BREAKDOWN_WATCH = "range_breakdown_watch"
    REVERSAL_WATCH = "reversal_watch"
    STRUCTURAL_RETEST = "structural_retest"
    NO_SETUP = "no_setup"


class StrategyDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
    NONE = "none"


class StrategySetupStatus(str, Enum):
    READY_FOR_RISK_REVIEW = "ready_for_risk_review"
    WAITING_FOR_TRIGGER = "waiting_for_trigger"
    WAITING_FOR_RETEST = "waiting_for_retest"
    BLOCKED_BY_CONFLICT = "blocked_by_conflict"
    BLOCKED_BY_READINESS = "blocked_by_readiness"
    BLOCKED_BY_CONVICTION = "blocked_by_conviction"
    INVALIDATED = "invalidated"
    NO_SETUP = "no_setup"


class StrategyTriggerType(str, Enum):
    CONFIRMED_BREAKOUT = "confirmed_breakout"
    CONFIRMED_BREAKDOWN = "confirmed_breakdown"
    BULLISH_RETEST_HOLD = "bullish_retest_hold"
    BEARISH_RETEST_REJECTION = "bearish_retest_rejection"
    STRUCTURE_CONTINUATION = "structure_continuation"
    RANGE_EXIT_CONFIRMATION = "range_exit_confirmation"
    NONE = "none"


class StrategyReferenceType(str, Enum):
    CURRENT_PRICE = "current_price"
    CAMARILLA_H3 = "camarilla_h3"
    CAMARILLA_H4 = "camarilla_h4"
    CAMARILLA_H5 = "camarilla_h5"
    CAMARILLA_H6 = "camarilla_h6"
    CAMARILLA_L3 = "camarilla_l3"
    CAMARILLA_L4 = "camarilla_l4"
    CAMARILLA_L5 = "camarilla_l5"
    CAMARILLA_L6 = "camarilla_l6"
    CPR_TC = "cpr_tc"
    CPR_PIVOT = "cpr_pivot"
    CPR_BC = "cpr_bc"
    VWAP = "vwap"
    OPTION_SUPPORT = "option_support"
    OPTION_RESISTANCE = "option_resistance"
    OPTION_MAX_PAIN = "option_max_pain"
    PRICE_ACTION_SWING_HIGH = "price_action_swing_high"
    PRICE_ACTION_SWING_LOW = "price_action_swing_low"


class StrategyInvalidationType(str, Enum):
    CLOSE_BACK_BELOW_LEVEL = "close_back_below_level"
    CLOSE_BACK_ABOVE_LEVEL = "close_back_above_level"
    BREAK_OF_STRUCTURE = "break_of_structure"
    PRIMARY_BIAS_REVERSAL = "primary_bias_reversal"
    CONFLICT_INCREASE = "conflict_increase"
    CONTEXT_STALE = "context_stale"
    NONE = "none"


class StrategyDecisionChange(str, Enum):
    INITIAL = "initial"
    SETUP_APPEARED = "setup_appeared"
    SETUP_STRENGTHENED = "setup_strengthened"
    SETUP_WEAKENED = "setup_weakened"
    TURNED_LONG = "turned_long"
    TURNED_SHORT = "turned_short"
    BECAME_WAIT = "became_wait"
    BECAME_NO_TRADE = "became_no_trade"
    SETUP_INVALIDATED = "setup_invalidated"
    UNCHANGED = "unchanged"


class StrategyDecisionQuality(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNAVAILABLE = "unavailable"
