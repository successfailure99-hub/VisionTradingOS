"""
Eligibility validation for Execution Runtime V1.
"""

from application.enums import ExecutionSafetyMode
from application.execution_runtime_v1.configuration import ExecutionRuntimeV1Configuration
from application.execution_runtime_v1.enums import ExecutionDecision, ExecutionSide
from application.execution_runtime_v1.models import side_from_risk
from brokers.zerodha.enums import BrokerExecutionMode
from engines.risk_management_v2.enums import RiskDecision
from engines.risk_management_v2.models import RiskManagementV2Snapshot
from engines.strategy_decision_v2.enums import StrategyAction


class ExecutionEligibilityValidator:
    def validate(
        self,
        risk: RiskManagementV2Snapshot,
        configuration: ExecutionRuntimeV1Configuration,
    ) -> tuple[ExecutionDecision, tuple[str, ...]]:
        if not isinstance(risk, RiskManagementV2Snapshot):
            raise TypeError("risk must be RiskManagementV2Snapshot")
        messages: list[str] = []
        if configuration.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            return ExecutionDecision.REJECTED, ("Execution Runtime V1 requires ANALYSIS_ONLY safety mode.",)
        if configuration.broker_mode is not BrokerExecutionMode.DRY_RUN:
            return ExecutionDecision.REJECTED, ("Execution Runtime V1 requires DRY_RUN broker mode.",)
        if risk.decision is RiskDecision.WAIT:
            return ExecutionDecision.WAIT, ("Risk Management V2 decision is WAIT.",)
        if risk.decision is RiskDecision.INSUFFICIENT_DATA:
            return ExecutionDecision.INSUFFICIENT_DATA, ("Risk Management V2 decision has insufficient data.",)
        if risk.decision is RiskDecision.REJECTED:
            return ExecutionDecision.REJECTED, ("Risk Management V2 rejected execution eligibility.",)
        if configuration.require_risk_execution_eligibility and not risk.execution_eligible:
            messages.append("Risk snapshot is not execution eligible.")
        if risk.decision not in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED}:
            messages.append("Risk decision is not approved.")
        if configuration.reject_zero_quantity and risk.approved_quantity <= 0:
            messages.append("Approved quantity must be positive.")
        if risk.strategy.action not in {StrategyAction.CONSIDER_LONG, StrategyAction.CONSIDER_SHORT}:
            messages.append("Strategy action is not executable.")
        if not risk.strategy.eligible:
            messages.append("Strategy is not eligible.")
        if not risk.strategy.risk_handoff.requires_risk_review:
            messages.append("Risk handoff does not require execution review.")
        if side_from_risk(risk) is ExecutionSide.NONE:
            messages.append("Strategy direction cannot map to execution side.")
        if messages:
            return ExecutionDecision.REJECTED, tuple(messages)
        return ExecutionDecision.ACCEPTED, ("Risk-approved decision is eligible for dry-run execution review.",)
