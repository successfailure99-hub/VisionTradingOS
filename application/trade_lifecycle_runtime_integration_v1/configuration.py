"""
Configuration for Trade Lifecycle Runtime Integration V1.
"""

from dataclasses import dataclass

from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.risk_management_v2.models import SUPPORTED_INSTRUMENTS


@dataclass(frozen=True, slots=True)
class TradeLifecycleRuntimeIntegrationV1Configuration:
    safety_mode: ExecutionSafetyMode = ExecutionSafetyMode.ANALYSIS_ONLY
    broker_mode: BrokerExecutionMode = BrokerExecutionMode.DRY_RUN
    enabled_instruments: tuple[Instrument, ...] = (
        Instrument.NIFTY,
        Instrument.BANKNIFTY,
        Instrument.SENSEX,
    )
    auto_start_coordinators: bool = True
    route_context_updates: bool = True
    route_position_price_updates: bool = True
    require_ready_market_context: bool = True
    require_application_running: bool = True
    reject_duplicate_context: bool = True
    history_limit: int = 120

    def __post_init__(self) -> None:
        if self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            raise ValueError("integration supports only ANALYSIS_ONLY safety mode")
        if self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("integration supports only DRY_RUN broker mode")
        instruments = tuple(self.enabled_instruments)
        if not instruments:
            raise ValueError("enabled instruments cannot be empty")
        seen = set()
        for instrument in instruments:
            if instrument not in SUPPORTED_INSTRUMENTS:
                raise ValueError("enabled instruments must be NIFTY, BANKNIFTY or SENSEX")
            if instrument in seen:
                raise ValueError("enabled instruments must be unique")
            seen.add(instrument)
        object.__setattr__(self, "enabled_instruments", instruments)
        for name in (
            "auto_start_coordinators",
            "route_context_updates",
            "route_position_price_updates",
            "require_ready_market_context",
            "require_application_running",
            "reject_duplicate_context",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if isinstance(self.history_limit, bool) or not isinstance(self.history_limit, int):
            raise TypeError("history_limit must be positive integer")
        if self.history_limit <= 0:
            raise ValueError("history_limit must be positive")
