"""
Immutable Risk Engine V1 models.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time
from math import isfinite
from numbers import Real

from engines.risk.enums import (
    RiskDecision,
    RiskDecisionStatus,
    RiskLifecycleState,
    RiskReasonCode,
    RiskRejectionReason,
    RiskReductionReason,
    RiskSeverity,
    RiskTier,
)
from engines.strategy.enums import TradeDirection
from engines.strategy.models import StrategyDecisionState


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    max_risk_percent: float = 1.0
    reduced_risk_percent: float = 0.5
    max_daily_loss_percent: float = 2.0
    max_consecutive_losses: int = 2
    reduced_after_consecutive_losses: int = 1
    max_trades_per_day: int = 3
    reduced_after_trades: int = 2
    max_lots: int = 2
    minimum_reward_risk: float = 1.5
    enabled: bool = True
    risk_per_trade_percentage: float = 1.0
    maximum_risk_per_trade_amount: float | None = None
    maximum_daily_loss_amount: float | None = None
    maximum_daily_loss_percentage: float | None = 2.0
    daily_profit_lock_trigger: float | None = None
    daily_profit_giveback_limit: float | None = None
    maximum_trades_per_session: int = 3
    maximum_consecutive_losses: int = 2
    cooldown_minutes_after_loss: int = 15
    revenge_trade_window_minutes: int = 10
    minimum_reward_to_risk: float = 1.5
    maximum_stop_distance_percentage: float | None = 2.0
    minimum_stop_distance_percentage: float | None = 0.05
    maximum_total_open_risk: float | None = None
    maximum_instrument_open_risk: float | None = None
    maximum_quantity: int | None = None
    maximum_lots: int = 2
    lot_sizes_by_instrument: dict[str, int] = field(
        default_factory=lambda: {"NIFTY": 75, "BANKNIFTY": 35, "SENSEX": 20}
    )
    allow_averaging_down: bool = False
    allow_duplicate_direction: bool = False
    allow_fomo_entry: bool = False
    trading_start_time: time = time(9, 15)
    last_entry_time: time = time(14, 30)
    force_exit_time: time = time(15, 15)
    require_stop_loss: bool = True
    require_target: bool = True
    manual_approval_required: bool = True

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


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
    account_equity: float = 0.0
    realized_pnl_today: float = 0.0
    trades_today: int = 0
    consecutive_losses: int = 0
    starting_capital: float | None = None
    available_capital: float | None = None
    realized_pnl: float | None = None
    unrealized_pnl: float = 0.0
    daily_pnl: float | None = None
    open_risk: float = 0.0
    margin_used: float = 0.0
    session_date: date | None = None


@dataclass(frozen=True, slots=True)
class TradeRiskPlan:
    entry_price: float
    stop_price: float | None = None
    target_price: float | None = None
    lot_size: int = 1
    requested_lots: int = 1
    instrument: str = "NIFTY"
    direction: TradeDirection | str = TradeDirection.BULLISH
    stop_loss_price: float | None = None
    requested_quantity: int | None = None
    order_type: str = "MARKET"
    strategy_id: str | None = None
    signal_id: str | None = None
    setup_name: str | None = None
    timestamp: datetime | None = None
    is_retest_entry: bool = False
    is_fomo_entry: bool = False
    is_averaging_entry: bool = False
    is_revenge_entry: bool = False
    existing_position_direction: TradeDirection | str | None = None
    existing_position_quantity: int = 0
    manual_approval: bool = False

    @property
    def effective_stop_loss_price(self) -> float | None:
        return self.stop_loss_price if self.stop_loss_price is not None else self.stop_price

    @property
    def effective_target_price(self) -> float | None:
        return self.target_price

    def fingerprint(self) -> str:
        return _fingerprint(_model_payload(self))


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


@dataclass(frozen=True, slots=True)
class RiskFinding:
    finding_id: str
    timestamp: datetime
    severity: RiskSeverity
    code: RiskReasonCode
    message: str
    field_name: str | None = None
    observed_value: str | None = None
    limit_value: str | None = None
    occurrence_count: int = 1

    def __post_init__(self) -> None:
        _aware_datetime(self.timestamp, "timestamp")
        if not isinstance(self.severity, RiskSeverity):
            raise TypeError("severity must be RiskSeverity")
        if not isinstance(self.code, RiskReasonCode):
            raise TypeError("code must be RiskReasonCode")
        _positive_int(self.occurrence_count, "occurrence_count")
        object.__setattr__(self, "message", _safe_text(self.message, "message"))
        if not isinstance(self.finding_id, str) or not self.finding_id.strip():
            raise ValueError("finding_id must be non-empty text")


@dataclass(frozen=True, slots=True)
class SessionRiskState:
    trading_date: date
    trades_taken: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    consecutive_losses: int = 0
    last_trade_timestamp: datetime | None = None
    last_loss_timestamp: datetime | None = None
    last_entry_timestamp: datetime | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    current_open_risk: float = 0.0
    instrument_open_risk: dict[str, float] = field(default_factory=dict)
    manual_lock_active: bool = False
    emergency_lock_active: bool = False
    daily_profit_lock_active: bool = False
    peak_daily_profit: float = 0.0
    cooldown_until: datetime | None = None
    revenge_lock_until: datetime | None = None
    findings: tuple[RiskFinding, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.trading_date, datetime) or not isinstance(self.trading_date, date):
            raise TypeError("trading_date must be a date")
        for name in ("trades_taken", "winning_trades", "losing_trades", "consecutive_losses"):
            _non_negative_int(getattr(self, name), name)
        for name in ("realized_pnl", "unrealized_pnl", "current_open_risk", "peak_daily_profit"):
            _finite_real(getattr(self, name), name)
        if self.current_open_risk < 0:
            raise ValueError("current_open_risk must be non-negative")
        instrument_risk = {}
        for key, value in dict(self.instrument_open_risk).items():
            symbol = _safe_text(key, "instrument").upper()
            amount = _finite_real(value, "instrument_open_risk")
            if amount < 0:
                raise ValueError("instrument open risk must be non-negative")
            instrument_risk[symbol] = amount
        object.__setattr__(self, "instrument_open_risk", instrument_risk)
        object.__setattr__(self, "findings", tuple(self.findings[-50:]))


@dataclass(frozen=True, slots=True)
class RiskDecisionRecord:
    decision_id: str
    timestamp: datetime
    status: RiskDecisionStatus
    approved: bool
    instrument: str
    direction: TradeDirection
    requested_quantity: int
    approved_quantity: int
    requested_lots: int
    approved_lots: int
    entry_price: float
    stop_loss_price: float | None
    target_price: float | None
    risk_per_unit: float
    reward_per_unit: float
    reward_to_risk: float
    requested_trade_risk: float
    approved_trade_risk: float
    maximum_allowed_trade_risk: float
    estimated_reward: float
    capital_at_risk_percentage: float
    total_open_risk_after_trade: float
    instrument_open_risk_after_trade: float
    primary_reason: RiskReasonCode
    findings: tuple[RiskFinding, ...]
    manual_approval_required: bool
    policy_fingerprint: str
    plan_fingerprint: str
    input_fingerprint: str

    def __post_init__(self) -> None:
        _aware_datetime(self.timestamp, "timestamp")
        if not isinstance(self.status, RiskDecisionStatus):
            raise TypeError("status must be RiskDecisionStatus")
        if type(self.approved) is not bool:
            raise TypeError("approved must be bool")
        object.__setattr__(self, "instrument", _safe_text(self.instrument, "instrument").upper())
        if not isinstance(self.direction, TradeDirection):
            raise TypeError("direction must be TradeDirection")
        for name in ("requested_quantity", "approved_quantity", "requested_lots", "approved_lots"):
            _non_negative_int(getattr(self, name), name)
        for name in (
            "entry_price",
            "risk_per_unit",
            "reward_per_unit",
            "reward_to_risk",
            "requested_trade_risk",
            "approved_trade_risk",
            "maximum_allowed_trade_risk",
            "estimated_reward",
            "capital_at_risk_percentage",
            "total_open_risk_after_trade",
            "instrument_open_risk_after_trade",
        ):
            _non_negative_real(getattr(self, name), name)
        if not isinstance(self.primary_reason, RiskReasonCode):
            raise TypeError("primary_reason must be RiskReasonCode")
        object.__setattr__(self, "findings", tuple(self.findings[:50]))


@dataclass(frozen=True, slots=True)
class RiskEngineSnapshot:
    enabled: bool
    lifecycle_state: RiskLifecycleState
    trading_date: date
    manual_lock_active: bool
    emergency_lock_active: bool
    daily_profit_lock_active: bool
    trades_taken: int
    winning_trades: int
    losing_trades: int
    consecutive_losses: int
    realized_pnl: float
    unrealized_pnl: float
    daily_pnl: float
    current_open_risk: float
    instrument_open_risk: dict[str, float]
    cooldown_until: datetime | None
    revenge_lock_until: datetime | None
    last_decision: RiskDecisionRecord | None
    findings: tuple[RiskFinding, ...]
    evaluation_count: int
    approved_count: int
    reduced_size_count: int
    rejected_count: int
    locked_count: int
    broker_order_calls: int = 0


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


def _aware_datetime(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")
    return value


def _safe_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty text")
    for token in ("api_key", "api_secret", "access_token", "request_token"):
        normalized = normalized.replace(token, "[REDACTED]")
    return normalized[:500]


def _model_payload(value):
    if hasattr(value, "__dataclass_fields__"):
        return {
            key: _model_payload(getattr(value, key))
            for key in sorted(value.__dataclass_fields__)
            if key not in {"finding_id", "decision_id"}
        }
    if isinstance(value, dict):
        return {str(key): _model_payload(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_model_payload(item) for item in value]
    if isinstance(value, list):
        return [_model_payload(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    return value


def _fingerprint(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
