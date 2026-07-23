"""
Trade Journal Runtime Integration V1 configuration.
"""

from dataclasses import dataclass

from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.risk_management_v2.models import SUPPORTED_INSTRUMENTS


@dataclass(frozen=True, slots=True)
class TradeJournalRuntimeIntegrationV1Configuration:
    safety_mode: ExecutionSafetyMode = ExecutionSafetyMode.ANALYSIS_ONLY
    broker_mode: BrokerExecutionMode = BrokerExecutionMode.DRY_RUN
    enabled_instruments: tuple[Instrument, ...] = (
        Instrument.NIFTY,
        Instrument.BANKNIFTY,
        Instrument.SENSEX,
    )
    auto_start_journal: bool = True
    auto_record_closed_positions: bool = True
    require_position_closed_stage: bool = True
    require_position_closed_outcome: bool = True
    reject_duplicate_lifecycle_identity: bool = True
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
            "auto_start_journal",
            "auto_record_closed_positions",
            "require_position_closed_stage",
            "require_position_closed_outcome",
            "reject_duplicate_lifecycle_identity",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if isinstance(self.history_limit, bool) or not isinstance(self.history_limit, int):
            raise TypeError("history_limit must be positive integer")
        if self.history_limit <= 0:
            raise ValueError("history_limit must be positive")
