"""
Immutable dashboard presentation models.
"""

from dataclasses import dataclass, field
from datetime import date, datetime


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
class DashboardMarketSessionView:
    market_status: str
    current_time: str
    session: str
    websocket: str
    live_ticks: str
    last_tick: str
    next_open: str


def default_market_session_view() -> DashboardMarketSessionView:
    return DashboardMarketSessionView(
        market_status="-",
        current_time="-",
        session="Closed",
        websocket="Offline",
        live_ticks="Offline",
        last_tick="-",
        next_open="-",
    )


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
    market_session: DashboardMarketSessionView = field(default_factory=default_market_session_view)

    def __post_init__(self) -> None:
        if not isinstance(self.market_session, DashboardMarketSessionView):
            raise TypeError("market_session must be DashboardMarketSessionView")
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
        market_session=DashboardMarketSessionView(
            market_status="Live market data not configured",
            current_time="-",
            session="Closed",
            websocket="Offline",
            live_ticks="Offline",
            last_tick="-",
            next_open="-",
        ),
    )


@dataclass(frozen=True, slots=True)
class DashboardOptionChainStrikeView:
    strike_price: float
    is_atm: bool
    call_last_price: float | None
    call_open_interest: int | None
    call_change_open_interest: int | None
    call_volume: int | None
    call_bid_price: float | None
    call_ask_price: float | None
    put_last_price: float | None
    put_open_interest: int | None
    put_change_open_interest: int | None
    put_volume: int | None
    put_bid_price: float | None
    put_ask_price: float | None

    def __post_init__(self) -> None:
        if isinstance(self.is_atm, bool) is False:
            raise TypeError("is_atm must be a bool")
        for name in ("call_open_interest", "call_volume", "put_open_interest", "put_volume"):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative(value, name)


@dataclass(frozen=True, slots=True)
class DashboardOptionChainRuntimeRowView:
    instrument: str
    state: str
    expiry: date | None
    contracts: int
    option_ticks: int
    last_update: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        _require_non_negative(self.contracts, "contracts")
        _require_non_negative(self.option_ticks, "option_ticks")
        _require_aware(self.last_update, "last_update")


@dataclass(frozen=True, slots=True)
class DashboardOptionChainEventView:
    timestamp: str
    instrument: str
    state: str
    message: str


