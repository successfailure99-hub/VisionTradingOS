"""
Configuration for Trade Lifecycle Coordinator V1.
"""

from dataclasses import dataclass

from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode


@dataclass(frozen=True, slots=True)
class TradeLifecycleV1Configuration:
    safety_mode: ExecutionSafetyMode = ExecutionSafetyMode.ANALYSIS_ONLY
    broker_mode: BrokerExecutionMode = BrokerExecutionMode.DRY_RUN
    auto_submit_risk_approved_execution: bool = True
    auto_open_position_on_fill: bool = True
    allow_partial_fill_position_open: bool = True
    stop_on_strategy_wait: bool = True
    stop_on_strategy_no_trade: bool = True
    stop_on_risk_wait: bool = True
    stop_on_risk_rejection: bool = True
    require_execution_runtime_running: bool = True
    require_no_active_position_before_new_trade: bool = True
    history_limit: int = 120

    def __post_init__(self) -> None:
        if self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            raise ValueError("Trade Lifecycle Coordinator V1 supports only ANALYSIS_ONLY safety mode")
        if self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("Trade Lifecycle Coordinator V1 supports only DRY_RUN broker mode")
        for name in (
            "auto_submit_risk_approved_execution",
            "auto_open_position_on_fill",
            "allow_partial_fill_position_open",
            "stop_on_strategy_wait",
            "stop_on_strategy_no_trade",
            "stop_on_risk_wait",
            "stop_on_risk_rejection",
            "require_execution_runtime_running",
            "require_no_active_position_before_new_trade",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if isinstance(self.history_limit, bool) or not isinstance(self.history_limit, int):
            raise TypeError("history_limit must be positive integer")
        if self.history_limit <= 0:
            raise ValueError("history_limit must be positive")
