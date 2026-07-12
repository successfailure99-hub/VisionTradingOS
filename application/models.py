"""
Immutable Application Orchestrator V1 models.
"""

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from brokers.zerodha.enums import BrokerExecutionMode
from core.models.building_candle import BuildingCandle
from core.models.candle import Candle
from core.models.tick import Tick
from engines.ai_reasoning.models import AIReasoningState
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context.models import MarketContextState
from engines.option_chain.models import OptionChainState
from engines.order_management.models import OrderState
from engines.position.models import PositionState
from engines.price_action.models import PriceActionState
from engines.risk.models import RiskDecisionState
from engines.strategy.models import StrategyDecisionState
from engines.trade_journal.models import TradeJournalRecord
from engines.vwap.levels import VWAPLevels


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
        timeframe = self.timeframe.strip()
        if timeframe != "1m":
            raise ValueError("Application Orchestrator V1 supports only timeframe '1m'.")
        if not isinstance(self.option_expiry_date, date) or isinstance(self.option_expiry_date, datetime):
            raise ValueError("RuntimeConfiguration option_expiry_date must be a date.")
        if not isinstance(self.safety_mode, ExecutionSafetyMode):
            raise ValueError("RuntimeConfiguration safety_mode must be an ExecutionSafetyMode.")
        object.__setattr__(self, "instruments", tuple(normalized))
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        object.__setattr__(self, "timeframe", timeframe)


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    symbol: RuntimeInstrument
    timeframe: str
    status: RuntimeStatus
    latest_tick: Tick | None
    latest_candle: BuildingCandle | Candle | None
    vwap: VWAPLevels | None
    cpr: CPRLevels | None
    camarilla: CamarillaLevels | None
    price_action: PriceActionState | None
    option_chain: OptionChainState | None
    market_context: MarketContextState | None
    ai_reasoning: AIReasoningState | None
    strategy: StrategyDecisionState | None
    risk: RiskDecisionState | None
    latest_order: OrderState | None
    position: PositionState | None
    latest_journal_record: TradeJournalRecord | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class OrchestratorSnapshot:
    status: RuntimeStatus
    safety_mode: ExecutionSafetyMode
    broker_mode: BrokerExecutionMode
    configured_instruments: tuple[RuntimeInstrument, ...]
    shared_market_data_ready: bool
    shared_trade_journal_ready: bool
    runtime_snapshots: tuple[RuntimeSnapshot, ...]
