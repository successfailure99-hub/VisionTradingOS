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


class VisionPriceActionTriggerStageStatus(str, Enum):
    EVALUATED_NO_TRIGGER = "evaluated_no_trigger"
    EVALUATED_NO_INTERACTION = "evaluated_no_interaction"
    EVALUATED_INDECISION = "evaluated_indecision"
    EVALUATED_TRIGGER = "evaluated_trigger"
    INSUFFICIENT_DATA = "insufficient_data"
    TRIGGER_ASSEMBLY_FAILED = "trigger_assembly_failed"


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


class VisionSetupDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


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


class VisionOpeningPriorRangeLocation(str, Enum):
    ABOVE_PRIOR_HIGH = "above_prior_high"
    INSIDE_PRIOR_RANGE = "inside_prior_range"
    BELOW_PRIOR_LOW = "below_prior_low"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionOpeningPivotValueLocation(str, Enum):
    IN_RANGE_IN_VALUE = "in_range_in_value"
    IN_RANGE_OUT_OF_VALUE = "in_range_out_of_value"
    OUT_OF_RANGE_OUT_OF_VALUE = "out_of_range_out_of_value"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionOpeningCPRLocation(str, Enum):
    ABOVE_CPR = "above_cpr"
    INSIDE_CPR = "inside_cpr"
    BELOW_CPR = "below_cpr"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionOpeningCamarillaLocation(str, Enum):
    ABOVE_H4 = "above_h4"
    BETWEEN_H3_H4 = "between_h3_h4"
    BETWEEN_L3_H3 = "between_l3_h3"
    BETWEEN_L4_L3 = "between_l4_l3"
    BELOW_L4 = "below_l4"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionOpeningGapState(str, Enum):
    GAP_UP = "gap_up"
    GAP_DOWN = "gap_down"
    NO_MEANINGFUL_GAP = "no_meaningful_gap"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionOpeningAcceptanceState(str, Enum):
    ACCEPTED = "accepted"
    PARTIALLY_ACCEPTED = "partially_accepted"
    UNRESOLVED = "unresolved"
    REJECTED = "rejected"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionOpeningScenario(str, Enum):
    BULLISH_CONTINUATION = "bullish_continuation"
    BEARISH_CONTINUATION = "bearish_continuation"
    BULLISH_BREAKOUT_WATCH = "bullish_breakout_watch"
    BEARISH_BREAKOUT_WATCH = "bearish_breakout_watch"
    BALANCE_RANGE = "balance_range"
    RESPONSIVE_REVERSAL_WATCH = "responsive_reversal_watch"
    CONFLICTED = "conflicted"
    UNRESOLVED = "unresolved"
    NO_ACTIVE_SCENARIO = "no_active_scenario"


class VisionOpeningScenarioDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    CONFLICTED = "conflicted"
    NONE = "none"


class VisionOpeningScenarioStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT_DATA = "insufficient_data"


class VisionOpeningActionZoneState(str, Enum):
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class VisionOpeningActionZoneId(str, Enum):
    H3_PULLBACK_LONG_ZONE = "h3_pullback_long_zone"
    L3_RESPONSIVE_LONG_ZONE = "l3_responsive_long_zone"
    L3_PULLBACK_SHORT_ZONE = "l3_pullback_short_zone"
    H3_RESPONSIVE_SHORT_ZONE = "h3_responsive_short_zone"
    H4_BULLISH_BREAKOUT_WATCH_ZONE = "h4_bullish_breakout_watch_zone"
    L4_BEARISH_BREAKOUT_WATCH_ZONE = "l4_bearish_breakout_watch_zone"


class VisionPivotReferenceFamily(str, Enum):
    CPR = "cpr"
    CAMARILLA = "camarilla"
    PRIOR_SESSION = "prior_session"
    VWAP = "vwap"
    OPENING_RANGE = "opening_range"
    STRUCTURE = "structure"
    LIQUIDITY = "liquidity"


class VisionPivotReferenceKind(str, Enum):
    CPR_BC = "cpr_bc"
    CPR_TC = "cpr_tc"
    CPR_PIVOT = "cpr_pivot"
    CAMARILLA_H3 = "camarilla_h3"
    CAMARILLA_H4 = "camarilla_h4"
    CAMARILLA_H5 = "camarilla_h5"
    CAMARILLA_H6 = "camarilla_h6"
    CAMARILLA_L3 = "camarilla_l3"
    CAMARILLA_L4 = "camarilla_l4"
    CAMARILLA_L5 = "camarilla_l5"
    CAMARILLA_L6 = "camarilla_l6"
    PRIOR_HIGH = "prior_high"
    PRIOR_LOW = "prior_low"
    PRIOR_CLOSE = "prior_close"
    VWAP = "vwap"
    OPENING_RANGE_HIGH = "opening_range_high"
    OPENING_RANGE_LOW = "opening_range_low"
    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"
    EQUAL_HIGH = "equal_high"
    EQUAL_LOW = "equal_low"
    FAIR_VALUE_GAP = "fair_value_gap"
    ORDER_BLOCK = "order_block"


