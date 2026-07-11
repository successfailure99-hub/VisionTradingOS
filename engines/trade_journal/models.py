"""
Immutable Trade Journal Engine V1 models.
"""

from dataclasses import dataclass
from datetime import datetime

from engines.ai_reasoning.enums import ReasoningConfidence, TradingSuitability
from engines.ai_reasoning.models import AIReasoningState
from engines.market_context.enums import MarketBias, MarketPhase
from engines.risk.models import RiskDecisionState
from engines.strategy.enums import SetupQuality, StrategyDecision, TradeDirection
from engines.strategy.models import StrategyDecisionState
from engines.trade_journal.enums import TradeCompliance, TradeExitType, TradeOutcome


@dataclass(frozen=True, slots=True)
class TradeJournalSnapshot:
    trade_id: str

    symbol: str
    exchange: str
    timeframe: str

    opened_at: datetime
    closed_at: datetime

    direction: TradeDirection

    entry_quantity: int
    exit_quantity: int

    average_entry_price: float
    average_exit_price: float

    planned_stop_price: float
    planned_target_price: float

    planned_risk_amount: float
    planned_reward_amount: float

    realized_gross_pnl: float

    strategy: StrategyDecisionState
    risk: RiskDecisionState
    ai_reasoning: AIReasoningState

    entry_order_ids: tuple[str, ...]
    exit_order_ids: tuple[str, ...]

    exit_type: TradeExitType

    def __post_init__(self) -> None:
        if isinstance(self.trade_id, str):
            object.__setattr__(self, "trade_id", self.trade_id.strip())
        if isinstance(self.symbol, str):
            object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if isinstance(self.exchange, str):
            object.__setattr__(self, "exchange", self.exchange.strip().upper())
        if isinstance(self.timeframe, str):
            object.__setattr__(self, "timeframe", self.timeframe.strip())
        if isinstance(self.entry_order_ids, tuple):
            object.__setattr__(self, "entry_order_ids", tuple(order_id.strip() if isinstance(order_id, str) else order_id for order_id in self.entry_order_ids))
        if isinstance(self.exit_order_ids, tuple):
            object.__setattr__(self, "exit_order_ids", tuple(order_id.strip() if isinstance(order_id, str) else order_id for order_id in self.exit_order_ids))


@dataclass(frozen=True, slots=True)
class TradeJournalRecord:
    trade_id: str

    symbol: str
    exchange: str
    timeframe: str

    opened_at: datetime
    closed_at: datetime
    holding_seconds: int

    direction: TradeDirection
    outcome: TradeOutcome
    compliance: TradeCompliance
    exit_type: TradeExitType

    entry_quantity: int
    exit_quantity: int

    average_entry_price: float
    average_exit_price: float

    planned_stop_price: float
    planned_target_price: float

    planned_risk_amount: float
    planned_reward_amount: float
    realized_gross_pnl: float

    r_multiple: float | None
    reward_risk_planned: float | None

    strategy_decision: StrategyDecision
    setup_quality: SetupQuality
    market_bias: MarketBias
    market_phase: MarketPhase
    reasoning_confidence: ReasoningConfidence
    trading_suitability: TradingSuitability

    strategy_rationale: tuple[str, ...]
    ai_explanation: tuple[str, ...]
    missing_information: tuple[str, ...]

    entry_order_ids: tuple[str, ...]
    exit_order_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TradeJournalSummary:
    total_trades: int

    winning_trades: int
    losing_trades: int
    breakeven_trades: int

    compliant_trades: int
    non_compliant_trades: int

    total_gross_pnl: float
    average_trade_pnl: float

    gross_profit: float
    gross_loss: float

    win_rate: float | None
    loss_rate: float | None

    average_win: float | None
    average_loss: float | None

    profit_factor: float | None
    expectancy: float | None

    average_r_multiple: float | None
    best_trade_pnl: float | None
    worst_trade_pnl: float | None

    average_holding_seconds: float | None
