"""
Immutable dashboard presentation models.
"""

from dataclasses import dataclass
from datetime import datetime


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
