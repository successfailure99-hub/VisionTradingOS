from dataclasses import replace
from datetime import date, timedelta

from core.enums.instrument import Instrument
from engines.risk_management_v2 import (
    AccountRiskState,
    InstrumentExposureState,
    RiskDecision,
    RiskManagementV2Calculator,
    RiskManagementV2Configuration,
    RiskManagementV2Input,
    RiskStatus,
    SessionRiskState,
)
from engines.strategy_decision_v2 import StrategyDecisionV2Engine, StrategyDecisionV2Input
from engines.strategy_decision_v2.enums import StrategyAction, StrategyDecisionQuality, StrategySetupStatus
from tests.test_strategy_decision_v2_integration import build_stack, replace_context


def strategy(kind="bullish", *, minutes=0):
    reasoning = build_stack(kind)
    if minutes:
        reasoning = replace_context(reasoning, timestamp=reasoning.timestamp + timedelta(minutes=minutes))
    return StrategyDecisionV2Engine(instrument=Instrument.NIFTY).process(
        StrategyDecisionV2Input(reasoning)
    )


def account(snapshot=None, **changes):
    timestamp = snapshot.timestamp if snapshot else strategy().timestamp
    base = AccountRiskState(timestamp, 10000.0, 10000.0, 10000.0, 10000.0, 0.0, 0.0, 0.0)
    return replace(base, **changes)


def session(**changes):
    base = SessionRiskState(date(2026, 7, 14), 0, 0, 0, 0, 0.0)
    return replace(base, **changes)


def exposure(instrument=Instrument.NIFTY, **changes):
    base = InstrumentExposureState(instrument, 0, 0.0, 0.0)
    return replace(base, **changes)


def risk_input(snapshot=None, **changes):
    snapshot = snapshot or strategy()
    params = dict(
        strategy=snapshot,
        account=account(snapshot),
        session=session(),
        instrument_exposure=exposure(snapshot.instrument),
        proposed_entry_price=108.0 if snapshot.action is not StrategyAction.CONSIDER_SHORT else 93.0,
        proposed_invalidation_price=58.0 if snapshot.action is not StrategyAction.CONSIDER_SHORT else 143.0,
        proposed_objective_price=188.0 if snapshot.action is not StrategyAction.CONSIDER_SHORT else 13.0,
    )
    params.update(changes)
    return RiskManagementV2Input(**params)


def config(**changes):
    params = {"maximum_position_quantity": 10}
    params.update(changes)
    return RiskManagementV2Configuration(**params)


def calculate(inputs=None, configuration=None, previous=None):
    return RiskManagementV2Calculator().calculate(
        inputs=inputs or risk_input(),
        configuration=configuration or config(),
        previous=previous,
    )


def test_approved_long_and_short_are_direction_preserving():
    long_snapshot = calculate()
    short_strategy = strategy("bearish")
    short_snapshot = calculate(risk_input(short_strategy))

    assert long_snapshot.decision is RiskDecision.APPROVED
    assert short_snapshot.decision is RiskDecision.APPROVED
    assert long_snapshot.strategy.direction.value == "long"
    assert short_snapshot.strategy.direction.value == "short"
    assert long_snapshot.approved_quantity == short_snapshot.approved_quantity == 1
    assert long_snapshot.execution_eligible is True


def test_approved_reduced_by_quality_or_exposure():
    low_quality = replace(strategy(), quality=StrategyDecisionQuality.LOW)
    quality_reduced = calculate(
        risk_input(low_quality, proposed_invalidation_price=83.0, proposed_objective_price=148.0)
    )
    exposure_reduced = calculate(
        risk_input(
            instrument_exposure=exposure(current_notional_exposure=850.0),
            proposed_invalidation_price=83.0,
            proposed_objective_price=148.0,
        )
    )
    full_same_geometry = calculate(risk_input(proposed_invalidation_price=83.0, proposed_objective_price=148.0))

    assert quality_reduced.decision is RiskDecision.APPROVED_REDUCED
    assert exposure_reduced.decision is RiskDecision.APPROVED_REDUCED
    assert quality_reduced.approved_quantity < full_same_geometry.approved_quantity


def test_hard_limits_reject_daily_loss_drawdown_trade_count_and_losses():
    cases = [
        risk_input(account=account(realized_pnl_today=-250.0)),
        risk_input(account=account(account_equity=9000.0, peak_equity=10000.0)),
        risk_input(session=session(trades_taken=3)),
        risk_input(session=session(trades_taken=2, losing_trades=2, consecutive_losses=2)),
    ]

    results = [calculate(item) for item in cases]

    assert [item.decision for item in results] == [RiskDecision.REJECTED] * 4
    assert results[0].status is RiskStatus.BLOCKED_BY_DAILY_LOSS
    assert results[1].status is RiskStatus.BLOCKED_BY_DRAWDOWN
    assert results[2].status is RiskStatus.BLOCKED_BY_TRADE_LIMIT
    assert results[3].status is RiskStatus.BLOCKED_BY_TRADE_LIMIT


def test_reward_risk_exposure_and_capital_rejections():
    low_reward = calculate(risk_input(proposed_objective_price=130.0))
    no_exposure = calculate(
        risk_input(instrument_exposure=exposure(current_notional_exposure=950.0))
    )
    no_capital = calculate(risk_input(account=account(available_capital=0.0)))

    assert low_reward.status is RiskStatus.BLOCKED_BY_STRATEGY
    assert no_exposure.status is RiskStatus.BLOCKED_BY_EXPOSURE
    assert no_capital.status is RiskStatus.BLOCKED_BY_CAPITAL


def test_strategy_wait_and_insufficient_data_are_never_approved():
    wait_strategy = replace(
        strategy(),
        action=StrategyAction.WAIT,
        setup_status=StrategySetupStatus.WAITING_FOR_TRIGGER,
        eligible=False,
        risk_handoff=replace(strategy().risk_handoff, requires_risk_review=False, setup_status=StrategySetupStatus.WAITING_FOR_TRIGGER),
    )
    insufficient = strategy("insufficient")

    wait_snapshot = calculate(risk_input(wait_strategy))
    insufficient_snapshot = calculate(risk_input(insufficient))

    assert wait_snapshot.decision is RiskDecision.WAIT
    assert insufficient_snapshot.decision is RiskDecision.INSUFFICIENT_DATA
    assert wait_snapshot.execution_eligible is False
    assert insufficient_snapshot.execution_eligible is False


def test_rationale_warnings_input_immutability_and_no_orders():
    inputs = risk_input()
    before = inputs
    snapshot = calculate(inputs)

    assert inputs == before
    assert snapshot.rationale[0].startswith("Strategy Decision V2")
    assert "Risk approval does not guarantee execution." in snapshot.warnings
    assert not any("order" in field for field in snapshot.__dataclass_fields__)
