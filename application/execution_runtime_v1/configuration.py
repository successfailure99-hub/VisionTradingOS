"""
Configuration for Execution Runtime V1.
"""

from dataclasses import dataclass

from application.enums import ExecutionSafetyMode
from application.execution_runtime_v1.enums import ExecutionFillPolicy, ExecutionOrderType
from brokers.zerodha.enums import BrokerExecutionMode


@dataclass(frozen=True, slots=True)
class ExecutionRuntimeV1Configuration:
    broker_mode: BrokerExecutionMode = BrokerExecutionMode.DRY_RUN
    safety_mode: ExecutionSafetyMode = ExecutionSafetyMode.ANALYSIS_ONLY

    order_type: ExecutionOrderType = ExecutionOrderType.LIMIT
    fill_policy: ExecutionFillPolicy = ExecutionFillPolicy.MANUAL_CONFIRMATION

    allow_partial_fill: bool = True
    require_manual_fill_confirmation: bool = True
    reject_zero_quantity: bool = True
    require_risk_execution_eligibility: bool = True

    maximum_open_intents: int = 1
    history_limit: int = 120

    def __post_init__(self) -> None:
        if self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("Execution Runtime V1 supports only DRY_RUN broker mode")
        if self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            raise ValueError("Execution Runtime V1 supports only ANALYSIS_ONLY safety mode")
        if not isinstance(self.order_type, ExecutionOrderType):
            raise TypeError("order_type must be ExecutionOrderType")
        if not isinstance(self.fill_policy, ExecutionFillPolicy):
            raise TypeError("fill_policy must be ExecutionFillPolicy")
        for name in (
            "allow_partial_fill",
            "require_manual_fill_confirmation",
            "reject_zero_quantity",
            "require_risk_execution_eligibility",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        for name in ("maximum_open_intents", "history_limit"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be positive integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.fill_policy is ExecutionFillPolicy.MANUAL_CONFIRMATION and not self.require_manual_fill_confirmation:
            raise ValueError("manual confirmation policy requires manual confirmation flag")