@dataclass(frozen=True, slots=True)
class DashboardOptionChainView:
    symbol: str
    available: bool
    exchange: str
    expiry_date: date | None
    timestamp: datetime | None
    underlying_price: float | None
    atm_strike: float | None
    strike_count: int
    total_call_oi: int
    total_put_oi: int
    total_call_change_oi: int
    total_put_change_oi: int
    oi_pcr: float | None
    change_oi_pcr: float | None
    max_call_oi_strike: float | None
    max_call_oi_value: int | None
    max_put_oi_strike: float | None
    max_put_oi_value: int | None
    max_call_change_oi_strike: float | None
    max_call_change_oi_value: int | None
    max_put_change_oi_strike: float | None
    max_put_change_oi_value: int | None
    resistance_strike: float | None
    support_strike: float | None
    max_pain_strike: float | None
    call_pressure: str
    put_pressure: str
    positioning_bias: str
    strikes: tuple[DashboardOptionChainStrikeView, ...]
    runtime_status: str = "Disabled"
    runtime_message: str = "Set LIVE_OPTION_CHAIN_ENABLED=true"
    runtime_underlying: str = "-"
    runtime_expiry: date | None = None
    runtime_subscribed_contracts: int = 0
    runtime_last_update: datetime | None = None
    runtime_last_error: str | None = None
    current_spot: float | None = None
    runtime_atm_strike: float | None = None
    contracts_resolved: int = 0
    option_ticks_received: int = 0
    last_spot_tick_at: datetime | None = None
    last_option_tick_at: datetime | None = None
    analytics_updated: bool = False
    health_market_feed: bool = False
    health_spot_feed: bool = False
    health_discovery: bool = False
    health_subscription: bool = False
    health_option_feed: bool = False
    health_analytics: bool = False
    health_dashboard: bool = False
    runtime_events: tuple[str, ...] = ()
    runtime_rows: tuple[DashboardOptionChainRuntimeRowView, ...] = ()
    event_rows: tuple[DashboardOptionChainEventView, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "strikes", tuple(self.strikes))
        _require_non_negative(self.strike_count, "strike_count")
        for name in (
            "total_call_oi",
            "total_put_oi",
            "max_call_oi_value",
            "max_put_oi_value",
            "max_call_change_oi_value",
            "max_put_change_oi_value",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative(value, name)
        _require_aware(self.timestamp, "timestamp")
        _require_aware(self.runtime_last_update, "runtime_last_update")
        _require_aware(self.last_spot_tick_at, "last_spot_tick_at")
        _require_aware(self.last_option_tick_at, "last_option_tick_at")
        _require_non_negative(self.runtime_subscribed_contracts, "runtime_subscribed_contracts")
        _require_non_negative(self.contracts_resolved, "contracts_resolved")
        _require_non_negative(self.option_ticks_received, "option_ticks_received")
        object.__setattr__(self, "runtime_events", tuple(self.runtime_events))
        rows = tuple(self.runtime_rows)
        events = tuple(self.event_rows)
        for row in rows:
            if not isinstance(row, DashboardOptionChainRuntimeRowView):
                raise TypeError("runtime_rows must contain DashboardOptionChainRuntimeRowView values")
        for event in events:
            if not isinstance(event, DashboardOptionChainEventView):
                raise TypeError("event_rows must contain DashboardOptionChainEventView values")
        object.__setattr__(self, "runtime_rows", rows)
        object.__setattr__(self, "event_rows", events)
        for strike in self.strikes:
            if not isinstance(strike, DashboardOptionChainStrikeView):
                raise TypeError("strikes must contain DashboardOptionChainStrikeView values")
        if self.strike_count != len(self.strikes):
            raise ValueError("strike_count must match strikes")
        object.__setattr__(self, "strikes", tuple(sorted(self.strikes, key=lambda strike: strike.strike_price)))


def unavailable_option_chain_view(symbol: str = "-") -> DashboardOptionChainView:
    return DashboardOptionChainView(
        symbol=symbol,
        available=False,
        exchange="-",
        expiry_date=None,
        timestamp=None,
        underlying_price=None,
        atm_strike=None,
        strike_count=0,
        total_call_oi=0,
        total_put_oi=0,
        total_call_change_oi=0,
        total_put_change_oi=0,
        oi_pcr=None,
        change_oi_pcr=None,
        max_call_oi_strike=None,
        max_call_oi_value=None,
        max_put_oi_strike=None,
        max_put_oi_value=None,
        max_call_change_oi_strike=None,
        max_call_change_oi_value=None,
        max_put_change_oi_strike=None,
        max_put_change_oi_value=None,
        resistance_strike=None,
        support_strike=None,
        max_pain_strike=None,
        call_pressure="-",
        put_pressure="-",
        positioning_bias="-",
        strikes=(),
        runtime_underlying=symbol,
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
    vwap_source: str
    vwap_source_type: str
    vwap_source_exchange: str
    vwap_source_expiry: date | None
    vwap_source_volume: int
    vwap_source_price: float | None
    vwap_source_state: str
    vwap_source_message: str
    vwap_subscription_active: bool
    vwap_historical_candles_loaded: int
    vwap_historical_volume: int
    vwap_historical_seed_complete: bool
    vwap_bootstrap_time: datetime | None
    vwap_live_tick_count: int
    vwap_last_live_volume: int
    vwap_last_delta_volume: int
    vwap_last_live_tick: datetime | None
    vwap_current_accumulated_volume: int
    vwap_last_error: str | None
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
class DashboardPriceActionView:
    symbol: str
    available: bool
    trend: str
    market_structure: str
    latest_hh: float | None
    latest_hl: float | None
    latest_lh: float | None
    latest_ll: float | None
    swing_high: float | None
    swing_low: float | None
    bos_direction: str
    choch_direction: str
    pullback_state: str
    range_state: str
    liquidity_sweep: str
    updated_at: datetime | None


def unavailable_price_action_view(symbol: str = "-") -> DashboardPriceActionView:
    return DashboardPriceActionView(
        symbol=symbol,
        available=False,
        trend="-",
        market_structure="-",
        latest_hh=None,
        latest_hl=None,
        latest_lh=None,
        latest_ll=None,
        swing_high=None,
        swing_low=None,
        bos_direction="-",
        choch_direction="-",
        pullback_state="-",
        range_state="-",
        liquidity_sweep="-",
        updated_at=None,
    )


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
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    lot_size: int | None
    approved_lots: int | None
    plan_status: str
    plan_valid_until: datetime | None
    risk_reason: str
    latest_order_status: str


@dataclass(frozen=True, slots=True)
class DashboardPositionView:
    symbol: str
    status: str
    has_position: bool
    side: str
    quantity: int | None
    average_price: float | None
    last_price: float | None
    unrealized_pnl: float | None
    realized_pnl: float | None
    stop_price: float | None
    target_price: float | None
    entry_price: float | None = None
    valid_until: datetime | None = None
    plan_id: str | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    exit_type: str = "-"
    mfe: float | None = None
    mae: float | None = None


@dataclass(frozen=True, slots=True)
class DashboardJournalView:
    symbol: str
    status: str
    records: int
    message: str
    latest_trade_id: str | None
    latest_exit_type: str
    latest_realized_pnl: float | None
    latest_opened_at: datetime | None
    latest_closed_at: datetime | None
    latest_instrument: str = "-"
    latest_side: str = "-"
    latest_quantity: int | None = None
    latest_entry_price: float | None = None
    latest_exit_price: float | None = None
    latest_holding_seconds: int | None = None
    latest_mfe: float | None = None
    latest_mae: float | None = None
    daily_pnl: float | None = None
    wins: int = 0
    losses: int = 0
    win_rate: float | None = None
    profit_factor: float | None = None


@dataclass(frozen=True, slots=True)
class DashboardView:
    runtime: DashboardRuntimeView
    markets: tuple[DashboardMarketView, ...]
    ai: tuple[DashboardAIView, ...]
    strategies: tuple[DashboardStrategyView, ...]
    positions: tuple[DashboardPositionView, ...]
    journals: tuple[DashboardJournalView, ...]
    price_actions: tuple[DashboardPriceActionView, ...] = field(default_factory=tuple)
    option_chains: tuple[DashboardOptionChainView, ...] = field(default_factory=tuple)
    live_market_data: DashboardLiveMarketDataView = field(default_factory=unavailable_live_market_data_view)
