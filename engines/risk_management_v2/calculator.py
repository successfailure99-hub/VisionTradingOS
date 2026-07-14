"""
Pure calculator for Risk Management Engine V2.
"""

from dataclasses import replace

from engines.risk_management_v2.configuration import RiskManagementV2Configuration
from engines.risk_management_v2.enums import (
    RiskDecision,
    RiskDecisionChange,
    RiskRuleResult,
    RiskRuleType,
    RiskSeverity,
    RiskStatus,
)
from engines.risk_management_v2.models import (
    PositionSizeRecommendation,
    RiskManagementV2Input,
    RiskManagementV2Snapshot,
    RiskRuleEvaluation,
)
from engines.risk_management_v2.sizing import PositionSizeCalculator
from engines.risk_management_v2.validator import RiskRuleValidator
from engines.strategy_decision_v2.enums import StrategyAction, StrategyDecisionQuality, StrategyDirection


class RiskManagementV2Calculator:
    def __init__(
        self,
        validator: RiskRuleValidator | None = None,
        sizing: PositionSizeCalculator | None = None,
    ) -> None:
        self._validator = validator or RiskRuleValidator()
        self._sizing = sizing or PositionSizeCalculator()

    def calculate(
        self,
        *,
        inputs: RiskManagementV2Input,
        configuration: RiskManagementV2Configuration,
        previous: RiskManagementV2Snapshot | None = None,
    ) -> RiskManagementV2Snapshot:
        evaluations = self._validator.evaluate(inputs, configuration)
        risk_distance = abs(inputs.proposed_entry_price - inputs.proposed_invalidation_price)
        reward_distance = _reward_distance(inputs)
        reward_risk_ratio = reward_distance / risk_distance if reward_distance is not None else None
        blocking = _blocking_evaluation(inputs, evaluations)
        risk_multiplier = _risk_multiplier(inputs, configuration, evaluations)
        reduced_by_rule = any(evaluation.result is RiskRuleResult.REDUCED for evaluation in evaluations)
        position_size = None
        decision = _strategy_decision(inputs, blocking)
        status = _strategy_status(inputs, blocking)
        severity = blocking.severity if blocking else RiskSeverity.NONE
        if blocking is None:
            position_size = self._sizing.calculate(inputs, configuration, risk_multiplier=risk_multiplier)
            if position_size.final_quantity <= 0:
                decision = RiskDecision.REJECTED
                status = RiskStatus.BLOCKED_BY_CAPITAL
                severity = RiskSeverity.HIGH
            elif position_size.reduced or reduced_by_rule:
                decision = RiskDecision.APPROVED_REDUCED
                status = RiskStatus.REDUCED_FOR_EXECUTION_REVIEW
                severity = RiskSeverity.LOW
            else:
                decision = RiskDecision.APPROVED
                status = RiskStatus.READY_FOR_EXECUTION_REVIEW
                severity = RiskSeverity.NONE
        approved_quantity = position_size.final_quantity if position_size and decision in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED} else 0
        if position_size is not None and approved_quantity == 0:
            position_size = replace(position_size, final_quantity=0, approved_risk_amount=0.0, reduced=position_size.rounded_quantity > 0)
        approved_risk = position_size.approved_risk_amount if position_size and approved_quantity > 0 else 0.0
        projected_notional = inputs.proposed_entry_price * approved_quantity * inputs.contract_multiplier
        snapshot = RiskManagementV2Snapshot(
            instrument=inputs.strategy.instrument,
            timestamp=inputs.strategy.timestamp,
            decision=decision,
            status=status,
            severity=severity,
            change=RiskDecisionChange.INITIAL,
            strategy=inputs.strategy,
            account=inputs.account,
            session=inputs.session,
            instrument_exposure=inputs.instrument_exposure,
            position_size=position_size if approved_quantity > 0 else None,
            rule_evaluations=evaluations,
            entry_price=inputs.proposed_entry_price,
            invalidation_price=inputs.proposed_invalidation_price,
            objective_price=inputs.proposed_objective_price,
            risk_distance=risk_distance,
            reward_distance=reward_distance,
            reward_risk_ratio=reward_risk_ratio,
            account_risk_amount=min(
                inputs.account.current_equity * configuration.risk_per_trade_fraction,
                inputs.account.current_equity * configuration.maximum_risk_per_trade_fraction,
                inputs.account.available_capital,
            ),
            approved_risk_amount=approved_risk,
            projected_notional_exposure=projected_notional,
            approved_quantity=approved_quantity,
            execution_eligible=decision in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED}
            and approved_quantity > 0
            and inputs.strategy.risk_handoff.requires_risk_review,
            rationale=_rationale(inputs, decision, position_size, reward_risk_ratio),
            warnings=_warnings(inputs, configuration, decision, position_size, evaluations),
        )
        return replace(snapshot, change=_change(snapshot, previous))


