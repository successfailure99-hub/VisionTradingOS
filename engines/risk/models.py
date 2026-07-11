"""
Immutable Risk Engine V1 models.
"""

from dataclasses import dataclass
from datetime import datetime

from engines.risk.enums import RiskDecision, RiskRejectionReason, RiskReductionReason, RiskTier
from engines.strategy.enums import TradeDirection
from engines.strategy.models import StrategyDecisionState


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    max_risk_percent: float
    reduced_risk_percent: float
    max_daily_loss_percent: float
    max_consecutive_losses: int
    reduced_after_consecutive_losses: int
    max_trades_per_day: int
    reduced_after_trades: int
    max_lots: int
    minimum_reward_risk: float


@dataclass(frozen=True, slots=True)
class AccountRiskState:
    account_equity: float
    realized_pnl_today: float
    trades_today: int
    consecutive_losses: int


@dataclass(frozen=True, slots=True)
class TradeRiskPlan:
    entry_price: float
    stop_price: float
    target_price: float
    lot_size: int
    requested_lots: int


@dataclass(frozen=True, slots=True)
class RiskSnapshot:
    symbol: str
    timeframe: str
    timestamp: datetime
    strategy: StrategyDecisionState
    policy: RiskPolicy
    account: AccountRiskState
    trade_plan: TradeRiskPlan

    def __post_init__(self) -> None:
        if isinstance(self.symbol, str):
            object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if isinstance(self.timeframe, str):
            object.__setattr__(self, "timeframe", self.timeframe.strip())


@dataclass(frozen=True, slots=True)
class RiskDecisionState:
    symbol: str
    timeframe: str
    timestamp: datetime

    decision: RiskDecision
    risk_tier: RiskTier
    rejection_reason: RiskRejectionReason
    reduction_reason: RiskReductionReason

    direction: TradeDirection

    account_equity: float
    realized_pnl_today: float
    daily_loss_limit_amount: float
    remaining_daily_loss_capacity: float

    applied_risk_percent: float
    risk_budget: float

    entry_price: float
    stop_price: float
    target_price: float

    stop_distance: float
    target_distance: float
    reward_risk_ratio: float

    lot_size: int
    requested_lots: int
    maximum_permitted_lots: int
    approved_lots: int
    approved_quantity: int

    estimated_risk_amount: float
    estimated_reward_amount: float

    rationale: tuple[str, ...]
