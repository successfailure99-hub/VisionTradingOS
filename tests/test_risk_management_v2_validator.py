from dataclasses import replace

from engines.risk_management_v2 import RiskRuleResult, RiskRuleType, RiskRuleValidator
from engines.strategy_decision_v2.enums import StrategyAction, StrategySetupStatus
from tests.test_risk_management_v2_calculator import account, config, exposure, risk_input, session, strategy


def results(inputs, configuration=None):
    return RiskRuleValidator().evaluate(inputs, configuration or config())


def by_rule(evaluations, rule):
    return next(item for item in evaluations if item.rule is rule)


def test_eligible_strategy_passes_and_order_is_deterministic():
    evaluations = results(risk_input())

    assert evaluations[0].rule is RiskRuleType.STRATEGY_ELIGIBILITY
    assert by_rule(evaluations, RiskRuleType.STRATEGY_ELIGIBILITY).result is RiskRuleResult.PASSED
    assert [item.rule for item in evaluations] == [
        RiskRuleType.STRATEGY_ELIGIBILITY,
        RiskRuleType.DAILY_LOSS_LIMIT,
        RiskRuleType.ACCOUNT_DRAWDOWN_LIMIT,
        RiskRuleType.CONSECUTIVE_LOSS_LIMIT,
        RiskRuleType.MAX_TRADES_PER_DAY,
        RiskRuleType.CAPITAL_AVAILABLE,
        RiskRuleType.INVALIDATION_REQUIRED,
        RiskRuleType.OBJECTIVE_REQUIRED,
        RiskRuleType.MINIMUM_REWARD_RISK,
        RiskRuleType.PER_TRADE_RISK_LIMIT,
        RiskRuleType.TOTAL_EXPOSURE_LIMIT,
        RiskRuleType.INSTRUMENT_EXPOSURE_LIMIT,
        RiskRuleType.MAX_POSITION_QUANTITY,
        RiskRuleType.STRATEGY_ELIGIBILITY,
    ]


def test_strategy_wait_no_trade_and_insufficient_fail_eligibility():
    ready = strategy()
    wait = replace(
        ready,
        action=StrategyAction.WAIT,
        setup_status=StrategySetupStatus.WAITING_FOR_TRIGGER,
        eligible=False,
        risk_handoff=replace(ready.risk_handoff, requires_risk_review=False, setup_status=StrategySetupStatus.WAITING_FOR_TRIGGER),
    )
    no_trade = strategy("conflict")
    insufficient = strategy("insufficient")

    assert results(risk_input(wait))[0].result is RiskRuleResult.FAILED
    assert results(risk_input(no_trade))[0].result is RiskRuleResult.FAILED
    assert results(risk_input(insufficient))[0].result is RiskRuleResult.FAILED


def test_daily_drawdown_trade_loss_capital_data_reward_and_exposure_rules():
    cases = [
        (risk_input(account=account(realized_pnl_today=-250.0)), RiskRuleType.DAILY_LOSS_LIMIT),
        (risk_input(account=account(account_equity=9000.0, peak_equity=10000.0)), RiskRuleType.ACCOUNT_DRAWDOWN_LIMIT),
        (risk_input(session=session(trades_taken=3)), RiskRuleType.MAX_TRADES_PER_DAY),
        (risk_input(session=session(trades_taken=2, losing_trades=2, consecutive_losses=2)), RiskRuleType.CONSECUTIVE_LOSS_LIMIT),
        (risk_input(account=account(available_capital=0.0)), RiskRuleType.CAPITAL_AVAILABLE),
        (risk_input(proposed_objective_price=None), RiskRuleType.OBJECTIVE_REQUIRED),
        (risk_input(proposed_objective_price=130.0), RiskRuleType.MINIMUM_REWARD_RISK),
        (risk_input(instrument_exposure=exposure(current_notional_exposure=950.0)), RiskRuleType.INSTRUMENT_EXPOSURE_LIMIT),
    ]

    for item, rule in cases:
        assert by_rule(results(item), rule).result is RiskRuleResult.FAILED


def test_position_cap_reduction_and_input_not_mutated():
    inputs = risk_input(proposed_invalidation_price=83.0, proposed_objective_price=148.0)
    before = inputs
    evaluations = results(inputs, config(maximum_position_quantity=1))

    assert inputs == before
    assert by_rule(evaluations, RiskRuleType.MAX_POSITION_QUANTITY).result is RiskRuleResult.PASSED