def _blocking_evaluation(inputs, evaluations):
    if inputs.strategy.action is StrategyAction.WAIT:
        return evaluations[0]
    if inputs.strategy.action is StrategyAction.INSUFFICIENT_DATA:
        return evaluations[0]
    for evaluation in evaluations:
        if evaluation.result is RiskRuleResult.FAILED:
            return evaluation
    return None


def _strategy_decision(inputs, blocking):
    if blocking is None:
        return RiskDecision.APPROVED
    if inputs.strategy.action is StrategyAction.WAIT:
        return RiskDecision.WAIT
    if inputs.strategy.action is StrategyAction.INSUFFICIENT_DATA:
        return RiskDecision.INSUFFICIENT_DATA
    return RiskDecision.REJECTED


def _strategy_status(inputs, blocking):
    if blocking is None:
        return RiskStatus.READY_FOR_EXECUTION_REVIEW
    if inputs.strategy.action is StrategyAction.INSUFFICIENT_DATA or blocking.rule in {RiskRuleType.OBJECTIVE_REQUIRED}:
        return RiskStatus.BLOCKED_BY_DATA
    if blocking.rule is RiskRuleType.DAILY_LOSS_LIMIT:
        return RiskStatus.BLOCKED_BY_DAILY_LOSS
    if blocking.rule is RiskRuleType.ACCOUNT_DRAWDOWN_LIMIT:
        return RiskStatus.BLOCKED_BY_DRAWDOWN
    if blocking.rule in {RiskRuleType.TOTAL_EXPOSURE_LIMIT, RiskRuleType.INSTRUMENT_EXPOSURE_LIMIT}:
        return RiskStatus.BLOCKED_BY_EXPOSURE
    if blocking.rule in {RiskRuleType.MAX_TRADES_PER_DAY, RiskRuleType.CONSECUTIVE_LOSS_LIMIT}:
        return RiskStatus.BLOCKED_BY_TRADE_LIMIT
    if blocking.rule is RiskRuleType.INVALIDATION_REQUIRED:
        return RiskStatus.BLOCKED_BY_INVALIDATION
    if blocking.rule is RiskRuleType.CAPITAL_AVAILABLE:
        return RiskStatus.BLOCKED_BY_CAPITAL
    return RiskStatus.BLOCKED_BY_STRATEGY


def _risk_multiplier(inputs, configuration, evaluations):
    if any(e.result is RiskRuleResult.REDUCED for e in evaluations):
        return configuration.reduced_size_fraction
    if inputs.strategy.quality is StrategyDecisionQuality.LOW:
        return configuration.reduced_size_fraction
    if inputs.strategy.quality is StrategyDecisionQuality.MODERATE and configuration.reduce_moderate_quality_setups:
        return configuration.reduced_size_fraction
    return 1.0


