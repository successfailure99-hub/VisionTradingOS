from engines.market_context_v2 import (
    EvidenceDirection,
    EvidenceStrength,
    MarketConflictSeverity,
    MarketContextReadiness,
    MarketDirection,
    MarketEvidenceSource,
    MarketRegime,
    TradePosture,
)


def test_exact_enum_values_and_no_duplicates():
    assert MarketDirection.STRONGLY_BULLISH.value == "strongly_bullish"
    assert MarketDirection.BULLISH.value == "bullish"
    assert MarketDirection.NEUTRAL.value == "neutral"
    assert MarketDirection.BEARISH.value == "bearish"
    assert MarketDirection.STRONGLY_BEARISH.value == "strongly_bearish"
    assert MarketDirection.CONFLICTED.value == "conflicted"
    assert MarketDirection.INSUFFICIENT_DATA.value == "insufficient_data"
    assert MarketRegime.TRENDING_UP.value == "trending_up"
    assert MarketRegime.TRENDING_DOWN.value == "trending_down"
    assert MarketRegime.RANGE_BOUND.value == "range_bound"
    assert MarketRegime.BREAKOUT_ATTEMPT.value == "breakout_attempt"
    assert MarketRegime.BREAKDOWN_ATTEMPT.value == "breakdown_attempt"
    assert MarketRegime.REVERSAL_RISK.value == "reversal_risk"
    assert MarketRegime.HIGH_CONFLICT.value == "high_conflict"
    assert MarketRegime.INSUFFICIENT_DATA.value == "insufficient_data"
    assert TradePosture.LOOK_FOR_LONGS.value == "look_for_longs"
    assert TradePosture.LOOK_FOR_SHORTS.value == "look_for_shorts"
    assert TradePosture.WAIT_FOR_CONFIRMATION.value == "wait_for_confirmation"
    assert TradePosture.AVOID_NEW_TRADES.value == "avoid_new_trades"
    assert TradePosture.MANAGE_EXISTING_ONLY.value == "manage_existing_only"
    assert TradePosture.INSUFFICIENT_DATA.value == "insufficient_data"
    assert MarketEvidenceSource.PRICE_ACTION.value == "price_action"
    assert MarketEvidenceSource.OPTION_CHAIN.value == "option_chain"
    assert MarketEvidenceSource.CAMARILLA.value == "camarilla"
    assert MarketEvidenceSource.CPR.value == "cpr"
    assert MarketEvidenceSource.VWAP.value == "vwap"
    assert EvidenceDirection.BULLISH.value == "bullish"
    assert EvidenceDirection.BEARISH.value == "bearish"
    assert EvidenceDirection.NEUTRAL.value == "neutral"
    assert EvidenceDirection.CONFLICTED.value == "conflicted"
    assert EvidenceDirection.UNAVAILABLE.value == "unavailable"
    assert EvidenceStrength.WEAK.value == "weak"
    assert EvidenceStrength.MODERATE.value == "moderate"
    assert EvidenceStrength.STRONG.value == "strong"
    assert MarketConflictSeverity.NONE.value == "none"
    assert MarketConflictSeverity.LOW.value == "low"
    assert MarketConflictSeverity.MODERATE.value == "moderate"
    assert MarketConflictSeverity.HIGH.value == "high"
    assert MarketConflictSeverity.CRITICAL.value == "critical"
    assert MarketContextReadiness.READY.value == "ready"
    assert MarketContextReadiness.PARTIAL.value == "partial"
    assert MarketContextReadiness.INSUFFICIENT.value == "insufficient"
    for enum_type in (
        MarketDirection,
        MarketRegime,
        TradePosture,
        MarketEvidenceSource,
        EvidenceDirection,
        EvidenceStrength,
        MarketConflictSeverity,
        MarketContextReadiness,
    ):
        values = [item.value for item in enum_type]
        assert len(values) == len(set(values))
