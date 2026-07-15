"""
Stateless Production Safety V1 evaluator.
"""

from application.enums import RuntimeStatus
from application.trade_journal_runtime_integration_v1.enums import TradeJournalRuntimeIntegrationStatus
from application.trade_lifecycle_runtime_integration_v1.enums import TradeLifecycleRuntimeIntegrationStatus
from core.enums.instrument import Instrument
from engines.production_safety_v1.configuration import ProductionSafetyV1Configuration
from engines.production_safety_v1.enums import (
    SafetyDecision,
    SafetyRuleResult,
    SafetyRuleType,
    SafetyScope,
    SafetySeverity,
)
from engines.production_safety_v1.models import ProductionSafetyV1Input, SafetyRuleEvaluation


class ProductionSafetyEvaluator:
    def evaluate(
        self,
        inputs: ProductionSafetyV1Input,
        configuration: ProductionSafetyV1Configuration,
        *,
        manual_global_lock: bool,
        manual_instrument_locks: tuple[Instrument, ...],
    ) -> tuple[SafetyRuleEvaluation, ...]:
        if not isinstance(inputs, ProductionSafetyV1Input):
            raise TypeError("inputs must be ProductionSafetyV1Input")
        if not isinstance(configuration, ProductionSafetyV1Configuration):
            raise TypeError("configuration must be ProductionSafetyV1Configuration")
        evaluations = []
        evaluations.append(_global_manual(manual_global_lock))
        for instrument in configuration.enabled_instruments:
            evaluations.append(_instrument_manual(instrument, instrument in manual_instrument_locks))
        evaluations.append(_application(inputs, configuration))
        evaluations.append(_lifecycle(inputs, configuration))
        evaluations.append(_journal(inputs, configuration))
        evaluations.append(_daily_loss(inputs, configuration))
        evaluations.append(_drawdown(inputs, configuration))
        evaluations.append(_trade_count(inputs, configuration))
        evaluations.append(_consecutive_losses(inputs, configuration))
        evaluations.extend(_active_execution(inputs, configuration))
        evaluations.extend(_active_position(inputs, configuration))
        evaluations.extend(_market_data(inputs, configuration))
        return tuple(evaluations)


def _ev(rule, scope, instrument, result, severity, decision, message, observed=None, limit=None):
    return SafetyRuleEvaluation(rule, scope, instrument, result, severity, decision, message, observed, limit)


def _global_manual(active):
    if active:
        return _ev(SafetyRuleType.MANUAL_KILL_SWITCH, SafetyScope.GLOBAL, None, SafetyRuleResult.FAILED, SafetySeverity.CRITICAL, SafetyDecision.BLOCK_GLOBAL, "Manual global kill switch is active.", "active", "inactive")
    return _ev(SafetyRuleType.MANUAL_KILL_SWITCH, SafetyScope.GLOBAL, None, SafetyRuleResult.PASSED, SafetySeverity.INFO, SafetyDecision.ALLOW, "Manual global kill switch is clear.", "inactive", "inactive")


def _instrument_manual(instrument, active):
    if active:
        return _ev(SafetyRuleType.MANUAL_KILL_SWITCH, SafetyScope.INSTRUMENT, instrument, SafetyRuleResult.FAILED, SafetySeverity.CRITICAL, SafetyDecision.BLOCK_INSTRUMENT, "Manual instrument kill switch is active.", "active", "inactive")
    return _ev(SafetyRuleType.MANUAL_KILL_SWITCH, SafetyScope.INSTRUMENT, instrument, SafetyRuleResult.PASSED, SafetySeverity.INFO, SafetyDecision.ALLOW, "Manual instrument kill switch is clear.", "inactive", "inactive")


def _application(inputs, configuration):
    failed = inputs.application_status is RuntimeStatus.ERROR and configuration.block_on_application_error
    return _ev(SafetyRuleType.APPLICATION_RUNTIME_HEALTH, SafetyScope.GLOBAL, None, SafetyRuleResult.FAILED if failed else SafetyRuleResult.PASSED, SafetySeverity.CRITICAL if failed else SafetySeverity.INFO, SafetyDecision.BLOCK_GLOBAL if failed else SafetyDecision.ALLOW, "Application runtime is unhealthy." if failed else "Application runtime is healthy.", inputs.application_status.value, RuntimeStatus.ERROR.value)