def _reward_distance(inputs):
    if inputs.proposed_objective_price is None:
        return None
    if inputs.strategy.direction is StrategyDirection.LONG:
        return inputs.proposed_objective_price - inputs.proposed_entry_price
    if inputs.strategy.direction is StrategyDirection.SHORT:
        return inputs.proposed_entry_price - inputs.proposed_objective_price
    return None


def _change(snapshot, previous):
    if previous is None:
        return RiskDecisionChange.INITIAL
    if snapshot.decision in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED} and previous.decision not in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED}:
        return RiskDecisionChange.BECAME_APPROVED if snapshot.decision is RiskDecision.APPROVED else RiskDecisionChange.BECAME_REDUCED
    if snapshot.decision is RiskDecision.APPROVED and previous.decision is RiskDecision.APPROVED_REDUCED:
        return RiskDecisionChange.BECAME_APPROVED
    if snapshot.decision is RiskDecision.APPROVED_REDUCED and previous.decision is RiskDecision.APPROVED:
        return RiskDecisionChange.BECAME_REDUCED
    if snapshot.decision is RiskDecision.REJECTED and previous.decision is not RiskDecision.REJECTED:
        return RiskDecisionChange.BECAME_REJECTED
    if snapshot.decision is RiskDecision.WAIT and previous.decision is not RiskDecision.WAIT:
        return RiskDecisionChange.BECAME_WAIT
    if snapshot.decision is previous.decision:
        if snapshot.approved_risk_amount > previous.approved_risk_amount or snapshot.approved_quantity > previous.approved_quantity:
            return RiskDecisionChange.RISK_INCREASED
        if snapshot.approved_risk_amount < previous.approved_risk_amount or snapshot.approved_quantity < previous.approved_quantity:
            return RiskDecisionChange.RISK_DECREASED
    return RiskDecisionChange.UNCHANGED


def _rationale(inputs, decision, position_size: PositionSizeRecommendation | None, reward_risk_ratio):
    return (
        "Strategy Decision V2 is eligible for risk review." if inputs.strategy.eligible else "Strategy Decision V2 blocks risk approval.",
        "Risk per unit is based on the structural invalidation distance.",
        "Daily loss and drawdown limits remain within bounds.",
        "Exposure limits are evaluated before approval.",
        f"Position quantity is {position_size.final_quantity if position_size else 0}.",
        f"Reward-risk ratio is {reward_risk_ratio:.2f}." if reward_risk_ratio is not None else "Reward-risk ratio is unavailable.",
        f"Setup quality is {inputs.strategy.quality.value}.",
        "The setup is approved at reduced size." if decision is RiskDecision.APPROVED_REDUCED else f"Risk decision is {decision.value}.",
        "Execution Runtime may evaluate this risk-approved decision." if decision in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED} else "Execution Runtime must not execute this decision.",
    )


def _warnings(inputs, configuration, decision, position_size, evaluations: tuple[RiskRuleEvaluation, ...]):
    warnings = []
    if position_size and position_size.reduced:
        warnings.append("Position size was reduced by configured risk limits.")
    if inputs.strategy.quality is StrategyDecisionQuality.MODERATE and configuration.reduce_moderate_quality_setups:
        warnings.append("Moderate-quality setup uses reduced risk.")
    if inputs.account.daily_loss_fraction >= configuration.maximum_daily_loss_fraction * 0.8:
        warnings.append("Daily loss is approaching the configured limit.")
    if inputs.session.consecutive_losses >= max(0, configuration.maximum_consecutive_losses - 1):
        warnings.append("Consecutive losses are near the blocking threshold.")
    if any(e.rule in {RiskRuleType.TOTAL_EXPOSURE_LIMIT, RiskRuleType.INSTRUMENT_EXPOSURE_LIMIT} and e.result is RiskRuleResult.REDUCED for e in evaluations):
        warnings.append("Position size was reduced by the exposure cap.")
    if decision in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED}:
        warnings.append("Risk approval does not guarantee execution.")
    return tuple(warnings) or ("Risk approval does not guarantee execution.",)
