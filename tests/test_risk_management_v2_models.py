from dataclasses import FrozenInstanceError, replace
from datetime import date

import pytest

from core.enums.instrument import Instrument
from engines.risk_management_v2 import (
    AccountRiskState,
    InstrumentExposureState,
    PositionSizeRecommendation,
    RiskDecision,
    RiskManagementV2Snapshot,
    RiskRuleEvaluation,
    RiskRuleResult,
    RiskRuleType,
    RiskSeverity,
)
from engines.strategy_decision_v2.enums import StrategyDecisionQuality
from tests.test_risk_management_v2_calculator import account, calculate, exposure, risk_input, session, strategy


def test_models_are_frozen_slotted_and_validate_account_session_exposure():
    acc = account()
    sess = session()
    exp = exposure()

    assert hasattr(AccountRiskState, "__slots__")
    with pytest.raises(FrozenInstanceError):
        acc.account_equity = 1.0
    assert acc.current_equity == 10000.0
    assert sess.trading_date == date(2026, 7, 14)
    assert exp.instrument is Instrument.NIFTY
    with pytest.raises(ValueError):
        account(peak_equity=9000.0)
    with pytest.raises(ValueError):
        session(trades_taken=1, winning_trades=1, losing_trades=1)
    with pytest.raises(ValueError):
        exposure(Instrument.SBI)


def test_input_price_geometry_and_collection_immutability():
    with pytest.raises(ValueError):
        risk_input(proposed_invalidation_price=120.0)
    short = strategy("bearish")
    with pytest.raises(ValueError):
        risk_input(short, proposed_invalidation_price=80.0)

    snapshot = calculate()

    assert isinstance(snapshot.rule_evaluations, tuple)
    with pytest.raises(FrozenInstanceError):
        snapshot.approved_quantity = 5
    assert not any("broker" in field for field in snapshot.__dataclass_fields__)
    assert not any("order" in field for field in snapshot.__dataclass_fields__)
    assert not any("strike" in field for field in snapshot.__dataclass_fields__)


def test_rule_position_and_snapshot_consistency():
    rule = RiskRuleEvaluation(
        RiskRuleType.CAPITAL_AVAILABLE,
        RiskRuleResult.PASSED,
        RiskSeverity.NONE,
        "Capital is available.",
        1,
        None,
    )
    size = PositionSizeRecommendation(50.0, 50.0, 50.0, 1.0, 1, 1, 1, 1, 1.0, False)
    snapshot = calculate()

    assert rule.message
    assert size.final_quantity == 1
    assert snapshot.decision is RiskDecision.APPROVED
    assert snapshot.position_size is not None
    assert snapshot.execution_eligible is True

    low_quality = calculate(
        risk_input(
            replace(strategy(), quality=StrategyDecisionQuality.LOW),
            proposed_invalidation_price=83.0,
            proposed_objective_price=148.0,
        )
    )
    assert low_quality.approved_quantity <= snapshot.approved_quantity


def test_rejected_snapshot_cannot_be_execution_eligible():
    rejected = calculate(risk_input(account=account(realized_pnl_today=-300.0)))

    assert rejected.decision is RiskDecision.REJECTED
    assert rejected.execution_eligible is False
    assert rejected.approved_quantity == 0
    assert rejected.position_size is None


def test_snapshot_rejects_inconsistent_execution_state():
    approved = calculate()
    fields = {field: getattr(approved, field) for field in approved.__dataclass_fields__}
    fields["execution_eligible"] = True
    fields["decision"] = RiskDecision.REJECTED
    fields["approved_quantity"] = 1

    with pytest.raises(ValueError):
        RiskManagementV2Snapshot(**fields)
