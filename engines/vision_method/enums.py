"""
Vision Method V1 deterministic vocabulary.
"""

from enum import Enum


class VisionOpeningLocation(str, Enum):
    ABOVE_CPR = "above_cpr"
    INSIDE_CPR = "inside_cpr"
    BELOW_CPR = "below_cpr"


class VisionMarketRegime(str, Enum):
    TREND_DAY = "trend_day"
    RANGE_DAY = "range_day"
    EXPANSION_DAY = "expansion_day"
    COMPRESSION_DAY = "compression_day"
    TRANSITION_DAY = "transition_day"
    REVERSAL_DAY = "reversal_day"
    UNKNOWN = "unknown"


class VisionStructureState(str, Enum):
    UNKNOWN = "unknown"
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"


class VisionSwingType(str, Enum):
    HIGH = "high"
    LOW = "low"


class VisionStructureTrend(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"
    UNKNOWN = "unknown"


class VisionStructurePattern(str, Enum):
    HH = "hh"
    HL = "hl"
    LH = "lh"
    LL = "ll"
    UNKNOWN = "unknown"


class VisionOptionConfirmation(str, Enum):
    CONFIRMS = "confirms"
    PARTIAL = "partial"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"


class VisionCandidateState(str, Enum):
    OBSERVE = "observe"
    WAIT = "wait"
    PREPARE_LONG = "prepare_long"
    PREPARE_SHORT = "prepare_short"
    LONG_ELIGIBLE = "long_eligible"
    SHORT_ELIGIBLE = "short_eligible"
    AVOID = "avoid"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionCPRRelation(str, Enum):
    ABOVE_CPR = "above_cpr"
    INSIDE_CPR = "inside_cpr"
    BELOW_CPR = "below_cpr"


class VisionCamarillaZone(str, Enum):
    ABOVE_H6 = "above_h6"
    H5_H6 = "h5_h6"
    H4_H5 = "h4_h5"
    H3_H4 = "h3_h4"
    INSIDE_VALUE = "inside_value"
    L3_L4 = "l3_l4"
    L4_L5 = "l4_l5"
    L5_L6 = "l5_l6"
    BELOW_L6 = "below_l6"


class VisionPreviousDayRelation(str, Enum):
    ABOVE_PREVIOUS_HIGH = "above_previous_high"
    INSIDE_PREVIOUS_RANGE = "inside_previous_range"
    BELOW_PREVIOUS_LOW = "below_previous_low"


class VisionGapType(str, Enum):
    GAP_UP = "gap_up"
    GAP_DOWN = "gap_down"
    NO_GAP = "no_gap"


class VisionVWAPRelation(str, Enum):
    ABOVE_VWAP = "above_vwap"
    BELOW_VWAP = "below_vwap"
    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"
    RETEST = "retest"
    REJECT = "reject"
    FAR_ABOVE = "far_above"
    FAR_BELOW = "far_below"
    UNAVAILABLE = "unavailable"


class VisionLevelQuality(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class VisionContextAssemblyStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


class VisionOpeningRangeState(str, Enum):
    WAITING = "waiting"
    INSIDE_RANGE = "inside_range"
    BREAK_ABOVE = "break_above"
    BREAK_BELOW = "break_below"
    RETEST = "retest"
    FALSE_BREAK = "false_break"


class VisionBreakDirection(str, Enum):
    NONE = "none"
    UP = "up"
    DOWN = "down"


class VisionRangeLocation(str, Enum):
    ABOVE_RANGE = "above_range"
    INSIDE_RANGE = "inside_range"
    BELOW_RANGE = "below_range"


class VisionLiquidityPool(str, Enum):
    BUY_SIDE = "buy_side"
    SELL_SIDE = "sell_side"
    NONE = "none"


class VisionLiquiditySweep(str, Enum):
    BUY_SIDE_SWEEP = "buy_side_sweep"
    SELL_SIDE_SWEEP = "sell_side_sweep"
    NONE = "none"


class VisionSweepDirection(str, Enum):
    BUY_SIDE = "buy_side"
    SELL_SIDE = "sell_side"
    NONE = "none"


class VisionFairValueGapDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NONE = "none"


class VisionOrderBlockDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NONE = "none"


class VisionBreakerBlockState(str, Enum):
    NOT_EVALUATED = "not_evaluated"


class VisionMitigationState(str, Enum):
    NOT_EVALUATED = "not_evaluated"


class VisionBOS(str, Enum):
    BULLISH_BOS = "bullish_bos"
    BEARISH_BOS = "bearish_bos"
    NONE = "none"


class VisionCHoCH(str, Enum):
    BULLISH_CHOCH = "bullish_choch"
    BEARISH_CHOCH = "bearish_choch"
    NONE = "none"


class VisionMSS(str, Enum):
    MARKET_STRUCTURE_SHIFT = "market_structure_shift"
    NONE = "none"


class VisionStructureEventPhase(str, Enum):
    CONTINUATION = "continuation"
    REVERSAL = "reversal"
    TRANSITION = "transition"
    NONE = "none"


class VisionReversalState(str, Enum):
    BULLISH_REVERSAL = "bullish_reversal"
    BEARISH_REVERSAL = "bearish_reversal"
    NONE = "none"


class VisionBreakStrength(str, Enum):
    WEAK = "weak"
    NORMAL = "normal"
    STRONG = "strong"
    NONE = "none"


class VisionSetupType(str, Enum):
    TREND_CONTINUATION = "trend_continuation"
    PULLBACK_CONTINUATION = "pullback_continuation"
    BREAKOUT = "breakout"
    FAILED_BREAKOUT = "failed_breakout"
    LIQUIDITY_REVERSAL = "liquidity_reversal"
    RANGE_FADE = "range_fade"
    NO_QUALITY_SETUP = "no_quality_setup"


class VisionSetupQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INVALID = "invalid"


class VisionDirectionQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INVALID = "invalid"


class VisionEntryLocationState(str, Enum):
    FAVORABLE = "favorable"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    DO_NOT_CHASE = "do_not_chase"
    WAIT_FOR_RETEST = "wait_for_retest"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionMoveMaturity(str, Enum):
    EARLY = "early"
    DEVELOPING = "developing"
    MATURE = "mature"
    EXTENDED = "extended"
    UNKNOWN = "unknown"


class VisionChaseRisk(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VisionPivotRelationship(str, Enum):
    HIGHER_VALUE = "higher_value"
    OVERLAPPING_HIGHER_VALUE = "overlapping_higher_value"
    LOWER_VALUE = "lower_value"
    OVERLAPPING_LOWER_VALUE = "overlapping_lower_value"
    UNCHANGED_VALUE = "unchanged_value"
    OUTSIDE_VALUE = "outside_value"
    INSIDE_VALUE = "inside_value"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionPivotWidthState(str, Enum):
    NARROW = "narrow"
    NORMAL = "normal"
    WIDE = "wide"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionPivotDirectionalPrior(str, Enum):
    BULLISH = "bullish"
    MODERATELY_BULLISH = "moderately_bullish"
    BEARISH = "bearish"
    MODERATELY_BEARISH = "moderately_bearish"
    BREAKOUT_UNRESOLVED = "breakout_unresolved"
    BALANCE_NEUTRAL = "balance_neutral"
    RANGE_BALANCE = "range_balance"
    CONFLICTED = "conflicted"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionPivotCombinedContext(str, Enum):
    BULLISH_ALIGNED = "bullish_aligned"
    BEARISH_ALIGNED = "bearish_aligned"
    MODERATELY_BULLISH = "moderately_bullish"
    MODERATELY_BEARISH = "moderately_bearish"
    BREAKOUT_POTENTIAL = "breakout_potential"
    BALANCE_RANGE = "balance_range"
    CONFLICTED = "conflicted"
    NEUTRAL = "neutral"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionPivotTendency(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionScenarioStatus(str, Enum):
    PROVISIONAL = "provisional"
    OPENING_CONFIRMATION_REQUIRED = "opening_confirmation_required"
    INSUFFICIENT_DATA = "insufficient_data"