class VisionPivotZoneType(str, Enum):
    SUPPORT_HOT_ZONE = "support_hot_zone"
    RESISTANCE_HOT_ZONE = "resistance_hot_zone"
    BREAKOUT_DECISION_ZONE = "breakout_decision_zone"
    REVERSAL_DECISION_ZONE = "reversal_decision_zone"
    TARGET_MAGNET_ZONE = "target_magnet_zone"
    CONFLICT_ZONE = "conflict_zone"
    NEUTRAL_HOT_ZONE = "neutral_hot_zone"


class VisionPivotZoneDirectionalRole(str, Enum):
    BULLISH_SUPPORT = "bullish_support"
    BEARISH_RESISTANCE = "bearish_resistance"
    BREAKOUT_UPSIDE = "breakout_upside"
    BREAKDOWN_DOWNSIDE = "breakdown_downside"
    TARGET_MAGNET = "target_magnet"
    NEUTRAL = "neutral"
    CONFLICT = "conflict"


class VisionPivotZoneQuality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class VisionPivotZoneStrength(str, Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class VisionPivotZoneStatus(str, Enum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    STALE = "stale"
    INVALIDATED = "invalidated"


class VisionPivotZoneAlignment(str, Enum):
    ALIGNED = "aligned"
    PARTIAL = "partial"
    OPPOSED = "opposed"
    NEUTRAL = "neutral"
    UNRESOLVED = "unresolved"


class VisionPivotPriceRelation(str, Enum):
    BELOW = "below"
    INSIDE = "inside"
    ABOVE = "above"
    APPROACHING = "approaching"


class VisionTriggerInteractionState(str, Enum):
    APPROACHING = "approaching"
    TESTING = "testing"
    PENETRATING = "penetrating"
    REJECTING = "rejecting"
    BROKEN = "broken"
    ACCEPTED = "accepted"
    RETESTING = "retesting"
    HOLDING = "holding"
    FAILING = "failing"
    CONSUMED = "consumed"
    NO_INTERACTION = "no_interaction"


class VisionTriggerType(str, Enum):
    NO_TRIGGER = "no_trigger"
    BULLISH_REJECTION = "bullish_rejection"
    BEARISH_REJECTION = "bearish_rejection"
    BULLISH_FAILED_BREAKOUT = "bullish_failed_breakout"
    BEARISH_FAILED_BREAKOUT = "bearish_failed_breakout"
    BULLISH_INITIATIVE_BREAKOUT = "bullish_initiative_breakout"
    BEARISH_INITIATIVE_BREAKOUT = "bearish_initiative_breakout"
    BULLISH_RETEST_HOLD = "bullish_retest_hold"
    BEARISH_RETEST_HOLD = "bearish_retest_hold"
    BULLISH_CONTINUATION = "bullish_continuation"
    BEARISH_CONTINUATION = "bearish_continuation"
    INDECISION = "indecision"


class VisionTriggerDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NONE = "none"


class VisionTriggerQuality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    INVALID = "invalid"


class VisionTriggerBreakState(str, Enum):
    NONE = "none"
    BROKEN_UP = "broken_up"
    BROKEN_DOWN = "broken_down"


class VisionTriggerAcceptanceState(str, Enum):
    NONE = "none"
    WAITING_FOR_ACCEPTANCE = "waiting_for_acceptance"
    ACCEPTED_UP = "accepted_up"
    ACCEPTED_DOWN = "accepted_down"
    FAILED_UP = "failed_up"
    FAILED_DOWN = "failed_down"


class VisionTriggerRetestState(str, Enum):
    NONE = "none"
    RETESTING = "retesting"
    RETEST_HOLD = "retest_hold"
    RETEST_FAILURE = "retest_failure"


class VisionCandlestickPattern(str, Enum):
    NONE = "none"
    BULLISH_WICK_REVERSAL = "bullish_wick_reversal"
    BEARISH_WICK_REVERSAL = "bearish_wick_reversal"
    BULLISH_OUTSIDE_REVERSAL = "bullish_outside_reversal"
    BEARISH_OUTSIDE_REVERSAL = "bearish_outside_reversal"
    BULLISH_EXTREME_REVERSAL = "bullish_extreme_reversal"
    BEARISH_EXTREME_REVERSAL = "bearish_extreme_reversal"
    DOJI = "doji"


class VisionTriggerAlignment(str, Enum):
    ALIGNED = "aligned"
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"
