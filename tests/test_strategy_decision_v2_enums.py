from engines.strategy_decision_v2 import (
    StrategyAction,
    StrategyDecisionChange,
    StrategyDecisionQuality,
    StrategyDirection,
    StrategyInvalidationType,
    StrategyReferenceType,
    StrategySetupFamily,
    StrategySetupStatus,
    StrategyTriggerType,
)


def test_exact_enum_values_and_no_duplicates():
    assert StrategyAction.CONSIDER_LONG.value == "consider_long"
    assert StrategyAction.CONSIDER_SHORT.value == "consider_short"
    assert StrategyAction.WAIT.value == "wait"
    assert StrategyAction.NO_TRADE.value == "no_trade"
    assert StrategyAction.INSUFFICIENT_DATA.value == "insufficient_data"
    assert StrategySetupFamily.TREND_CONTINUATION.value == "trend_continuation"
    assert StrategySetupFamily.BREAKOUT_RETEST.value == "breakout_retest"
    assert StrategySetupFamily.BREAKDOWN_RETEST.value == "breakdown_retest"
    assert StrategySetupFamily.REVERSAL_WATCH.value == "reversal_watch"
    assert StrategyDirection.LONG.value == "long"
    assert StrategySetupStatus.READY_FOR_RISK_REVIEW.value == "ready_for_risk_review"
    assert StrategyTriggerType.BULLISH_RETEST_HOLD.value == "bullish_retest_hold"
    assert StrategyReferenceType.CAMARILLA_H4.value == "camarilla_h4"
    assert StrategyInvalidationType.PRIMARY_BIAS_REVERSAL.value == "primary_bias_reversal"
    assert StrategyDecisionChange.SETUP_APPEARED.value == "setup_appeared"
    assert StrategyDecisionQuality.UNAVAILABLE.value == "unavailable"
    for enum_type in (
        StrategyAction,
        StrategySetupFamily,
        StrategyDirection,
        StrategySetupStatus,
        StrategyTriggerType,
        StrategyReferenceType,
        StrategyInvalidationType,
        StrategyDecisionChange,
        StrategyDecisionQuality,
    ):
        values = [item.value for item in enum_type]
        assert len(values) == len(set(values))