def _lifecycle(inputs, configuration):
    status = inputs.lifecycle_integration_snapshot.status
    failed = status is TradeLifecycleRuntimeIntegrationStatus.ERROR and configuration.block_on_trade_lifecycle_error
    return _ev(SafetyRuleType.TRADE_LIFECYCLE_HEALTH, SafetyScope.GLOBAL, None, SafetyRuleResult.FAILED if failed else SafetyRuleResult.PASSED, SafetySeverity.CRITICAL if failed else SafetySeverity.INFO, SafetyDecision.BLOCK_GLOBAL if failed else SafetyDecision.ALLOW, "Trade lifecycle integration is unhealthy." if failed else "Trade lifecycle integration is healthy.", status.value, TradeLifecycleRuntimeIntegrationStatus.ERROR.value)


def _journal(inputs, configuration):
    status = inputs.journal_integration_snapshot.status
    is_error = status is TradeJournalRuntimeIntegrationStatus.ERROR
    if is_error and configuration.block_on_journal_runtime_error:
        return _ev(SafetyRuleType.JOURNAL_RUNTIME_HEALTH, SafetyScope.GLOBAL, None, SafetyRuleResult.FAILED, SafetySeverity.HIGH, SafetyDecision.BLOCK_GLOBAL, "Trade journal runtime integration is unhealthy.", status.value, TradeJournalRuntimeIntegrationStatus.ERROR.value)
    if is_error:
        return _ev(SafetyRuleType.JOURNAL_RUNTIME_HEALTH, SafetyScope.GLOBAL, None, SafetyRuleResult.WARNING, SafetySeverity.MODERATE, SafetyDecision.ALLOW_WITH_WARNING, "Trade journal runtime integration is degraded.", status.value, TradeJournalRuntimeIntegrationStatus.ERROR.value)
    return _ev(SafetyRuleType.JOURNAL_RUNTIME_HEALTH, SafetyScope.GLOBAL, None, SafetyRuleResult.PASSED, SafetySeverity.INFO, SafetyDecision.ALLOW, "Trade journal runtime integration is healthy.", status.value, TradeJournalRuntimeIntegrationStatus.ERROR.value)


def _daily_loss(inputs, configuration):
    account = inputs.account_risk_state
    daily_loss = max(0.0, -(account.realized_pnl_today + account.unrealized_pnl))
    fraction = daily_loss / account.day_start_equity
    failed = fraction >= configuration.maximum_daily_loss_fraction
    return _ev(SafetyRuleType.DAILY_LOSS_LIMIT, SafetyScope.GLOBAL, None, SafetyRuleResult.FAILED if failed else SafetyRuleResult.PASSED, SafetySeverity.CRITICAL if failed else SafetySeverity.INFO, SafetyDecision.BLOCK_GLOBAL if failed else SafetyDecision.ALLOW, "Daily loss limit breached." if failed else "Daily loss is within limit.", fraction, configuration.maximum_daily_loss_fraction)


def _drawdown(inputs, configuration):
    account = inputs.account_risk_state
    current_equity = account.account_equity + account.unrealized_pnl
    fraction = max(0.0, account.peak_equity - current_equity) / account.peak_equity
    failed = fraction >= configuration.maximum_account_drawdown_fraction
    return _ev(SafetyRuleType.ACCOUNT_DRAWDOWN_LIMIT, SafetyScope.GLOBAL, None, SafetyRuleResult.FAILED if failed else SafetyRuleResult.PASSED, SafetySeverity.CRITICAL if failed else SafetySeverity.INFO, SafetyDecision.BLOCK_GLOBAL if failed else SafetyDecision.ALLOW, "Account drawdown limit breached." if failed else "Account drawdown is within limit.", fraction, configuration.maximum_account_drawdown_fraction)


def _trade_count(inputs, configuration):
    count = inputs.session_risk_state.trades_taken
    failed = count >= configuration.maximum_trades_per_day
    return _ev(SafetyRuleType.MAXIMUM_TRADES_LIMIT, SafetyScope.GLOBAL, None, SafetyRuleResult.FAILED if failed else SafetyRuleResult.PASSED, SafetySeverity.HIGH if failed else SafetySeverity.INFO, SafetyDecision.BLOCK_GLOBAL if failed else SafetyDecision.ALLOW, "Maximum trades per day reached." if failed else "Trade count is within limit.", count, configuration.maximum_trades_per_day)


