"""
Immutable Application Orchestrator V1 models.
"""

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from brokers.zerodha.enums import BrokerExecutionMode


@dataclass(frozen=True, slots=True)
class RuntimeConfiguration:
    instruments: tuple[RuntimeInstrument, ...] = (RuntimeInstrument.NIFTY,)
    exchange: str = "NSE"
    timeframe: str = "1m"
    option_expiry_date: date = date(1970, 1, 1)
    safety_mode: ExecutionSafetyMode = ExecutionSafetyMode.ANALYSIS_ONLY

    def __post_init__(self) -> None:
        if not isinstance(self.instruments, tuple) or not self.instruments:
            raise ValueError("RuntimeConfiguration instruments must be a non-empty tuple.")
        normalized = []
        for instrument in self.instruments:
            if not isinstance(instrument, RuntimeInstrument):
                raise ValueError("RuntimeConfiguration supports only RuntimeInstrument values.")
            if instrument in normalized:
                raise ValueError("RuntimeConfiguration instruments must be unique.")
            normalized.append(instrument)
        if not isinstance(self.exchange, str) or not self.exchange.strip():
            raise ValueError("RuntimeConfiguration exchange cannot be empty.")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("RuntimeConfiguration timeframe cannot be empty.")
        if not isinstance(self.option_expiry_date, date) or isinstance(self.option_expiry_date, datetime):
            raise ValueError("RuntimeConfiguration option_expiry_date must be a date.")
        if not isinstance(self.safety_mode, ExecutionSafetyMode):
            raise ValueError("RuntimeConfiguration safety_mode must be an ExecutionSafetyMode.")
        object.__setattr__(self, "instruments", tuple(normalized))
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        object.__setattr__(self, "timeframe", self.timeframe.strip())


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    instrument: RuntimeInstrument
    status: RuntimeStatus
    exchange: str
    timeframe: str
    last_tick_timestamp: datetime | None
    latest_price: float | None
    candle_ready: bool
    vwap_ready: bool
    cpr_ready: bool
    camarilla_ready: bool
    price_action_ready: bool
    option_chain_ready: bool
    market_context_ready: bool
    ai_reasoning_ready: bool
    strategy_ready: bool
    risk_ready: bool
    latest_order_ready: bool
    position_ready: bool


@dataclass(frozen=True, slots=True)
class OrchestratorSnapshot:
    status: RuntimeStatus
    safety_mode: ExecutionSafetyMode
    broker_mode: BrokerExecutionMode
    configured_instruments: tuple[RuntimeInstrument, ...]
    shared_market_data_ready: bool
    shared_trade_journal_ready: bool
    runtime_snapshots: tuple[RuntimeSnapshot, ...]
