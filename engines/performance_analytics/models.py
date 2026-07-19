"""
Immutable performance analytics models for completed paper trades.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from math import isfinite
from numbers import Real
from pathlib import Path

from engines.paper_trading.models import PaperTradeRecord
from engines.performance_analytics.enums import AnalyticsGroupType, AnalyticsPeriod, AnalyticsRecordStatus, ReviewClassification


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    record_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate: float | None = None
    loss_rate: float | None = None
    breakeven_rate: float | None = None
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    total_fees: float = 0.0
    average_trade: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    largest_win: float | None = None
    largest_loss: float | None = None
    profit_factor: float | None = None
    expectancy: float | None = None
    expectancy_r: float | None = None
    average_r: float | None = None
    median_r: float | None = None
    best_r: float | None = None
    worst_r: float | None = None
    payoff_ratio: float | None = None
    maximum_drawdown: float = 0.0
    maximum_drawdown_percentage: float = 0.0
    current_drawdown: float = 0.0
    current_drawdown_percentage: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    maximum_consecutive_wins: int = 0
    maximum_consecutive_losses: int = 0
    average_holding_seconds: float | None = None
    average_mfe: float | None = None
    average_mae: float | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("record_count", "winning_trades", "losing_trades", "breakeven_trades", "consecutive_wins", "consecutive_losses", "maximum_consecutive_wins", "maximum_consecutive_losses"):
            _non_negative_int(getattr(self, name), name)
        if self.winning_trades + self.losing_trades + self.breakeven_trades != self.record_count:
            raise ValueError("win/loss/breakeven counts must equal record_count")
        for name in ("start_time", "end_time"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
        for name in _SUMMARY_FLOAT_FIELDS:
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite_real(value, name))


@dataclass(frozen=True, slots=True)
class EquityCurvePoint:
    sequence: int
    trade_id: str
    instrument: str
    timestamp: datetime
    trade_pnl: float
    cumulative_pnl: float
    running_peak: float
    drawdown: float
    drawdown_percentage: float

    def __post_init__(self) -> None:
        _positive_int(self.sequence, "sequence")
        _text(self.trade_id, "trade_id")
        object.__setattr__(self, "instrument", _text(self.instrument, "instrument").upper())
        _aware(self.timestamp, "timestamp")
        for name in ("trade_pnl", "cumulative_pnl", "running_peak", "drawdown", "drawdown_percentage"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class PeriodPerformance:
    period: AnalyticsPeriod
    label: str
    period_start: date
    period_end: date
    summary: PerformanceSummary

    def __post_init__(self) -> None:
        if not isinstance(self.period, AnalyticsPeriod):
            raise TypeError("period must be AnalyticsPeriod")
        _text(self.label, "label")
        if not isinstance(self.period_start, date) or isinstance(self.period_start, datetime):
            raise TypeError("period_start must be date")
        if not isinstance(self.period_end, date) or isinstance(self.period_end, datetime):
            raise TypeError("period_end must be date")
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot be before period_start")
        if not isinstance(self.summary, PerformanceSummary):
            raise TypeError("summary must be PerformanceSummary")


@dataclass(frozen=True, slots=True)
class GroupPerformance:
    group_type: AnalyticsGroupType
    group_key: str
    summary: PerformanceSummary

    def __post_init__(self) -> None:
        if not isinstance(self.group_type, AnalyticsGroupType):
            raise TypeError("group_type must be AnalyticsGroupType")
        object.__setattr__(self, "group_key", _text(self.group_key, "group_key"))
        if not isinstance(self.summary, PerformanceSummary):
            raise TypeError("summary must be PerformanceSummary")


@dataclass(frozen=True, slots=True)
class AnalyticsDiagnostics:
    enabled: bool = True
    loaded_records: int = 0
    accepted_records: int = 0
    duplicate_records_ignored: int = 0
    conflicting_records: int = 0
    persistence_writes: int = 0
    persistence_failures: int = 0
    load_failures: int = 0
    csv_exports: int = 0
    excel_exports: int = 0
    export_failures: int = 0
    analytics_recalculations: int = 0
    last_event: str = "-"
    last_error: str | None = None
    broker_order_calls: int = 0

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be bool")
        for name in ("loaded_records", "accepted_records", "duplicate_records_ignored", "conflicting_records", "persistence_writes", "persistence_failures", "load_failures", "csv_exports", "excel_exports", "export_failures", "analytics_recalculations", "broker_order_calls"):
            _non_negative_int(getattr(self, name), name)
        if self.broker_order_calls != 0:
            raise ValueError("performance analytics must not call broker orders")
        _text(self.last_event, "last_event")
        if self.last_error is not None:
            _text(self.last_error, "last_error")


@dataclass(frozen=True, slots=True)
class AnalyticsFilters:
    instrument: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        if self.instrument is not None:
            object.__setattr__(self, "instrument", _text(self.instrument, "instrument").upper())
        for name in ("start_date", "end_date"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, date) or isinstance(value, datetime)):
                raise TypeError(f"{name} must be date or None")
        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")


@dataclass(frozen=True, slots=True)
class AnalyticsSnapshot:
    overall: PerformanceSummary
    selected_instrument: PerformanceSummary
    equity_curve: tuple[EquityCurvePoint, ...]
    daily_performance: tuple[PeriodPerformance, ...]
    weekly_performance: tuple[PeriodPerformance, ...]
    monthly_performance: tuple[PeriodPerformance, ...]
    instrument_statistics: tuple[GroupPerformance, ...]
    direction_statistics: tuple[GroupPerformance, ...]
    setup_statistics: tuple[GroupPerformance, ...]
    entry_type_statistics: tuple[GroupPerformance, ...] = ()
    exit_type_statistics: tuple[GroupPerformance, ...] = ()
    time_of_day_statistics: tuple[GroupPerformance, ...] = ()
    camarilla_statistics: tuple[GroupPerformance, ...] = ()
    cpr_statistics: tuple[GroupPerformance, ...] = ()
    ai_confidence_statistics: tuple[GroupPerformance, ...] = ()
    latest_records: tuple[PaperTradeRecord, ...] = ()
    filters_applied: AnalyticsFilters = field(default_factory=AnalyticsFilters)
    generated_at: datetime | None = None
    diagnostics: AnalyticsDiagnostics = field(default_factory=AnalyticsDiagnostics)

    def __post_init__(self) -> None:
        if not isinstance(self.overall, PerformanceSummary) or not isinstance(self.selected_instrument, PerformanceSummary):
            raise TypeError("summary fields must be PerformanceSummary")
        object.__setattr__(self, "equity_curve", _tuple_of(self.equity_curve, EquityCurvePoint, "equity_curve"))
        for name in ("daily_performance", "weekly_performance", "monthly_performance"):
            object.__setattr__(self, name, _tuple_of(getattr(self, name), PeriodPerformance, name))
        for name in ("instrument_statistics", "direction_statistics", "setup_statistics", "entry_type_statistics", "exit_type_statistics", "time_of_day_statistics", "camarilla_statistics", "cpr_statistics", "ai_confidence_statistics"):
            object.__setattr__(self, name, _tuple_of(getattr(self, name), GroupPerformance, name))
        object.__setattr__(self, "latest_records", _tuple_of(self.latest_records, PaperTradeRecord, "latest_records"))
        if not isinstance(self.filters_applied, AnalyticsFilters):
            raise TypeError("filters_applied must be AnalyticsFilters")
        if self.generated_at is not None:
            _aware(self.generated_at, "generated_at")
        if not isinstance(self.diagnostics, AnalyticsDiagnostics):
            raise TypeError("diagnostics must be AnalyticsDiagnostics")


@dataclass(frozen=True, slots=True)
class JournalRecordResult:
    status: AnalyticsRecordStatus
    record: PaperTradeRecord | None
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, AnalyticsRecordStatus):
            raise TypeError("status must be AnalyticsRecordStatus")
        if self.record is not None and not isinstance(self.record, PaperTradeRecord):
            raise TypeError("record must be PaperTradeRecord or None")
        _text(self.message, "message")


@dataclass(frozen=True, slots=True)
class ExportResult:
    path: Path
    record_count: int
    exported_at: datetime
    format: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        _non_negative_int(self.record_count, "record_count")
        _aware(self.exported_at, "exported_at")
        _text(self.format, "format")


@dataclass(frozen=True, slots=True)
class PostTradeReview:
    trade_id: str
    classification: ReviewClassification
    planned_r: float
    realized_r: float | None
    execution_efficiency: float | None
    mfe_capture_ratio: float | None
    mae_relative_to_planned_risk: float | None
    exit_assessment: str
    setup_assessment: str
    process_observations: tuple[str, ...]
    positive_observations: tuple[str, ...]
    improvement_observations: tuple[str, ...]
    review_tags: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.trade_id, "trade_id")
        if not isinstance(self.classification, ReviewClassification):
            raise TypeError("classification must be ReviewClassification")
        object.__setattr__(self, "planned_r", _finite_real(self.planned_r, "planned_r"))
        for name in ("realized_r", "execution_efficiency", "mfe_capture_ratio", "mae_relative_to_planned_risk"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite_real(value, name))
        for name in ("exit_assessment", "setup_assessment"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("process_observations", "positive_observations", "improvement_observations", "review_tags"):
            object.__setattr__(self, name, tuple(str(item).strip() for item in getattr(self, name) if str(item).strip()))


@dataclass(frozen=True, slots=True)
class TradeReplayMetadata:
    trade_id: str
    plan_id: str
    instrument: str
    timeframe: str | None
    trading_date: date
    entry_time: datetime
    exit_time: datetime
    direction: str
    entry_price: float
    stop_price: float
    target_price: float
    exit_price: float
    entry_type: str
    strategy_setup: str
    strategy_reasoning: tuple[str, ...]
    ai_reasoning: str | None
    market_context_labels: tuple[str, ...]
    option_chain_labels: tuple[str, ...]
    cpr_labels: tuple[str, ...]
    camarilla_labels: tuple[str, ...]
    vwap_labels: tuple[str, ...]
    source_strategy_id: str
    source_plan_identity: str
    market_data_reference: str | None = None

    def __post_init__(self) -> None:
        for name in ("trade_id", "plan_id", "instrument", "direction", "entry_type", "strategy_setup", "source_strategy_id", "source_plan_identity"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.timeframe is not None:
            object.__setattr__(self, "timeframe", _text(self.timeframe, "timeframe"))
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date")
        _aware(self.entry_time, "entry_time")
        _aware(self.exit_time, "exit_time")
        for name in ("entry_price", "stop_price", "target_price", "exit_price"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))
        for name in ("strategy_reasoning", "market_context_labels", "option_chain_labels", "cpr_labels", "camarilla_labels", "vwap_labels"):
            object.__setattr__(self, name, tuple(str(item).strip() for item in getattr(self, name) if str(item).strip()))


_SUMMARY_FLOAT_FIELDS = (
    "win_rate", "loss_rate", "breakeven_rate", "gross_profit", "gross_loss", "net_profit", "total_fees",
    "average_trade", "average_win", "average_loss", "largest_win", "largest_loss", "profit_factor", "expectancy",
    "expectancy_r", "average_r", "median_r", "best_r", "worst_r", "payoff_ratio", "maximum_drawdown",
    "maximum_drawdown_percentage", "current_drawdown", "current_drawdown_percentage", "average_holding_seconds",
    "average_mfe", "average_mae",
)


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


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")


def _text(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _tuple_of(values, item_type, name: str):
    items = tuple(values)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain {item_type.__name__}")
    return items

