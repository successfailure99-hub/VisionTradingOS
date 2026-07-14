from dataclasses import replace

from engines.risk_management_v2 import RiskDecisionChange, RiskManagementV2Engine
from engines.strategy_decision_v2.enums import StrategyAction, StrategySetupStatus
from tests.test_risk_management_v2_calculator import account, config, exposure, risk_input, strategy


def engine():
    return RiskManagementV2Engine(instrument=strategy().instrument, configuration=config())


def test_rejected_to_approved_approved_to_reduced_and_reduced_to_approved():
    item = engine()
    rejected = item.process(risk_input(strategy(), account=account(realized_pnl_today=-300.0)))
    approved = item.process(risk_input(strategy(minutes=1)))
    reduced = item.process(risk_input(strategy(minutes=2), instrument_exposure=exposure(current_notional_exposure=850.0), proposed_invalidation_price=83.0, proposed_objective_price=148.0))
    approved_again = item.process(risk_input(strategy(minutes=3)))

    assert rejected.change is RiskDecisionChange.INITIAL
    assert approved.change is RiskDecisionChange.BECAME_APPROVED
    assert reduced.change is RiskDecisionChange.BECAME_REDUCED
    assert approved_again.change is RiskDecisionChange.BECAME_APPROVED


def test_approved_to_rejected_wait_and_quantity_decrease():
    item = engine()
    first = item.process(risk_input(strategy()))
    rejected = item.process(risk_input(strategy(minutes=1), account=account(strategy(minutes=1), realized_pnl_today=-300.0)))
    wait_base = strategy(minutes=2)
    wait_strategy = replace(
        wait_base,
        action=StrategyAction.WAIT,
        setup_status=StrategySetupStatus.WAITING_FOR_TRIGGER,
        eligible=False,
        risk_handoff=replace(wait_base.risk_handoff, requires_risk_review=False, setup_status=StrategySetupStatus.WAITING_FOR_TRIGGER),
    )
    wait = item.process(risk_input(wait_strategy))

    assert first.change is RiskDecisionChange.INITIAL
    assert rejected.change is RiskDecisionChange.BECAME_REJECTED
    assert wait.change is RiskDecisionChange.BECAME_WAIT


def test_same_timestamp_correction_uses_previous_distinct_state():
    item = engine()
    first_strategy = strategy()
    first = item.process(risk_input(first_strategy))
    corrected = item.process(risk_input(first_strategy, account=account(first_strategy, available_capital=5000.0)))
    second = item.process(risk_input(strategy(minutes=1)))
    corrected_second = item.process(risk_input(strategy(minutes=1), instrument_exposure=exposure(current_notional_exposure=850.0), proposed_invalidation_price=83.0, proposed_objective_price=148.0))

    assert corrected.change is RiskDecisionChange.INITIAL
    assert second.change is RiskDecisionChange.UNCHANGED
    assert corrected_second.change is RiskDecisionChange.BECAME_REDUCED
    assert item.previous_snapshot is corrected
    assert first.timestamp == corrected.timestamp
