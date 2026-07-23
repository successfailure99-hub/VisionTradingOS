"""
Rule validation for Risk Management Engine V2.
"""

from engines.risk_management_v2.configuration import RiskManagementV2Configuration
from engines.risk_management_v2.enums import RiskRuleResult, RiskRuleType, RiskSeverity
from engines.risk_management_v2.models import RiskManagementV2Input, RiskRuleEvaluation
from engines.strategy_decision_v2.enums import (
    StrategyAction,
    StrategyDecisionQuality,
    StrategySetupStatus,
)


class RiskRuleValidator:
    def evaluate(
        self,
        inputs: RiskManagementV2Input,
        configuration: RiskManagementV2Configuration,
    ) -> tuple[RiskRuleEvaluation, ...]:
        risk_distance = abs(inputs.proposed_entry_price - inputs.proposed_invalidation_price)
        reward_risk = _calculate_reward_risk(inputs, risk_distance)
        projected_unit = inputs.proposed_entry_price * inputs.contract_multiplier
        current_equity = inputs.account.current_equity
        total_limit = current_equity * configuration.maximum_total_exposure_fraction
        instrument_limit = current_equity * configuration.maximum_instrument_exposure_fraction
        return (
            _strategy(inputs),
            _daily_loss(inputs, configuration),
            _drawdown(inputs, configuration),
            _consecutive_losses(inputs, configuration),
            _trade_count(inputs, configuration),
            _capital(inputs),
            _invalidation(inputs, configuration, risk_distance),
            _objective(inputs, configuration),
            _reward_risk_rule(reward_risk, configuration),
            _per_trade_risk(inputs, configuration, risk_distance),
            _total_exposure(inputs, projected_unit, total_limit),
            _instrument_exposure(inputs, projected_unit, instrument_limit),
            _position_cap(configuration),
            _quality(inputs, configuration),
        )


def _evaluation(rule, result, severity, message, observed=None, limit=None):
    return RiskRuleEvaluation(rule, result, severity, message, observed, limit)