def _consecutive_losses(inputs, configuration):
    count = inputs.session_risk_state.consecutive_losses
    failed = count >= configuration.maximum_consecutive_losses
    return _ev(SafetyRuleType.CONSECUTIVE_LOSS_LIMIT, SafetyScope.GLOBAL, None, SafetyRuleResult.FAILED if failed else SafetyRuleResult.PASSED, SafetySeverity.HIGH if failed else SafetySeverity.INFO, SafetyDecision.BLOCK_GLOBAL if failed else SafetyDecision.ALLOW, "Consecutive loss limit reached." if failed else "Consecutive losses are within limit.", count, configuration.maximum_consecutive_losses)


def _active_execution(inputs, configuration):
    evaluations = []
    active = {item.instrument: item.coordinator_snapshot.execution_snapshot.open_intent_count for item in inputs.lifecycle_integration_snapshot.instruments}
    for instrument in configuration.enabled_instruments:
        count = active.get(instrument, 0)
        failed = configuration.block_new_trades_with_active_execution and count > 0
        evaluations.append(_ev(SafetyRuleType.ACTIVE_EXECUTION_PRESENT, SafetyScope.INSTRUMENT, instrument, SafetyRuleResult.FAILED if failed else SafetyRuleResult.PASSED, SafetySeverity.HIGH if failed else SafetySeverity.INFO, SafetyDecision.BLOCK_INSTRUMENT if failed else SafetyDecision.ALLOW, "Active execution blocks new trades." if failed else "No active execution.", count, 0))
    return evaluations


def _active_position(inputs, configuration):
    evaluations = []
    active = {item.instrument: int(item.coordinator_snapshot.position_snapshot.has_open_position) for item in inputs.lifecycle_integration_snapshot.instruments}
    for instrument in configuration.enabled_instruments:
        count = active.get(instrument, 0)
        failed = configuration.block_new_trades_with_active_position and count > 0
        evaluations.append(_ev(SafetyRuleType.ACTIVE_POSITION_PRESENT, SafetyScope.INSTRUMENT, instrument, SafetyRuleResult.FAILED if failed else SafetyRuleResult.PASSED, SafetySeverity.HIGH if failed else SafetySeverity.INFO, SafetyDecision.BLOCK_INSTRUMENT if failed else SafetyDecision.ALLOW, "Active position blocks new trades." if failed else "No active position.", count, 0))
    return evaluations


def _market_data(inputs, configuration):
    by_instrument = dict(inputs.latest_market_data_at)
    evaluations = []
    for instrument in configuration.enabled_instruments:
        latest = by_instrument.get(instrument)
        if latest is None:
            evaluations.append(_ev(SafetyRuleType.MARKET_DATA_STALENESS, SafetyScope.INSTRUMENT, instrument, SafetyRuleResult.FAILED, SafetySeverity.CRITICAL, SafetyDecision.BLOCK_INSTRUMENT, "Market data timestamp is missing.", "missing", configuration.market_data_stale_after_seconds))
            continue
        age = (inputs.timestamp - latest).total_seconds()
        if age >= configuration.market_data_stale_after_seconds:
            evaluations.append(_ev(SafetyRuleType.MARKET_DATA_STALENESS, SafetyScope.INSTRUMENT, instrument, SafetyRuleResult.FAILED, SafetySeverity.HIGH, SafetyDecision.BLOCK_INSTRUMENT, "Market data is stale.", age, configuration.market_data_stale_after_seconds))
        elif age >= configuration.market_data_warning_after_seconds:
            evaluations.append(_ev(SafetyRuleType.MARKET_DATA_STALENESS, SafetyScope.INSTRUMENT, instrument, SafetyRuleResult.WARNING, SafetySeverity.MODERATE, SafetyDecision.ALLOW_WITH_WARNING, "Market data freshness warning.", age, configuration.market_data_warning_after_seconds))
        else:
            evaluations.append(_ev(SafetyRuleType.MARKET_DATA_STALENESS, SafetyScope.INSTRUMENT, instrument, SafetyRuleResult.PASSED, SafetySeverity.INFO, SafetyDecision.ALLOW, "Market data is fresh.", age, configuration.market_data_stale_after_seconds))
    return evaluations
