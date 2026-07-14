from dataclasses import replace

from application.enums import ExecutionSafetyMode
from application.execution_runtime_v1 import ExecutionDecision, ExecutionEligibilityValidator, ExecutionRuntimeV1Configuration
from brokers.zerodha.enums import BrokerExecutionMode
from engines.risk_management_v2.enums import RiskDecision
from engines.strategy_decision_v2.enums import StrategyAction, StrategySetupStatus
from tests.test_risk_management_v2_calculator import account, calculate, risk_input, strategy


def validate(risk, configuration=None):
    return ExecutionEligibilityValidator().validate(risk, configuration or ExecutionRuntimeV1Configuration())


def test_approved_and_approved_reduced_are_accepted():
    approved = calculate()
    reduced = calculate(risk_input(proposed_invalidation_price=83.0, proposed_objective_price=148.0))

    assert validate(approved)[0] is ExecutionDecision.ACCEPTED
    assert validate(reduced)[0] is ExecutionDecision.ACCEPTED


def test_rejected_wait_insufficient_zero_quantity_and_ineligible_are_not_accepted():
    rejected = calculate(risk_input(account=account(realized_pnl_today=-300.0)))
    insufficient = calculate(risk_input(strategy("insufficient")))
    ready = strategy()
    wait_strategy = replace(
        ready,
        action=StrategyAction.WAIT,
        setup_status=StrategySetupStatus.WAITING_FOR_TRIGGER,
        eligible=False,
        risk_handoff=replace(ready.risk_handoff, requires_risk_review=False, setup_status=StrategySetupStatus.WAITING_FOR_TRIGGER),
    )
    wait = calculate(risk_input(wait_strategy))
    zero = replace(calculate(), approved_quantity=0, execution_eligible=False, decision=RiskDecision.REJECTED, position_size=None)

    assert validate(rejected)[0] is ExecutionDecision.REJECTED
    assert validate(wait)[0] is ExecutionDecision.WAIT
    assert validate(insufficient)[0] is ExecutionDecision.INSUFFICIENT_DATA
    assert validate(zero)[0] is ExecutionDecision.REJECTED


def test_wrong_safety_or_broker_mode_rejects_without_risk_override():
    cfg = object.__new__(ExecutionRuntimeV1Configuration)
    object.__setattr__(cfg, "broker_mode", BrokerExecutionMode.CLIENT)
    object.__setattr__(cfg, "safety_mode", ExecutionSafetyMode.ANALYSIS_ONLY)
    object.__setattr__(cfg, "require_risk_execution_eligibility", True)
    object.__setattr__(cfg, "reject_zero_quantity", True)

    assert validate(calculate(), cfg)[0] is ExecutionDecision.REJECTED
