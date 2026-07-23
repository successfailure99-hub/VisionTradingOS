from engines.strategy_decision_v2 import (
    StrategyAction,
    StrategyDecisionV2Calculator,
    StrategyDecisionV2Configuration,
    StrategyDecisionV2Input,
    StrategySetupFamily,
    StrategySetupStatus,
)
from tests.test_strategy_decision_v2_integration import build_stack, replace_context
from tests.test_ai_reasoning_v2_models import ExpertSetup, FusionDirection


def calculate(reasoning, price):
    return StrategyDecisionV2Calculator().calculate(
        inputs=StrategyDecisionV2Input(reasoning),
        configuration=StrategyDecisionV2Configuration(),
    )


def test_eligible_long_short_conflict_and_insufficient():
    long = calculate(build_stack("bullish"), 108.0)
    assert long.action is StrategyAction.CONSIDER_LONG
    assert long.setup_status is StrategySetupStatus.READY_FOR_RISK_REVIEW
    assert long.risk_handoff.requires_risk_review is True
    assert long.entry_conditions and long.invalidation_rules
    assert long.objectives == ()
    assert long.current_price is None
    short = calculate(build_stack("bearish"), 93.0)
    assert short.action is StrategyAction.CONSIDER_SHORT
    conflict = calculate(build_stack("conflict"), 108.0)
    assert conflict.action is StrategyAction.NO_TRADE
    insufficient = calculate(build_stack("insufficient"), 108.0)
    assert insufficient.action is StrategyAction.INSUFFICIENT_DATA


def test_breakout_retest_waits_and_reversal_watch_is_not_actionable():
    breakout = calculate(replace_context(build_stack("bullish"), primary_setup=ExpertSetup.BREAKOUT), 108.0)
    assert breakout.action is StrategyAction.WAIT
    assert breakout.setup_family is StrategySetupFamily.BREAKOUT_RETEST
    assert breakout.setup_status is StrategySetupStatus.WAITING_FOR_RETEST
    breakdown = calculate(
        replace_context(
            build_stack("bearish"),
            primary_setup=ExpertSetup.BREAKOUT,
            direction=FusionDirection.BEARISH,
        ),
        93.0,
    )
    assert breakdown.setup_family is StrategySetupFamily.BREAKDOWN_RETEST
    reversal = calculate(replace_context(build_stack("bullish"), primary_setup=ExpertSetup.REVERSAL_ATTEMPT), 108.0)
    assert reversal.action is StrategyAction.WAIT
    assert reversal.setup_family is StrategySetupFamily.REVERSAL_WATCH
