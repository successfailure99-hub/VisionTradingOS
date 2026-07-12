"""
Immutable dashboard presentation models.
"""

from dataclasses import dataclass, field
from datetime import datetime


def _require_non_negative(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_aware(value: datetime | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class DashboardRuntimeView:
    application_status: str
    broker_mode: str
    safety_mode: str
    configured_instruments: tuple[str, ...]
    market_data_ready: bool
    trade_journal_ready: bool
    start_count: int
    stop_count: int
    restart_count: int
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class DashboardLiveSubscriptionView:
    instrument: str
    exchange: str
    instrument_token: int
    mode: str

    def __post_init__(self) -> None:
        _require_non_negative(self.instrument_token, "instrument_token")


@dataclass(frozen=True, slots=True)
class DashboardLiveMarketDataView:
    available: bool
    runtime_status: str
    ready: bool
    running: bool
    websocket_status: str
    connected: bool
    configured_instruments: tuple[str, ...]
    configured_tokens: tuple[int, ...]
    subscription_count: int
    subscription_rows: tuple[DashboardLiveSubscriptionView, ...]
    connection_count: int
    disconnection_count: int
    reconnect_count: int
    raw_tick_count: int
    normalized_tick_count: int
    delivered_tick_count: int
    rejected_tick_count: int
    start_count: int
    stop_count: int
    last_connected_at: datetime | None
    last_disconnected_at: datetime | None
    last_tick_at: datetime | None
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "configured_instruments", tuple(self.configured_instruments))
        object.__setattr__(self, "configured_tokens", tuple(self.configured_tokens))
        object.__setattr__(self, "subscription_rows", tuple(self.subscription_rows))
        for name in (
            "subscription_count",
            "connection_count",
            "disconnection_count",
            "reconnect_count",
            "raw_tick_count",
            "normalized_tick_count",
            "delivered_tick_count",
            "rejected_tick_count",
            "start_count",
            "stop_count",
        ):
            _require_non_negative(getattr(self, name), name)
        for name in (
            "last_connected_at",
            "last_disconnected_at",
            "last_tick_at",
            "last_started_at",
            "last_stopped_at",
        ):
            _require_aware(getattr(self, name), name)
        if self.subscription_count != len(self.subscription_rows):
            raise ValueError("subscription_count must match subscription_rows")


def unavailable_live_market_data_view() -> DashboardLiveMarketDataView:
    return DashboardLiveMarketDataView(
        available=False,
        runtime_status="Live market data not configured",
        ready=False,
        running=False,
        websocket_status="Offline",
        connected=False,
        configured_instruments=(),
        configured_tokens=(),
        subscription_count=0,
        subscription_rows=(),
        connection_count=0,
        disconnection_count=0,
        reconnect_count=0,
        raw_tick_count=0,
        normalized_tick_count=0,
        delivered_tick_count=0,
        rejected_tick_count=0,
        start_count=0,
        stop_count=0,
        last_connected_at=None,
        last_disconnected_at=None,
        last_tick_at=None,
        last_started_at=None,
        last_stopped_at=None,
        last_error=None,
    )


@dataclass(frozen=True, slots=True)
class DashboardMarketView:
    symbol: str
    timeframe: str
    runtime_status: str
    last_price: float | None
    bid_price: float | None
    ask_price: float | None
    session_high: float | None
    session_low: float | None
    latest_candle_open: float | None
    latest_candle_high: float | None
    latest_candle_low: float | None
    latest_candle_close: float | None
    vwap: float | None
    cpr_pivot: float | None
    cpr_bc: float | None
    cpr_tc: float | None
    camarilla_h3: float | None
    camarilla_h4: float | None
    camarilla_h5: float | None
    camarilla_h6: float | None
    camarilla_l3: float | None
    camarilla_l4: float | None
    camarilla_l5: float | None
    camarilla_l6: float | None
    market_bias: str
    market_phase: str
    context_strength: str
    option_chain_direction: str
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class DashboardAIView:
    symbol: str
    market_summary: str
    confidence: str
    agreement: str
    conflict: str
    trading_suitability: str
    explanation: str
    missing_information: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DashboardStrategyView:
    symbol: str
    decision: str
    direction: str
    setup_quality: str
    entry_reference: str
    stop_reference: str
    target_reference: str
    block_reason: str
    risk_decision: str
    approved_quantity: int | None
    risk_amount: float | None
    reward_risk: float | None
    latest_order_status: str


@dataclass(frozen=True, slots=True)
class DashboardPositionView:
    symbol: str
    has_position: bool
    side: str
    quantity: int | None
    average_price: float | None
    last_price: float | None
    unrealized_pnl: float | None
    realized_pnl: float | None
    stop_price: float | None
    target_price: float | None


@dataclass(frozen=True, slots=True)
class DashboardJournalView:
    symbol: str
    latest_trade_id: str | None
    latest_exit_type: str
    latest_realized_pnl: float | None
    latest_opened_at: datetime | None
    latest_closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class DashboardView:
    runtime: DashboardRuntimeView
    markets: tuple[DashboardMarketView, ...]
    ai: tuple[DashboardAIView, ...]
    strategies: tuple[DashboardStrategyView, ...]
    positions: tuple[DashboardPositionView, ...]
    journals: tuple[DashboardJournalView, ...]
    live_market_data: DashboardLiveMarketDataView = field(default_factory=unavailable_live_market_data_view)
