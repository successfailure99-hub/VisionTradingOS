"""
Immutable Risk Engine V1 models.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real

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
class InstrumentLotSize:
    symbol: str
    lot_size: int

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol must be non-empty text")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        _positive_int(self.lot_size, "lot_size")


@dataclass(frozen=True, slots=True)
class RiskConfiguration:
    capital: float | None = None
    risk_per_trade_percentage: float = 1.0
    maximum_risk_per_trade_amount: float | None = None
    maximum_lots: int = 2
    minimum_reward_risk: float = 1.5
    maximum_stop_distance_percentage: float = 1.0
    maximum_trades_per_day: int = 3
    maximum_daily_loss: float = 0.0
    minimum_confidence: str = "medium"
    allowed_market_sessions: tuple[str, ...] = ("LIVE",)
    allow_low_confidence: bool = False
    allow_mixed_signals: bool = False
    trade_plan_validity_minutes: int = 15
    max_data_age_seconds: int = 300
    lot_sizes: tuple[InstrumentLotSize, ...] = ()

    def __post_init__(self) -> None:
        if self.capital is not None:
            _positive_real(self.capital, "capital")
        _percentage(self.risk_per_trade_percentage, "risk_per_trade_percentage")
        if self.maximum_risk_per_trade_amount is not None:
            _positive_real(self.maximum_risk_per_trade_amount, "maximum_risk_per_trade_amount")
        _positive_int(self.maximum_lots, "maximum_lots")
        _positive_real(self.minimum_reward_risk, "minimum_reward_risk")
        _percentage(self.maximum_stop_distance_percentage, "maximum_stop_distance_percentage")
        _positive_int(self.maximum_trades_per_day, "maximum_trades_per_day")
        _non_negative_real(self.maximum_daily_loss, "maximum_daily_loss")
        _positive_int(self.trade_plan_validity_minutes, "trade_plan_validity_minutes")
        _positive_int(self.max_data_age_seconds, "max_data_age_seconds")
        if not isinstance(self.minimum_confidence, str) or not self.minimum_confidence.strip():
            raise ValueError("minimum_confidence must be non-empty text")
        object.__setattr__(self, "minimum_confidence", self.minimum_confidence.strip().lower())
        sessions = tuple(str(item).strip().upper() for item in self.allowed_market_sessions if str(item).strip())
        if not sessions:
            raise ValueError("allowed_market_sessions cannot be empty")
        object.__setattr__(self, "allowed_market_sessions", sessions)
        for name in ("allow_low_confidence", "allow_mixed_signals"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        lots = tuple(self.lot_sizes)
        if any(not isinstance(item, InstrumentLotSize) for item in lots):
            raise TypeError("lot_sizes must contain InstrumentLotSize values")
        if len({item.symbol for item in lots}) != len(lots):
            raise ValueError("lot_sizes must be unique by symbol")
        object.__setattr__(self, "lot_sizes", lots)

    def lot_size_for(self, symbol: str) -> int | None:
        normalized = symbol.strip().upper() if isinstance(symbol, str) else ""
        for item in self.lot_sizes:
            if item.symbol == normalized:
                return item.lot_size
        return None

    @property
    def risk_budget(self) -> float | None:
        if self.capital is None:
            return None
        percent_budget = self.capital * self.risk_per_trade_percentage / 100
        if self.maximum_risk_per_trade_amount is None:
            return round(percent_budget, 2)
        return round(min(percent_budget, self.maximum_risk_per_trade_amount), 2)


@dataclass(frozen=True, slots=True)
class DailyRiskState:
    trading_date: object
    plans_approved: int = 0
    trades_completed: int = 0
    realized_pnl: float = 0.0
    risk_reserved: float = 0.0

    def __post_init__(self) -> None:
        _non_negative_int(self.plans_approved, "plans_approved")
        _non_negative_int(self.trades_completed, "trades_completed")
        _finite_real(self.realized_pnl, "realized_pnl")
        _non_negative_real(self.risk_reserved, "risk_reserved")


@dataclass(frozen=True, slots=True)
class TradePlan:
    plan_id: str
    instrument: str
    created_at: datetime
    strategy_direction: TradeDirection
    strategy_setup: str
    entry_type: str
    entry_price: float
    stop_price: float
    target_price: float
    lot_size: int
    approved_lots: int
    approved_quantity: int
    risk_amount: float
    reward_amount: float
    reward_risk: float
    valid_from: datetime
    valid_until: datetime
    status: str
    reasoning: tuple[str, ...]
    source_strategy_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, str) or not self.plan_id.strip():
            raise ValueError("plan_id must be non-empty text")
        if not isinstance(self.instrument, str) or not self.instrument.strip():
            raise ValueError("instrument must be non-empty text")
        object.__setattr__(self, "instrument", self.instrument.strip().upper())
        for name in ("created_at", "valid_from", "valid_until"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware datetime")
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        if not isinstance(self.strategy_direction, TradeDirection) or self.strategy_direction is TradeDirection.NONE:
            raise ValueError("strategy_direction must be bullish or bearish")
        for name in ("entry_price", "stop_price", "target_price", "risk_amount", "reward_amount", "reward_risk"):
            _positive_real(getattr(self, name), name)
        _positive_int(self.lot_size, "lot_size")
        _positive_int(self.approved_lots, "approved_lots")
        _positive_int(self.approved_quantity, "approved_quantity")
        if self.approved_quantity != self.approved_lots * self.lot_size:
            raise ValueError("approved_quantity must equal approved_lots * lot_size")
        if self.strategy_direction is TradeDirection.BULLISH and not (self.stop_price < self.entry_price < self.target_price):
            raise ValueError("bullish plan requires stop < entry < target")
        if self.strategy_direction is TradeDirection.BEARISH and not (self.target_price < self.entry_price < self.stop_price):
            raise ValueError("bearish plan requires target < entry < stop")
        if self.status not in {"READY", "REJECTED", "EXPIRED"}:
            raise ValueError("status must be READY, REJECTED or EXPIRED")
        object.__setattr__(self, "reasoning", tuple(str(item).strip() for item in self.reasoning if str(item).strip()))
        if not self.reasoning:
            raise ValueError("reasoning cannot be empty")
        if not isinstance(self.source_strategy_id, str) or not self.source_strategy_id.strip():
            raise ValueError("source_strategy_id must be non-empty text")


@dataclass(frozen=True, slots=True)
class RiskEvaluation:
    instrument: str
    evaluated_at: datetime
    approved: bool
    status: str
    risk_level: str
    rejection_code: str
    rejection_reason: str
    warnings: tuple[str, ...]
    capital: float | None
    risk_budget: float | None
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    stop_distance: float | None
    target_distance: float | None
    reward_risk: float | None
    lot_size: int | None
    requested_lots: int
    approved_lots: int
    approved_quantity: int
    estimated_risk_amount: float
    estimated_reward_amount: float
    daily_trade_count: int
    daily_realized_pnl: float
    daily_remaining_risk: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, str) or not self.instrument.strip():
            raise ValueError("instrument must be non-empty text")
        object.__setattr__(self, "instrument", self.instrument.strip().upper())
        if not isinstance(self.evaluated_at, datetime) or self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware datetime")
        if type(self.approved) is not bool:
            raise TypeError("approved must be bool")
        for name in ("requested_lots", "approved_lots", "approved_quantity", "daily_trade_count"):
            _non_negative_int(getattr(self, name), name)
        for name in ("estimated_risk_amount", "estimated_reward_amount"):
            _non_negative_real(getattr(self, name), name)
        _finite_real(self.daily_realized_pnl, "daily_realized_pnl")
        if not self.approved and (self.approved_lots != 0 or self.approved_quantity != 0):
            raise ValueError("rejected evaluation cannot contain approved quantity")
        object.__setattr__(self, "warnings", tuple(str(item).strip() for item in self.warnings if str(item).strip()))


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
    plan_id: str | None = None
    plan_status: str = "-"
    valid_until: datetime | None = None
    risk_reason: str | None = None
    trade_plan_ready: bool = False


def _finite_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _positive_real(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def _non_negative_real(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _percentage(value: Real, name: str) -> float:
    number = _positive_real(value, name)
    if number > 100:
        raise ValueError(f"{name} must be at most 100")
    return number


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be positive integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be non-negative integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
