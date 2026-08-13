"""
Immutable Trade Journal & Performance Analytics V1 models.
"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from application.execution_runtime_v1.enums import ExecutionSide
from application.trade_lifecycle_v1.models import TradeLifecycleV1Snapshot
from core.enums.instrument import Instrument
from engines.option_paper_execution.models import OptionPaperPositionSnapshot
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
    PaperRecoveryStatus,
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
    trade_source: str = "STRATEGY_DECISION_V2"
    trade_candidate_reference: str | None = None
    vision_method_snapshot_reference: str | None = None
    vision_method_validation_reference: str | None = None
    record_state: str = "closed"
    instrument_type: str = "UNDERLYING"
    execution_style: str = "STRATEGY_DECISION_V2"
    option_candidate_reference: str | None = None
    option_position_reference: str | None = None
    contract_trading_symbol: str | None = None
    instrument_token: int | None = None
    expiry: date | None = None
    strike: float | None = None
    option_type: str | None = None
    transaction_type: str | None = None
    moneyness: str | None = None
    itm_steps: int | None = None
    lots: int | None = None
    lot_size: int | None = None

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
        object.__setattr__(self, "record_state", _one_of(self.record_state, "record_state", {"open", "closed"}))
        if isinstance(self.lifecycle_snapshot, TradeLifecycleV1Snapshot):
            if self.lifecycle_snapshot.instrument is not self.instrument:
                raise ValueError("lifecycle snapshot instrument mismatch")
            position = self.lifecycle_snapshot.position_result.position if self.lifecycle_snapshot.position_result else None
            if position is None or position.open_quantity != 0 or position.closed_at is None:
                raise ValueError("lifecycle snapshot must contain a closed position")
            if position.dry_run is not True or position.analysis_only is not True:
                raise ValueError("journal entries must remain dry-run and analysis-only")
            if self.record_state != "closed":
                raise ValueError("standard lifecycle journal entries must be closed")
        elif isinstance(self.lifecycle_snapshot, OptionPaperPositionSnapshot):
            option_position = self.lifecycle_snapshot
            if self.option_position_reference is not None and self.option_position_reference != option_position.position_id:
                raise ValueError("option position reference mismatch")
            if self.record_state == "closed" and option_position.closed_at is None:
                raise ValueError("closed option journal entry requires a closed option paper position")
        else:
            raise TypeError("lifecycle_snapshot must be TradeLifecycleV1Snapshot or OptionPaperPositionSnapshot")
        object.__setattr__(self, "trade_source", _non_empty(self.trade_source, "trade_source"))
        object.__setattr__(self, "instrument_type", _non_empty(self.instrument_type, "instrument_type"))
        object.__setattr__(self, "execution_style", _non_empty(self.execution_style, "execution_style"))
        for name in (
            "trade_candidate_reference",
            "vision_method_snapshot_reference",
            "vision_method_validation_reference",
            "option_candidate_reference",
            "option_position_reference",
            "contract_trading_symbol",
            "option_type",
            "transaction_type",
            "moneyness",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _non_empty(value, name))
        if self.instrument_token is not None:
            _positive_int(self.instrument_token, "instrument_token")
        if self.expiry is not None and (not isinstance(self.expiry, date) or isinstance(self.expiry, datetime)):
            raise TypeError("expiry must be date or None")
        if self.strike is not None:
            object.__setattr__(self, "strike", _positive_real(self.strike, "strike"))
        for name in ("itm_steps", "lots", "lot_size"):
            value = getattr(self, name)
            if value is not None:
                _non_negative_int(value, name)

@dataclass(frozen=True, slots=True)
class VisionTradeJournalRecord:
    trade_id: str
    instrument: Instrument
    exchange: str
    timeframe: str
    trading_date: date
    trade_source: str
    setup_classification: str
    candidate_direction: str
    candidate_quality: str
    validation_result: str
    outcome: TradeOutcome
    exit_reason: PositionExitReason
    vision_method_snapshot_reference: str
    vision_method_validation_reference: str
    trade_candidate_reference: str
    risk_reference: str
    lifecycle_reference: str
    paper_position_reference: str
    validation_trace_reference: str
    entry_timestamp: datetime
    entry_price: float
    quantity: int
    stop_price: float
    target_price: float | None
    exit_timestamp: datetime
    exit_price: float
    gross_pnl: float
    fees: float
    slippage: float
    net_pnl: float
    supporting_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    record_version: int = 1
    record_state: str = "closed"
    instrument_type: str = "UNDERLYING"
    execution_style: str = "STRATEGY_DECISION_V2"
    option_candidate_reference: str | None = None
    option_position_reference: str | None = None
    contract_trading_symbol: str | None = None
    instrument_token: int | None = None
    expiry: date | None = None
    strike: float | None = None
    option_type: str | None = None
    transaction_type: str | None = None
    moneyness: str | None = None
    itm_steps: int | None = None
    lots: int | None = None
    lot_size: int | None = None

    def __post_init__(self) -> None:
        _non_empty(self.trade_id, "trade_id")
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        for name in (
            "exchange",
            "timeframe",
            "trade_source",
            "setup_classification",
            "candidate_direction",
            "candidate_quality",
            "validation_result",
            "vision_method_snapshot_reference",
            "vision_method_validation_reference",
            "trade_candidate_reference",
            "risk_reference",
            "lifecycle_reference",
            "paper_position_reference",
            "validation_trace_reference",
        ):
            object.__setattr__(self, name, _non_empty(getattr(self, name), name))
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date")
        if not isinstance(self.outcome, TradeOutcome):
            raise TypeError("outcome must be TradeOutcome")
        if not isinstance(self.exit_reason, PositionExitReason):
            raise TypeError("exit_reason must be PositionExitReason")
        for name in ("entry_timestamp", "exit_timestamp", "created_at", "updated_at"):
            _aware(getattr(self, name), name)
        if self.exit_timestamp < self.entry_timestamp:
            raise ValueError("exit_timestamp cannot precede entry_timestamp")
        for name in ("entry_price", "stop_price", "exit_price"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        if self.target_price is not None:
            object.__setattr__(self, "target_price", _positive_real(self.target_price, "target_price"))
        _positive_int(self.quantity, "quantity")
        for name in ("gross_pnl", "fees", "slippage", "net_pnl"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))
        object.__setattr__(self, "supporting_reasons", _strings(self.supporting_reasons, "supporting_reasons"))
        object.__setattr__(self, "blocking_reasons", _strings(self.blocking_reasons, "blocking_reasons"))
        _positive_int(self.record_version, "record_version")
        object.__setattr__(self, "record_state", _one_of(self.record_state, "record_state", {"open", "closed"}))
        object.__setattr__(self, "instrument_type", _non_empty(self.instrument_type, "instrument_type"))
        object.__setattr__(self, "execution_style", _non_empty(self.execution_style, "execution_style"))
        for name in (
            "option_candidate_reference",
            "option_position_reference",
            "contract_trading_symbol",
            "option_type",
            "transaction_type",
            "moneyness",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _non_empty(value, name))
        if self.instrument_token is not None:
            _positive_int(self.instrument_token, "instrument_token")
        if self.expiry is not None and (not isinstance(self.expiry, date) or isinstance(self.expiry, datetime)):
            raise TypeError("expiry must be date or None")
        if self.strike is not None:
            object.__setattr__(self, "strike", _positive_real(self.strike, "strike"))
        for name in ("itm_steps", "lots", "lot_size"):
            value = getattr(self, name)
            if value is not None:
                _non_negative_int(value, name)


@dataclass(frozen=True, slots=True)
class ActivePaperPositionCheckpoint:
    trade_id: str
    instrument: Instrument
    exchange: str
    timeframe: str
    trading_date: date
    candidate_identity: str
    candidate_state: str
    direction: str
    entry_timestamp: datetime
    entry_price: float
    quantity: int
    stop_price: float
    target_price: float | None
    last_market_timestamp: datetime
    lifecycle_state: str
    position_state: str
    unrealized_pnl: float
    vision_method_snapshot_reference: str
    vision_method_validation_reference: str
    trade_candidate_reference: str
    risk_reference: str
    created_at: datetime
    updated_at: datetime
    checkpoint_version: int = 1
    instrument_type: str = "UNDERLYING"
    execution_style: str = "STRATEGY_DECISION_V2"
    runtime_session_id: str | None = None
    option_candidate_reference: str | None = None
    option_position_reference: str | None = None
    contract_trading_symbol: str | None = None
    instrument_token: int | None = None
    expiry: date | None = None
    strike: float | None = None
    option_type: str | None = None
    transaction_type: str | None = None
    moneyness: str | None = None
    itm_steps: int | None = None
    lots: int | None = None
    lot_size: int | None = None
    underlying_spot: float | None = None
    premium_reference: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    open_interest: int | None = None
    volume: int | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    underlying_invalidation: str | None = None
    underlying_target_context: str | None = None
    selection_score: float | None = None
    selection_policy: str | None = None
    selection_reasoning: tuple[str, ...] = ()
    option_candidate_status: str | None = None
    risk_decision: str | None = None
    requested_lots: int | None = None
    approved_lots: int | None = None
    approved_quantity: int | None = None
    risk_per_unit: float | None = None
    reward_per_unit: float | None = None
    planned_rupee_risk: float | None = None
    planned_rupee_reward: float | None = None
    paper_capital: float | None = None
    margin_available: float | None = None
    option_risk_reason: str | None = None
    option_risk_warnings: tuple[str, ...] = ()
    current_premium: float | None = None
    exit_premium: float | None = None
    closed_at: datetime | None = None
    realized_pnl: float | None = None
    total_pnl: float | None = None
    exit_reason: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.trade_id, "trade_id")
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        for name in (
            "exchange",
            "timeframe",
            "candidate_identity",
            "candidate_state",
            "direction",
            "lifecycle_state",
            "position_state",
            "vision_method_snapshot_reference",
            "vision_method_validation_reference",
            "trade_candidate_reference",
            "risk_reference",
        ):
            object.__setattr__(self, name, _non_empty(getattr(self, name), name))
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date")
        for name in ("entry_timestamp", "last_market_timestamp", "created_at", "updated_at"):
            _aware(getattr(self, name), name)
        if self.last_market_timestamp < self.entry_timestamp:
            raise ValueError("last_market_timestamp cannot precede entry_timestamp")
        object.__setattr__(self, "entry_price", _positive_real(self.entry_price, "entry_price"))
        object.__setattr__(self, "stop_price", _positive_real(self.stop_price, "stop_price"))
        if self.target_price is not None:
            object.__setattr__(self, "target_price", _positive_real(self.target_price, "target_price"))
        _positive_int(self.quantity, "quantity")
        object.__setattr__(self, "unrealized_pnl", _finite_real(self.unrealized_pnl, "unrealized_pnl"))
        _positive_int(self.checkpoint_version, "checkpoint_version")
        object.__setattr__(self, "instrument_type", _non_empty(self.instrument_type, "instrument_type"))
        object.__setattr__(self, "execution_style", _non_empty(self.execution_style, "execution_style"))
        for name in (
            "runtime_session_id",
            "option_candidate_reference",
            "option_position_reference",
            "contract_trading_symbol",
            "option_type",
            "transaction_type",
            "moneyness",
            "underlying_invalidation",
            "underlying_target_context",
            "selection_policy",
            "option_candidate_status",
            "risk_decision",
            "option_risk_reason",
            "exit_reason",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _non_empty(value, name))
        if self.expiry is not None and (not isinstance(self.expiry, date) or isinstance(self.expiry, datetime)):
            raise TypeError("expiry must be date or None")
        if self.closed_at is not None:
            _aware(self.closed_at, "closed_at")
        for name in ("instrument_token", "itm_steps", "lots", "lot_size", "open_interest", "volume", "requested_lots", "approved_lots", "approved_quantity"):
            value = getattr(self, name)
            if value is not None:
                _non_negative_int(value, name)
        for name in (
            "strike",
            "underlying_spot",
            "premium_reference",
            "bid",
            "ask",
            "spread",
            "implied_volatility",
            "delta",
            "selection_score",
            "risk_per_unit",
            "reward_per_unit",
            "planned_rupee_risk",
            "planned_rupee_reward",
            "paper_capital",
            "margin_available",
            "current_premium",
            "exit_premium",
            "realized_pnl",
            "total_pnl",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite_real(value, name))
        object.__setattr__(self, "selection_reasoning", _strings(self.selection_reasoning, "selection_reasoning"))
        object.__setattr__(self, "option_risk_warnings", _strings(self.option_risk_warnings, "option_risk_warnings"))


@dataclass(frozen=True, slots=True)
class PaperRecoverySnapshot:
    status: PaperRecoveryStatus
    trade_id: str | None
    checkpoint: ActivePaperPositionCheckpoint | None
    recovered_at: datetime
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, PaperRecoveryStatus):
            raise TypeError("status must be PaperRecoveryStatus")
        if self.trade_id is not None:
            _non_empty(self.trade_id, "trade_id")
        if self.checkpoint is not None and not isinstance(self.checkpoint, ActivePaperPositionCheckpoint):
            raise TypeError("checkpoint must be ActivePaperPositionCheckpoint or None")
        _aware(self.recovered_at, "recovered_at")
        object.__setattr__(self, "reason", _non_empty(self.reason, "reason"))

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


def _one_of(value: str, name: str, allowed: set[str]) -> str:
    text = _non_empty(value, name).lower()
    if text not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}")
    return text


def _strings(values, name: str) -> tuple[str, ...]:
    items = tuple(str(item).strip() for item in tuple(values or ()) if str(item).strip())
    if len(set(items)) != len(items):
        raise ValueError(f"{name} cannot contain duplicate values")
    return items


def _tuple_of(values, item_type, name: str):
    items = tuple(values)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain {item_type.__name__}")
    return items