def _strategy(inputs):
    strategy = inputs.strategy
    if strategy.action is StrategyAction.WAIT or strategy.setup_status in {
        StrategySetupStatus.WAITING_FOR_TRIGGER,
        StrategySetupStatus.WAITING_FOR_RETEST,
    }:
        return _evaluation(RiskRuleType.STRATEGY_ELIGIBILITY, RiskRuleResult.FAILED, RiskSeverity.LOW, "Strategy Decision V2 is waiting for confirmation.")
    if strategy.action is StrategyAction.INSUFFICIENT_DATA:
        return _evaluation(RiskRuleType.STRATEGY_ELIGIBILITY, RiskRuleResult.FAILED, RiskSeverity.MODERATE, "Strategy Decision V2 has insufficient data.")
    if strategy.action is StrategyAction.NO_TRADE:
        return _evaluation(RiskRuleType.STRATEGY_ELIGIBILITY, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Strategy Decision V2 is no trade.")
    if not strategy.eligible or not strategy.risk_handoff.requires_risk_review or strategy.setup_status is not StrategySetupStatus.READY_FOR_RISK_REVIEW:
        return _evaluation(RiskRuleType.STRATEGY_ELIGIBILITY, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Strategy Decision V2 is not eligible for risk review.")
    return _evaluation(RiskRuleType.STRATEGY_ELIGIBILITY, RiskRuleResult.PASSED, RiskSeverity.NONE, "Strategy Decision V2 is eligible for risk review.")


def _daily_loss(inputs, configuration):
    observed = inputs.account.daily_loss_fraction
    if observed >= configuration.maximum_daily_loss_fraction:
        return _evaluation(RiskRuleType.DAILY_LOSS_LIMIT, RiskRuleResult.FAILED, RiskSeverity.CRITICAL, "Daily loss limit is reached.", observed, configuration.maximum_daily_loss_fraction)
    return _evaluation(RiskRuleType.DAILY_LOSS_LIMIT, RiskRuleResult.PASSED, RiskSeverity.NONE, "Daily loss remains within bounds.", observed, configuration.maximum_daily_loss_fraction)


def _drawdown(inputs, configuration):
    observed = inputs.account.drawdown_fraction
    if observed >= configuration.maximum_account_drawdown_fraction:
        return _evaluation(RiskRuleType.ACCOUNT_DRAWDOWN_LIMIT, RiskRuleResult.FAILED, RiskSeverity.CRITICAL, "Account drawdown limit is reached.", observed, configuration.maximum_account_drawdown_fraction)
    return _evaluation(RiskRuleType.ACCOUNT_DRAWDOWN_LIMIT, RiskRuleResult.PASSED, RiskSeverity.NONE, "Account drawdown remains within bounds.", observed, configuration.maximum_account_drawdown_fraction)


def _consecutive_losses(inputs, configuration):
    if not configuration.block_after_consecutive_losses:
        return _evaluation(RiskRuleType.CONSECUTIVE_LOSS_LIMIT, RiskRuleResult.NOT_APPLICABLE, RiskSeverity.NONE, "Consecutive-loss blocking is disabled.", inputs.session.consecutive_losses, configuration.maximum_consecutive_losses)
    if inputs.session.consecutive_losses >= configuration.maximum_consecutive_losses:
        return _evaluation(RiskRuleType.CONSECUTIVE_LOSS_LIMIT, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Consecutive-loss limit is reached.", inputs.session.consecutive_losses, configuration.maximum_consecutive_losses)
    return _evaluation(RiskRuleType.CONSECUTIVE_LOSS_LIMIT, RiskRuleResult.PASSED, RiskSeverity.NONE, "Consecutive losses remain within bounds.", inputs.session.consecutive_losses, configuration.maximum_consecutive_losses)


def _trade_count(inputs, configuration):
    if inputs.session.trades_taken >= configuration.maximum_trades_per_day:
        return _evaluation(RiskRuleType.MAX_TRADES_PER_DAY, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Maximum trades per day is reached.", inputs.session.trades_taken, configuration.maximum_trades_per_day)
    return _evaluation(RiskRuleType.MAX_TRADES_PER_DAY, RiskRuleResult.PASSED, RiskSeverity.NONE, "Trade count remains within bounds.", inputs.session.trades_taken, configuration.maximum_trades_per_day)


def _capital(inputs):
    if inputs.account.available_capital <= 0.0 or inputs.account.current_equity <= 0.0:
        return _evaluation(RiskRuleType.CAPITAL_AVAILABLE, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Available capital is not sufficient.", inputs.account.available_capital, 0)
    return _evaluation(RiskRuleType.CAPITAL_AVAILABLE, RiskRuleResult.PASSED, RiskSeverity.NONE, "Available capital is positive.", inputs.account.available_capital, None)


def _invalidation(inputs, configuration, risk_distance):
    if risk_distance <= 0.0:
        return _evaluation(RiskRuleType.INVALIDATION_REQUIRED, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Invalidation distance must be positive.", risk_distance, 0)
    return _evaluation(RiskRuleType.INVALIDATION_REQUIRED, RiskRuleResult.PASSED, RiskSeverity.NONE, "Structural invalidation is available.", risk_distance, None)


def _objective(inputs, configuration):
    if configuration.require_structural_objective and inputs.proposed_objective_price is None:
        return _evaluation(RiskRuleType.OBJECTIVE_REQUIRED, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Structural objective is required.")
    return _evaluation(RiskRuleType.OBJECTIVE_REQUIRED, RiskRuleResult.PASSED, RiskSeverity.NONE, "Structural objective requirement is satisfied.")


def _reward_risk_rule(value, configuration):
    if value is None:
        return _evaluation(RiskRuleType.MINIMUM_REWARD_RISK, RiskRuleResult.NOT_APPLICABLE, RiskSeverity.NONE, "Reward-risk is not required.", None, configuration.minimum_reward_risk_ratio)
    if value < configuration.minimum_reward_risk_ratio:
        return _evaluation(RiskRuleType.MINIMUM_REWARD_RISK, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Reward-risk ratio is below minimum.", value, configuration.minimum_reward_risk_ratio)
    return _evaluation(RiskRuleType.MINIMUM_REWARD_RISK, RiskRuleResult.PASSED, RiskSeverity.NONE, "Reward-risk ratio meets minimum.", value, configuration.minimum_reward_risk_ratio)


def _calculate_reward_risk(inputs, risk_distance):
    if inputs.proposed_objective_price is None:
        return None
    if inputs.strategy.direction.value == "long":
        reward_distance = inputs.proposed_objective_price - inputs.proposed_entry_price
    elif inputs.strategy.direction.value == "short":
        reward_distance = inputs.proposed_entry_price - inputs.proposed_objective_price
    else:
        return None
    return reward_distance / risk_distance if risk_distance > 0.0 else None


def _per_trade_risk(inputs, configuration, risk_distance):
    risk_amount = risk_distance * inputs.contract_multiplier * inputs.quantity_step
    limit = inputs.account.current_equity * configuration.maximum_risk_per_trade_fraction
    if risk_amount > limit:
        return _evaluation(RiskRuleType.PER_TRADE_RISK_LIMIT, RiskRuleResult.REDUCED, RiskSeverity.MODERATE, "Per-trade risk requires quantity control.", risk_amount, limit)
    return _evaluation(RiskRuleType.PER_TRADE_RISK_LIMIT, RiskRuleResult.PASSED, RiskSeverity.NONE, "Per-trade risk remains within bounds.", risk_amount, limit)


def _total_exposure(inputs, projected_unit, limit):
    remaining = limit - inputs.account.current_total_exposure
    if remaining < projected_unit:
        return _evaluation(RiskRuleType.TOTAL_EXPOSURE_LIMIT, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Total exposure capacity cannot support minimum quantity.", remaining, projected_unit)
    return _evaluation(RiskRuleType.TOTAL_EXPOSURE_LIMIT, RiskRuleResult.PASSED, RiskSeverity.NONE, "Total exposure has available capacity.", inputs.account.current_total_exposure, limit)


def _instrument_exposure(inputs, projected_unit, limit):
    remaining = limit - inputs.instrument_exposure.current_notional_exposure
    if remaining < projected_unit:
        return _evaluation(RiskRuleType.INSTRUMENT_EXPOSURE_LIMIT, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Instrument exposure capacity cannot support minimum quantity.", remaining, projected_unit)
    return _evaluation(RiskRuleType.INSTRUMENT_EXPOSURE_LIMIT, RiskRuleResult.PASSED, RiskSeverity.NONE, "Instrument exposure has available capacity.", inputs.instrument_exposure.current_notional_exposure, limit)


def _position_cap(configuration):
    return _evaluation(RiskRuleType.MAX_POSITION_QUANTITY, RiskRuleResult.PASSED, RiskSeverity.NONE, "Configured maximum quantity is available.", configuration.maximum_position_quantity, configuration.maximum_position_quantity)


def _quality(inputs, configuration):
    if inputs.strategy.quality is StrategyDecisionQuality.UNAVAILABLE:
        return _evaluation(RiskRuleType.STRATEGY_ELIGIBILITY, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Strategy quality is unavailable.")
    if inputs.strategy.quality is StrategyDecisionQuality.LOW:
        if configuration.reject_low_quality_setups:
            return _evaluation(RiskRuleType.STRATEGY_ELIGIBILITY, RiskRuleResult.FAILED, RiskSeverity.HIGH, "Low-quality setup is rejected.")
        return _evaluation(RiskRuleType.STRATEGY_ELIGIBILITY, RiskRuleResult.REDUCED, RiskSeverity.MODERATE, "Low-quality setup uses reduced risk.")
    if inputs.strategy.quality is StrategyDecisionQuality.MODERATE and configuration.reduce_moderate_quality_setups:
        return _evaluation(RiskRuleType.STRATEGY_ELIGIBILITY, RiskRuleResult.REDUCED, RiskSeverity.LOW, "Moderate-quality setup uses reduced risk.")
    return _evaluation(RiskRuleType.STRATEGY_ELIGIBILITY, RiskRuleResult.PASSED, RiskSeverity.NONE, "Setup quality supports configured risk.")
