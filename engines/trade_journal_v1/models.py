"""
Immutable Trade Journal & Performance Analytics V1 models.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real

from application.execution_runtime_v1.enums import ExecutionSide
from application.trade_lifecycle_v1.models import TradeLifecycleV1Snapshot
from core.enums.instrument import Instrument
from engines.position_management_v1.enums import PositionExitReason
from engines.risk_management_v2.enums import RiskDecision
from engines.risk_management_v2.models import SUPPORTED_INSTRUMENTS
from engines.strategy_decision_v2.enums import (
    StrategyDecisionQuality,
    StrategyDirection,
    StrategySetupFamily,
)
from engines.trade_journal_v1.enums import (
    JournalChange,
    PerformanceTrend,
    TradeCloseCategory,
    TradeJournalStatus,
    TradeOutcome,
    TradeRecordStatus,
)


@dataclass(frozen=True, slots=True)
class TradeJournalEntry:
    trade_id: str
    instrument: Instrument
    opened_at: datetime
    closed_at: datetime
    duration_seconds: float
    direction: StrategyDirection
    setup_family: StrategySetupFamily
    setup_quality: StrategyDecisionQuality
    entry_price: float
    average_exit_price: float
    initial_quantity: int
    closed_quantity: int
    invalidation_price: float
    objective_price: float | None
    realized_pnl: float
    risk_amount: float
    r_multiple: float | None
    outcome: TradeOutcome
    exit_reason: PositionExitReason
    close_category: TradeCloseCategory
    market_state: str
    market_phase: str
    structural_confidence: str
    context_confidence: float
    reasoning_direction: str
    reasoning_conviction: str
    reasoning_confidence: float
    risk_decision: RiskDecision
    risk_approved_quantity: int
    execution_side: ExecutionSide
    execution_fill_price: float
    execution_filled_quantity: int
    lifecycle_snapshot: TradeLifecycleV1Snapshot

    def __post_init__(self) -> None:
        _non_empty(self.trade_id, "trade_id")
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.opened_at, "opened_at")
        _aware(self.closed_at, "closed_at")
        if self.closed_at < self.opened_at:
            raise ValueError("closed_at cannot precede opened_at")
        object.__setattr__(self, "duration_seconds", _non_negative_real(self.duration_seconds, "duration_seconds"))
        for name in ("direction", "setup_family", "setup_quality", "outcome", "exit_reason", "close_category", "risk_decision", "execution_side"):
            value = getattr(self, name)
            enum_type = _ENTRY_ENUMS[name]
            if not isinstance(value, enum_type):
                raise TypeError(f"{name} must be {enum_type.__name__}")
        for name in ("market_state", "market_phase", "structural_confidence", "reasoning_direction", "reasoning_conviction"):
            object.__setattr__(self, name, _non_empty(getattr(self, name), name))
        for name in ("entry_price", "average_exit_price", "invalidation_price", "execution_fill_price"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        if self.objective_price is not None:
            object.__setattr__(self, "objective_price", _positive_real(self.objective_price, "objective_price"))
        _positive_int(self.initial_quantity, "initial_quantity")
        _positive_int(self.closed_quantity, "closed_quantity")
        if self.closed_quantity > self.initial_quantity:
            raise ValueError("closed quantity cannot exceed initial quantity")
        object.__setattr__(self, "realized_pnl", _finite_real(self.realized_pnl, "realized_pnl"))
        object.__setattr__(self, "risk_amount", _non_negative_real(self.risk_amount, "risk_amount"))
        if self.r_multiple is not None:
            object.__setattr__(self, "r_multiple", _finite_real(self.r_multiple, "r_multiple"))
        object.__setattr__(self, "context_confidence", _bounded(self.context_confidence, "context_confidence"))
        object.__setattr__(self, "reasoning_confidence", _bounded(self.reasoning_confidence, "reasoning_confidence"))
        _non_negative_int(self.risk_approved_quantity, "risk_approved_quantity")
        _positive_int(self.execution_filled_quantity, "execution_filled_quantity")
        if not isinstance(self.lifecycle_snapshot, TradeLifecycleV1Snapshot):
            raise TypeError("lifecycle_snapshot must be TradeLifecycleV1Snapshot")
        if self.lifecycle_snapshot.instrument is not self.instrument:
            raise ValueError("lifecycle snapshot instrument mismatch")
        position = self.lifecycle_snapshot.position_result.position if self.lifecycle_snapshot.position_result else None
        if position is None or position.open_quantity != 0 or position.closed_at is None:
            raise ValueError("lifecycle snapshot must contain a closed position")
        if position.dry_run is not True or position.analysis_only is not True:
            raise ValueError("journal entries must remain dry-run and analysis-only")


@dataclass(frozen=True, slots=True)
class TradeJournalRecordResult:
    status: TradeRecordStatus
    entry: TradeJournalEntry | None
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, TradeRecordStatus):
            raise TypeError("status must be TradeRecordStatus")
        if self.entry is not None and not isinstance(self.entry, TradeJournalEntry):
            raise TypeError("entry must be TradeJournalEntry or None")
        if self.status is TradeRecordStatus.RECORDED and self.entry is None:
            raise ValueError("RECORDED requires entry")
        _non_empty(self.message, "message")


@dataclass(frozen=True, slots=True)
class EquityCurvePoint:
    sequence: int
    timestamp: datetime
    trade_id: str
    realized_pnl: float
    cumulative_pnl: float
    equity_peak: float
    drawdown_amount: float
    drawdown_fraction: float | None

    def __post_init__(self) -> None:
        _positive_int(self.sequence, "sequence")
        _aware(self.timestamp, "timestamp")
        _non_empty(self.trade_id, "trade_id")
        for name in ("realized_pnl", "cumulative_pnl", "equity_peak"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))
        object.__setattr__(self, "drawdown_amount", _non_negative_real(self.drawdown_amount, "drawdown_amount"))
        if self.drawdown_fraction is not None:
            object.__setattr__(self, "drawdown_fraction", _bounded(self.drawdown_fraction, "drawdown_fraction"))


@dataclass(frozen=True, slots=True)
class TradePerformanceStatistics:
    trade_count: int
    win_count: int
    loss_count: int
    flat_count: int
    win_rate: float | None
    loss_rate: float | None
    total_pnl: float
    gross_profit: float
    gross_loss: float
    net_pnl: float
    average_trade: float | None
    average_win: float | None
    average_loss: float | None
    largest_win: float | None
    largest_loss: float | None
    expectancy: float | None
    profit_factor: float | None
    average_r_multiple: float | None
    maximum_r_multiple: float | None
    minimum_r_multiple: float | None
    maximum_drawdown_amount: float
    maximum_drawdown_fraction: float | None
    current_winning_streak: int
    current_losing_streak: int
    maximum_winning_streak: int
    maximum_losing_streak: int
    trend: PerformanceTrend

    def __post_init__(self) -> None:
        for name in ("trade_count", "win_count", "loss_count", "flat_count", "current_winning_streak", "current_losing_streak", "maximum_winning_streak", "maximum_losing_streak"):
            _non_negative_int(getattr(self, name), name)
        if self.win_count + self.loss_count + self.flat_count != self.trade_count:
            raise ValueError("win + loss + flat must equal trade count")
        for name in ("win_rate", "loss_rate", "maximum_drawdown_fraction"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _bounded(value, name))
        for name in ("total_pnl", "gross_profit", "gross_loss", "net_pnl"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))
        for name in ("average_trade", "average_win", "average_loss", "largest_win", "largest_loss", "expectancy", "profit_factor", "average_r_multiple", "maximum_r_multiple", "minimum_r_multiple"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite_real(value, name))
        object.__setattr__(self, "maximum_drawdown_amount", _non_negative_real(self.maximum_drawdown_amount, "maximum_drawdown_amount"))
        if not isinstance(self.trend, PerformanceTrend):
            raise TypeError("trend must be PerformanceTrend")


@dataclass(frozen=True, slots=True)
class InstrumentPerformance:
    instrument: Instrument
    statistics: TradePerformanceStatistics

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        if not isinstance(self.statistics, TradePerformanceStatistics):
            raise TypeError("statistics must be TradePerformanceStatistics")


@dataclass(frozen=True, slots=True)
class SetupPerformance:
    setup_family: StrategySetupFamily
    statistics: TradePerformanceStatistics

    def __post_init__(self) -> None:
        if not isinstance(self.setup_family, StrategySetupFamily):
            raise TypeError("setup_family must be StrategySetupFamily")
        if not isinstance(self.statistics, TradePerformanceStatistics):
            raise TypeError("statistics must be TradePerformanceStatistics")


@dataclass(frozen=True, slots=True)
class ConfidenceBucketPerformance:
    bucket_label: str
    minimum_confidence: float
    maximum_confidence: float
    statistics: TradePerformanceStatistics

    def __post_init__(self) -> None:
        _non_empty(self.bucket_label, "bucket_label")
        object.__setattr__(self, "minimum_confidence", _bounded(self.minimum_confidence, "minimum_confidence"))
        object.__setattr__(self, "maximum_confidence", _bounded(self.maximum_confidence, "maximum_confidence"))
        if self.maximum_confidence < self.minimum_confidence:
            raise ValueError("maximum_confidence cannot be below minimum_confidence")
        if not isinstance(self.statistics, TradePerformanceStatistics):
            raise TypeError("statistics must be TradePerformanceStatistics")


@dataclass(frozen=True, slots=True)
class TradePerformanceAnalyticsSnapshot:
    timestamp: datetime
    overall: TradePerformanceStatistics
    by_instrument: tuple[InstrumentPerformance, ...]
    by_setup: tuple[SetupPerformance, ...]
    by_confidence: tuple[ConfidenceBucketPerformance, ...]
    equity_curve: tuple[EquityCurvePoint, ...]
    best_instrument: Instrument | None
    worst_instrument: Instrument | None
    best_setup: StrategySetupFamily | None
    worst_setup: StrategySetupFamily | None
    last_trade: TradeJournalEntry | None

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.overall, TradePerformanceStatistics):
            raise TypeError("overall must be TradePerformanceStatistics")
        object.__setattr__(self, "by_instrument", _tuple_of(self.by_instrument, InstrumentPerformance, "by_instrument"))
        object.__setattr__(self, "by_setup", _tuple_of(self.by_setup, SetupPerformance, "by_setup"))
        object.__setattr__(self, "by_confidence", _tuple_of(self.by_confidence, ConfidenceBucketPerformance, "by_confidence"))
        object.__setattr__(self, "equity_curve", _tuple_of(self.equity_curve, EquityCurvePoint, "equity_curve"))
        if self.best_instrument is not None and self.best_instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("best_instrument must be supported or None")
        if self.worst_instrument is not None and self.worst_instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("worst_instrument must be supported or None")
        if self.best_setup is not None and not isinstance(self.best_setup, StrategySetupFamily):
            raise TypeError("best_setup must be StrategySetupFamily or None")
        if self.worst_setup is not None and not isinstance(self.worst_setup, StrategySetupFamily):
            raise TypeError("worst_setup must be StrategySetupFamily or None")
        if self.last_trade is not None and not isinstance(self.last_trade, TradeJournalEntry):
            raise TypeError("last_trade must be TradeJournalEntry or None")


@dataclass(frozen=True, slots=True)
class TradeJournalV1Snapshot:
    timestamp: datetime
    status: TradeJournalStatus
    change: JournalChange
    trade_count: int
    duplicate_count: int
    rejected_count: int
    latest_entry: TradeJournalEntry | None
    analytics: TradePerformanceAnalyticsSnapshot
    running: bool
    ready: bool
    last_error: str | None

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.status, TradeJournalStatus):
            raise TypeError("status must be TradeJournalStatus")
        if not isinstance(self.change, JournalChange):
            raise TypeError("change must be JournalChange")
        for name in ("trade_count", "duplicate_count", "rejected_count"):
            _non_negative_int(getattr(self, name), name)
        if self.latest_entry is not None and not isinstance(self.latest_entry, TradeJournalEntry):
            raise TypeError("latest_entry must be TradeJournalEntry or None")
        if not isinstance(self.analytics, TradePerformanceAnalyticsSnapshot):
            raise TypeError("analytics must be TradePerformanceAnalyticsSnapshot")
        if type(self.running) is not bool or type(self.ready) is not bool:
            raise TypeError("running and ready must be bool")
        if self.running and self.status is not TradeJournalStatus.RUNNING:
            raise ValueError("running=True requires RUNNING status")
        if self.last_error is not None:
            _non_empty(self.last_error, "last_error")


_ENTRY_ENUMS = {
    "direction": StrategyDirection,
    "setup_family": StrategySetupFamily,
    "setup_quality": StrategyDecisionQuality,
    "outcome": TradeOutcome,
    "exit_reason": PositionExitReason,
    "close_category": TradeCloseCategory,
    "risk_decision": RiskDecision,
    "execution_side": ExecutionSide,
}


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _finite_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _positive_real(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number <= 0.0:
        raise ValueError(f"{name} must be positive")
    return number


def _non_negative_real(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _bounded(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return number


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")


def _non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty string")
    return value.strip()


def _tuple_of(values, item_type, name: str):
    items = tuple(values)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain {item_type.__name__}")
    return items
