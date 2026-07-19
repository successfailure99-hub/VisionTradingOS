"""
Immutable Paper Trading & Position Lifecycle V1 models.
"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from engines.paper_trading.enums import PaperExitType, PaperOrderState, PaperPositionState
from engines.strategy.enums import TradeDirection


@dataclass(frozen=True, slots=True)
class PaperOrder:
    paper_order_id: str
    plan_id: str
    instrument: str
    created_at: datetime
    updated_at: datetime
    direction: TradeDirection
    entry_type: str
    entry_price: float
    stop_price: float
    target_price: float
    quantity: int
    lot_size: int
    approved_lots: int
    state: PaperOrderState
    valid_until: datetime
    triggered_at: datetime | None = None
    trigger_price: float | None = None
    cancelled_at: datetime | None = None
    expired_at: datetime | None = None
    rejection_reason: str | None = None
    source_plan_identity: str = "-"

    def __post_init__(self) -> None:
        _text(self.paper_order_id, "paper_order_id")
        _text(self.plan_id, "plan_id")
        object.__setattr__(self, "instrument", _text(self.instrument, "instrument").upper())
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")
        _aware(self.valid_until, "valid_until")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")
        if self.valid_until <= self.created_at:
            raise ValueError("valid_until must be after created_at")
        if not isinstance(self.direction, TradeDirection) or self.direction is TradeDirection.NONE:
            raise ValueError("direction must be bullish or bearish")
        for name in ("entry_price", "stop_price", "target_price"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        _validate_geometry(self.direction, self.entry_price, self.stop_price, self.target_price)
        object.__setattr__(self, "quantity", _positive_int(self.quantity, "quantity"))
        object.__setattr__(self, "lot_size", _positive_int(self.lot_size, "lot_size"))
        object.__setattr__(self, "approved_lots", _positive_int(self.approved_lots, "approved_lots"))
        if self.quantity != self.lot_size * self.approved_lots:
            raise ValueError("quantity must equal lot_size * approved_lots")
        if not isinstance(self.state, PaperOrderState):
            raise TypeError("state must be PaperOrderState")
        if self.state is PaperOrderState.TRIGGERED:
            _aware(self.triggered_at, "triggered_at")
            _positive_real(self.trigger_price, "trigger_price")
        if self.state is PaperOrderState.CANCELLED:
            _aware(self.cancelled_at, "cancelled_at")
            _text(self.rejection_reason, "rejection_reason")
        if self.state is PaperOrderState.EXPIRED:
            _aware(self.expired_at, "expired_at")


@dataclass(frozen=True, slots=True)
class PaperPosition:
    position_id: str
    paper_order_id: str
    plan_id: str
    instrument: str
    direction: TradeDirection
    quantity: int
    lot_size: int
    opened_at: datetime
    entry_price: float
    last_price: float
    stop_price: float
    target_price: float
    unrealized_pnl: float
    maximum_favourable_excursion: float
    maximum_adverse_excursion: float
    state: PaperPositionState
    closed_at: datetime | None = None
    exit_price: float | None = None
    exit_type: PaperExitType | None = None
    realized_pnl: float | None = None
    holding_seconds: int | None = None

    def __post_init__(self) -> None:
        _text(self.position_id, "position_id")
        _text(self.paper_order_id, "paper_order_id")
        _text(self.plan_id, "plan_id")
        object.__setattr__(self, "instrument", _text(self.instrument, "instrument").upper())
        if not isinstance(self.direction, TradeDirection) or self.direction is TradeDirection.NONE:
            raise ValueError("direction must be bullish or bearish")
        object.__setattr__(self, "quantity", _positive_int(self.quantity, "quantity"))
        object.__setattr__(self, "lot_size", _positive_int(self.lot_size, "lot_size"))
        _aware(self.opened_at, "opened_at")
        for name in ("entry_price", "last_price", "stop_price", "target_price"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        _validate_geometry(self.direction, self.entry_price, self.stop_price, self.target_price)
        object.__setattr__(self, "unrealized_pnl", _finite_real(self.unrealized_pnl, "unrealized_pnl"))
        object.__setattr__(self, "maximum_favourable_excursion", _non_negative_real(self.maximum_favourable_excursion, "maximum_favourable_excursion"))
        object.__setattr__(self, "maximum_adverse_excursion", _non_negative_real(self.maximum_adverse_excursion, "maximum_adverse_excursion"))
        if not isinstance(self.state, PaperPositionState):
            raise TypeError("state must be PaperPositionState")
        if self.state is PaperPositionState.OPEN:
            if self.closed_at is not None or self.exit_price is not None or self.exit_type is not None or self.realized_pnl is not None or self.holding_seconds is not None:
                raise ValueError("open position cannot contain final exit fields")
        else:
            _aware(self.closed_at, "closed_at")
            if self.closed_at < self.opened_at:
                raise ValueError("closed_at cannot be before opened_at")
            object.__setattr__(self, "exit_price", _positive_real(self.exit_price, "exit_price"))
            if not isinstance(self.exit_type, PaperExitType):
                raise TypeError("exit_type must be PaperExitType")
            object.__setattr__(self, "realized_pnl", _finite_real(self.realized_pnl, "realized_pnl"))
            if isinstance(self.holding_seconds, bool) or not isinstance(self.holding_seconds, int) or self.holding_seconds < 0:
                raise ValueError("holding_seconds must be non-negative integer")


@dataclass(frozen=True, slots=True)
class PaperTradeRecord:
    trade_id: str
    position_id: str
    paper_order_id: str
    plan_id: str
    instrument: str
    direction: TradeDirection
    quantity: int
    lot_size: int
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    stop_price: float
    target_price: float
    exit_type: PaperExitType
    gross_pnl: float
    fees: float
    net_pnl: float
    reward_risk_planned: float
    reward_risk_realized: float | None
    maximum_favourable_excursion: float
    maximum_adverse_excursion: float
    holding_seconds: int
    strategy_setup: str
    strategy_confidence: str
    strategy_reasoning: tuple[str, ...]
    trading_date: date

    def __post_init__(self) -> None:
        for name in ("trade_id", "position_id", "paper_order_id", "plan_id"):
            _text(getattr(self, name), name)
        object.__setattr__(self, "instrument", _text(self.instrument, "instrument").upper())
        if not isinstance(self.direction, TradeDirection) or self.direction is TradeDirection.NONE:
            raise ValueError("direction must be bullish or bearish")
        object.__setattr__(self, "quantity", _positive_int(self.quantity, "quantity"))
        object.__setattr__(self, "lot_size", _positive_int(self.lot_size, "lot_size"))
        _aware(self.entry_time, "entry_time")
        _aware(self.exit_time, "exit_time")
        if self.exit_time < self.entry_time:
            raise ValueError("exit_time cannot be before entry_time")
        for name in ("entry_price", "exit_price", "stop_price", "target_price", "reward_risk_planned"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        if not isinstance(self.exit_type, PaperExitType):
            raise TypeError("exit_type must be PaperExitType")
        for name in ("gross_pnl", "fees", "net_pnl", "maximum_favourable_excursion", "maximum_adverse_excursion"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))
        if self.reward_risk_realized is not None:
            object.__setattr__(self, "reward_risk_realized", _finite_real(self.reward_risk_realized, "reward_risk_realized"))
        if isinstance(self.holding_seconds, bool) or not isinstance(self.holding_seconds, int) or self.holding_seconds < 0:
            raise ValueError("holding_seconds must be non-negative integer")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date")
        object.__setattr__(self, "strategy_reasoning", tuple(str(item).strip() for item in self.strategy_reasoning if str(item).strip()))


@dataclass(frozen=True, slots=True)
class PaperJournalSummary:
    record_count: int = 0
    latest_record: PaperTradeRecord | None = None
    daily_realized_pnl: float = 0.0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    profit_factor: float | None = None


@dataclass(frozen=True, slots=True)
class PaperTradingDiagnostics:
    paper_trading_enabled: bool
    safe_mode_confirmed: bool
    plans_received: int = 0
    orders_created: int = 0
    orders_triggered: int = 0
    orders_cancelled: int = 0
    orders_expired: int = 0
    positions_opened: int = 0
    positions_closed: int = 0
    journal_records: int = 0
    last_event: str = "-"
    last_error: str | None = None
    broker_order_calls: int = 0


@dataclass(frozen=True, slots=True)
class PaperTradingSnapshot:
    enabled: bool
    safe_mode_confirmed: bool
    order: PaperOrder | None
    position: PaperPosition | None
    journal_summary: PaperJournalSummary
    latest_record: PaperTradeRecord | None
    last_event: str
    last_error: str | None
    diagnostics: PaperTradingDiagnostics


def _text(value: str | None, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime | None, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _finite_real(value: Real | None, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _positive_real(value: Real | None, name: str) -> float:
    number = _finite_real(value, name)
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def _non_negative_real(value: Real | None, name: str) -> float:
    number = _finite_real(value, name)
    if number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")
    return value


def _validate_geometry(direction: TradeDirection, entry: float, stop: float, target: float) -> None:
    if direction is TradeDirection.BULLISH and not (stop < entry < target):
        raise ValueError("bullish geometry requires stop < entry < target")
    if direction is TradeDirection.BEARISH and not (target < entry < stop):
        raise ValueError("bearish geometry requires target < entry < stop")

