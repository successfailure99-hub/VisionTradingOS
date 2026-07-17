"""
Pure dashboard presentation builders.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from application.lifecycle_manager import LifecycleSnapshot
from application.live_market_data import LiveMarketDataRuntimeSnapshot
from application.models import RuntimeSnapshot
from dashboard.models import (
    DashboardAIView,
    DashboardJournalView,
    DashboardLiveMarketDataView,
    DashboardLiveSubscriptionView,
    DashboardMarketSessionView,
    DashboardMarketView,
    DashboardOptionChainStrikeView,
    DashboardOptionChainEventView,
    DashboardOptionChainRuntimeRowView,
    DashboardOptionChainView,
    DashboardPriceActionView,
    DashboardPositionView,
    DashboardRuntimeView,
    DashboardStrategyView,
    DashboardView,
    unavailable_live_market_data_view,
    unavailable_option_chain_view,
    unavailable_price_action_view,
)


MISSING = "-"
INSTRUMENT_ORDER = ("NIFTY", "BANKNIFTY", "SENSEX")
IST = ZoneInfo("Asia/Kolkata")
PRE_OPEN_TIME = time(9, 0)
MARKET_OPEN_TIME = time(9, 15)
MARKET_CLOSE_TIME = time(15, 30)
OPTION_CHAIN_STALE_SECONDS = 60


def build_dashboard_view(
    lifecycle_snapshot: LifecycleSnapshot,
    live_market_data_snapshot: LiveMarketDataRuntimeSnapshot | None = None,
    *,
    live_option_chain_snapshot=None,
    clock=None,
) -> DashboardView:
    runtime_snapshots = _stable_runtime_snapshots(lifecycle_snapshot.orchestrator_snapshot.runtime_snapshots)
    option_status_by_symbol = _option_status_by_symbol(live_option_chain_snapshot)
    all_option_statuses = tuple(option_status_by_symbol.get(symbol) for symbol in INSTRUMENT_ORDER)
    return DashboardView(
        runtime=build_runtime_view(lifecycle_snapshot),
        markets=tuple(build_market_view(snapshot) for snapshot in runtime_snapshots),
        price_actions=tuple(build_price_action_view(snapshot) for snapshot in runtime_snapshots),
        ai=tuple(build_ai_view(snapshot) for snapshot in runtime_snapshots),
        strategies=tuple(build_strategy_view(snapshot) for snapshot in runtime_snapshots),
        positions=tuple(build_position_view(snapshot) for snapshot in runtime_snapshots),
        journals=tuple(build_journal_view(snapshot) for snapshot in runtime_snapshots),
        option_chains=tuple(
            build_option_chain_view(
                snapshot,
                option_status_by_symbol.get(_enum_text(snapshot.symbol)),
                all_option_statuses=all_option_statuses,
                clock=clock,
            )
            for snapshot in runtime_snapshots
        ),
        live_market_data=build_live_market_data_view(live_market_data_snapshot, clock=clock),
    )


def build_live_market_data_view(
    snapshot: LiveMarketDataRuntimeSnapshot | None,
    *,
    clock=None,
) -> DashboardLiveMarketDataView:
    if snapshot is None:
        return unavailable_live_market_data_view()
    websocket = snapshot.websocket
    subscriptions = tuple(getattr(websocket, "subscribed_instruments", ()) or ()) if websocket is not None else ()
    rows = tuple(
        DashboardLiveSubscriptionView(
            instrument=_enum_text(subscription.instrument),
            exchange=_enum_text(subscription.exchange),
            instrument_token=subscription.instrument_token,
            mode=_enum_text(subscription.mode),
        )
        for subscription in subscriptions
    )
    return DashboardLiveMarketDataView(
        available=True,
        runtime_status=_enum_text(snapshot.status),
        ready=snapshot.ready,
        running=snapshot.running,
        websocket_status=_enum_text(getattr(websocket, "status", None)),
        connected=bool(getattr(websocket, "connected", False)),
        configured_instruments=tuple(_enum_text(instrument) for instrument in snapshot.configured_instruments),
        configured_tokens=tuple(snapshot.configured_tokens),
        subscription_count=len(rows),
        subscription_rows=rows,
        connection_count=getattr(websocket, "connection_count", 0),
        disconnection_count=getattr(websocket, "disconnection_count", 0),
        reconnect_count=getattr(websocket, "reconnect_count", 0),
        raw_tick_count=getattr(websocket, "raw_tick_count", 0),
        normalized_tick_count=getattr(websocket, "normalized_tick_count", 0),
        delivered_tick_count=getattr(websocket, "delivered_tick_count", 0),
        rejected_tick_count=getattr(websocket, "rejected_tick_count", 0),
        start_count=snapshot.start_count,
        stop_count=snapshot.stop_count,
        last_connected_at=getattr(websocket, "last_connected_at", None),
        last_disconnected_at=getattr(websocket, "last_disconnected_at", None),
        last_tick_at=getattr(websocket, "last_tick_at", None),
        last_started_at=snapshot.last_started_at,
        last_stopped_at=snapshot.last_stopped_at,
        last_error=_safe_error(snapshot.last_error or getattr(websocket, "last_error", None)),
        market_session=build_market_session_view(snapshot, clock=clock),
    )


def build_market_session_view(
    snapshot: LiveMarketDataRuntimeSnapshot,
    *,
    clock=None,
) -> DashboardMarketSessionView:
    now = _clock_now(clock)
    market_status, session, next_open = _market_status(now)
    websocket = snapshot.websocket
    connected = bool(getattr(websocket, "connected", False))
    delivered_tick_count = getattr(websocket, "delivered_tick_count", 0) if websocket is not None else 0
    last_tick_at = getattr(websocket, "last_tick_at", None) if websocket is not None else None
    if not connected:
        websocket_text = "Disconnected"
        live_ticks = "Offline"
    elif delivered_tick_count > 0 or last_tick_at is not None:
        websocket_text = "Connected"
        live_ticks = "Receiving"
    else:
        websocket_text = "Connected"
        live_ticks = "Waiting"
    return DashboardMarketSessionView(
        market_status=market_status,
        current_time=_time_text(now),
        session=session,
        websocket=websocket_text,
        live_ticks=live_ticks,
        last_tick=_time_text(last_tick_at) if last_tick_at is not None else MISSING,
        next_open=next_open,
    )


def build_runtime_view(lifecycle_snapshot: LifecycleSnapshot) -> DashboardRuntimeView:
    orchestrator = lifecycle_snapshot.orchestrator_snapshot
    return DashboardRuntimeView(
        application_status=_enum_text(lifecycle_snapshot.status),
        broker_mode=_enum_text(orchestrator.broker_mode),
        safety_mode=_enum_text(orchestrator.safety_mode),
        configured_instruments=tuple(_enum_text(instrument) for instrument in orchestrator.configured_instruments),
        market_data_ready=orchestrator.shared_market_data_ready,
        trade_journal_ready=orchestrator.shared_trade_journal_ready,
        start_count=lifecycle_snapshot.start_count,
        stop_count=lifecycle_snapshot.stop_count,
        restart_count=lifecycle_snapshot.restart_count,
        last_started_at=lifecycle_snapshot.last_started_at,
        last_stopped_at=lifecycle_snapshot.last_stopped_at,
        last_error=lifecycle_snapshot.last_error,
    )


def build_market_view(runtime_snapshot: RuntimeSnapshot) -> DashboardMarketView:
    tick = runtime_snapshot.latest_tick
    candle = runtime_snapshot.latest_candle
    context = runtime_snapshot.market_context
    vwap = runtime_snapshot.vwap
    vwap_source = runtime_snapshot.vwap_source
    cpr = runtime_snapshot.cpr
    camarilla = runtime_snapshot.camarilla
    return DashboardMarketView(
        symbol=_enum_text(runtime_snapshot.symbol),
        timeframe=runtime_snapshot.timeframe,
        runtime_status=_enum_text(runtime_snapshot.status),
        last_price=getattr(tick, "last_price", None),
        bid_price=getattr(tick, "bid_price", None),
        ask_price=getattr(tick, "ask_price", None),
        session_high=getattr(context, "session_high", None),
        session_low=getattr(context, "session_low", None),
        latest_candle_open=getattr(candle, "open", None),
        latest_candle_high=getattr(candle, "high", None),
        latest_candle_low=getattr(candle, "low", None),
        latest_candle_close=getattr(candle, "close", None),
        vwap=getattr(vwap, "vwap", None),
        vwap_source=_vwap_source_label(runtime_snapshot),
        vwap_source_type=_vwap_source_text(vwap_source, "source_type"),
        vwap_source_exchange=_vwap_source_text(vwap_source, "source_exchange"),
        vwap_source_expiry=getattr(vwap_source, "expiry", None),
        vwap_source_volume=getattr(vwap_source, "cumulative_volume", 0) if vwap_source is not None else 0,
        vwap_source_price=getattr(vwap_source, "last_source_price", None),
        vwap_source_state=_vwap_source_text(vwap_source, "state"),
        vwap_source_message=_vwap_source_text(vwap_source, "message"),
        vwap_subscription_active=bool(getattr(vwap_source, "subscription_active", False)),
        vwap_historical_candles_loaded=getattr(vwap_source, "historical_candles_loaded", 0) if vwap_source is not None else 0,
        vwap_historical_volume=getattr(vwap_source, "historical_volume", 0) if vwap_source is not None else 0,
        vwap_live_tick_count=getattr(vwap_source, "live_tick_count", 0) if vwap_source is not None else 0,
        vwap_last_live_tick=getattr(vwap_source, "last_live_tick", None),
        vwap_last_error=getattr(vwap_source, "last_error", None),
        cpr_pivot=getattr(cpr, "pivot", None),
        cpr_bc=getattr(cpr, "bc", None),
        cpr_tc=getattr(cpr, "tc", None),
        camarilla_h3=getattr(camarilla, "h3", None),
        camarilla_h4=getattr(camarilla, "h4", None),
        camarilla_h5=getattr(camarilla, "h5", None),
        camarilla_h6=getattr(camarilla, "h6", None),
        camarilla_l3=getattr(camarilla, "l3", None),
        camarilla_l4=getattr(camarilla, "l4", None),
        camarilla_l5=getattr(camarilla, "l5", None),
        camarilla_l6=getattr(camarilla, "l6", None),
        market_bias=_enum_text(getattr(context, "market_bias", None)),
        market_phase=_enum_text(getattr(context, "market_phase", None)),
        context_strength=_enum_text(getattr(context, "context_strength", None)),
        option_chain_direction=_enum_text(getattr(context, "option_chain_direction", None)),
        updated_at=runtime_snapshot.updated_at,
    )


def _vwap_source_label(runtime_snapshot: RuntimeSnapshot) -> str:
    source = runtime_snapshot.vwap_source
    if source is None:
        return f"{_enum_text(runtime_snapshot.symbol)} Spot" if runtime_snapshot.vwap is not None else MISSING
    if getattr(source, "ready", False):
        return _enum_text(getattr(source, "trading_symbol", None))
    reason = getattr(source, "unavailable_reason", None)
    return _enum_text(reason) if reason else MISSING


def _vwap_source_text(source, field_name: str) -> str:
    if source is None:
        return MISSING
    value = getattr(source, field_name, None)
    return _enum_text(value) if value else MISSING


def build_price_action_view(runtime_snapshot: RuntimeSnapshot) -> DashboardPriceActionView:
    price_action = runtime_snapshot.price_action
    symbol = _enum_text(runtime_snapshot.symbol)
    if price_action is None:
        return unavailable_price_action_view(symbol)
    if _enum_text(price_action.symbol) != symbol:
        return unavailable_price_action_view(symbol)
    return DashboardPriceActionView(
        symbol=symbol,
        available=True,
        trend=_enum_text(price_action.trend),
        market_structure=_enum_text(price_action.market_structure),
        latest_hh=_swing_price(price_action.latest_hh),
        latest_hl=_swing_price(price_action.latest_hl),
        latest_lh=_swing_price(price_action.latest_lh),
        latest_ll=_swing_price(price_action.latest_ll),
        swing_high=_swing_price(price_action.swing_high),
        swing_low=_swing_price(price_action.swing_low),
        bos_direction=_enum_text(price_action.bos_direction),
        choch_direction=_enum_text(price_action.choch_direction),
        pullback_state=_enum_text(price_action.pullback_state),
        range_state=_enum_text(price_action.range_state),
        liquidity_sweep=_enum_text(price_action.liquidity_sweep),
        updated_at=price_action.updated_at,
    )


def build_option_chain_view(
    runtime_snapshot: RuntimeSnapshot,
    runtime_status=None,
    *,
    all_option_statuses=(),
    clock=None,
) -> DashboardOptionChainView:
    state = runtime_snapshot.option_chain
    symbol = _enum_text(runtime_snapshot.symbol)
    if state is None:
        return _apply_option_runtime_status(
            unavailable_option_chain_view(symbol),
            runtime_status,
            all_option_statuses=all_option_statuses,
            clock=clock,
        )
    if _enum_text(state.symbol) != symbol:
        return _apply_option_runtime_status(
            unavailable_option_chain_view(symbol),
            runtime_status,
            all_option_statuses=all_option_statuses,
            clock=clock,
        )
    strikes = tuple(
        _build_option_chain_strike_view(strike, state.atm_strike)
        for strike in sorted(tuple(state.strikes), key=lambda strike: strike.strike_price)
    )
    return _apply_option_runtime_status(DashboardOptionChainView(
        symbol=symbol,
        available=True,
        exchange=_enum_text(state.exchange),
        expiry_date=state.expiry_date,
        timestamp=state.timestamp,
        underlying_price=state.underlying_price,
        atm_strike=state.atm_strike,
        strike_count=state.strike_count,
        total_call_oi=state.total_call_oi,
        total_put_oi=state.total_put_oi,
        total_call_change_oi=state.total_call_change_oi,
        total_put_change_oi=state.total_put_change_oi,
        oi_pcr=state.oi_pcr,
        change_oi_pcr=state.change_oi_pcr,
        max_call_oi_strike=_metric_strike(state.max_call_oi),
        max_call_oi_value=_metric_value(state.max_call_oi),
        max_put_oi_strike=_metric_strike(state.max_put_oi),
        max_put_oi_value=_metric_value(state.max_put_oi),
        max_call_change_oi_strike=_metric_strike(state.max_call_change_oi),
        max_call_change_oi_value=_metric_value(state.max_call_change_oi),
        max_put_change_oi_strike=_metric_strike(state.max_put_change_oi),
        max_put_change_oi_value=_metric_value(state.max_put_change_oi),
        resistance_strike=state.resistance_strike,
        support_strike=state.support_strike,
        max_pain_strike=state.max_pain_strike,
        call_pressure=_enum_text(state.call_pressure),
        put_pressure=_enum_text(state.put_pressure),
        positioning_bias=_enum_text(state.positioning_bias),
        strikes=strikes,
    ), runtime_status, all_option_statuses=all_option_statuses, clock=clock)


def build_ai_view(runtime_snapshot: RuntimeSnapshot) -> DashboardAIView:
    ai = runtime_snapshot.ai_reasoning
    return DashboardAIView(
        symbol=_enum_text(runtime_snapshot.symbol),
        market_summary=_enum_text(getattr(ai, "market_summary", None)),
        confidence=_enum_text(getattr(ai, "confidence", None)),
        agreement=_enum_text(getattr(ai, "agreement_summary", None)),
        conflict=_enum_text(getattr(ai, "conflict_summary", None)),
        trading_suitability=_enum_text(getattr(ai, "trading_suitability", None)),
        explanation=getattr(ai, "explanation", None) or MISSING,
        missing_information=tuple(getattr(ai, "missing_information", ()) or ()),
    )


def build_strategy_view(runtime_snapshot: RuntimeSnapshot) -> DashboardStrategyView:
    strategy = runtime_snapshot.strategy
    risk = runtime_snapshot.risk
    order = runtime_snapshot.latest_order
    return DashboardStrategyView(
        symbol=_enum_text(runtime_snapshot.symbol),
        decision=_enum_text(getattr(strategy, "decision", None)),
        direction=_enum_text(getattr(strategy, "direction", None)),
        setup_quality=_enum_text(getattr(strategy, "setup_quality", None)),
        entry_reference=_enum_text(getattr(strategy, "entry_reference", None)),
        stop_reference=_enum_text(getattr(strategy, "stop_reference", None)),
        target_reference=_enum_text(getattr(strategy, "target_reference", None)),
        block_reason=_enum_text(getattr(strategy, "block_reason", None)),
        risk_decision=_enum_text(getattr(risk, "decision", None)),
        approved_quantity=getattr(risk, "approved_quantity", None),
        risk_amount=getattr(risk, "estimated_risk_amount", None),
        reward_risk=getattr(risk, "reward_risk_ratio", None),
        latest_order_status=_enum_text(getattr(order, "status", None)),
    )


def build_position_view(runtime_snapshot: RuntimeSnapshot) -> DashboardPositionView:
    position = runtime_snapshot.position
    tick = runtime_snapshot.latest_tick
    has_position = position is not None and getattr(position, "absolute_quantity", 0) > 0
    return DashboardPositionView(
        symbol=_enum_text(runtime_snapshot.symbol),
        status="Active Position" if has_position else "No Active Position",
        has_position=has_position,
        side=_enum_text(getattr(position, "side", None)),
        quantity=getattr(position, "absolute_quantity", None),
        average_price=getattr(position, "average_entry_price", None),
        last_price=getattr(tick, "last_price", None) or getattr(position, "mark_price", None),
        unrealized_pnl=getattr(position, "unrealized_pnl", None),
        realized_pnl=getattr(position, "realized_pnl", None),
        stop_price=getattr(runtime_snapshot.risk, "stop_price", None),
        target_price=getattr(runtime_snapshot.risk, "target_price", None),
    )


def build_journal_view(runtime_snapshot: RuntimeSnapshot) -> DashboardJournalView:
    record = runtime_snapshot.latest_journal_record
    has_record = record is not None
    return DashboardJournalView(
        symbol=_enum_text(runtime_snapshot.symbol),
        status="Ready",
        records=1 if has_record else 0,
        message="Latest completed DRY_RUN trade" if has_record else "No completed DRY_RUN trades",
        latest_trade_id=getattr(record, "trade_id", None),
        latest_exit_type=_enum_text(getattr(record, "exit_type", None)),
        latest_realized_pnl=getattr(record, "realized_gross_pnl", None),
        latest_opened_at=getattr(record, "opened_at", None),
        latest_closed_at=getattr(record, "closed_at", None),
    )


def _enum_text(value) -> str:
    if value is None:
        return MISSING
    raw = getattr(value, "value", value)
    text = str(raw).strip()
    if not text:
        return MISSING
    if text.isupper():
        return text
    return text.replace("_", " ").title()


def _safe_error(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return value.__class__.__name__
    return value


def _build_option_chain_strike_view(strike, atm_strike: float | None) -> DashboardOptionChainStrikeView:
    call = strike.call
    put = strike.put
    return DashboardOptionChainStrikeView(
        strike_price=strike.strike_price,
        is_atm=atm_strike is not None and strike.strike_price == atm_strike,
        call_last_price=getattr(call, "last_price", None),
        call_open_interest=getattr(call, "open_interest", None),
        call_change_open_interest=getattr(call, "change_in_open_interest", None),
        call_volume=getattr(call, "volume", None),
        call_bid_price=getattr(call, "bid_price", None),
        call_ask_price=getattr(call, "ask_price", None),
        put_last_price=getattr(put, "last_price", None),
        put_open_interest=getattr(put, "open_interest", None),
        put_change_open_interest=getattr(put, "change_in_open_interest", None),
        put_volume=getattr(put, "volume", None),
        put_bid_price=getattr(put, "bid_price", None),
        put_ask_price=getattr(put, "ask_price", None),
    )


def _metric_strike(metric) -> float | None:
    return getattr(metric, "strike_price", None)


def _metric_value(metric) -> int | None:
    return getattr(metric, "value", None)


def _option_status_by_symbol(snapshot) -> dict[str, object]:
    if snapshot is None:
        return {}
    return {
        _enum_text(getattr(item, "underlying", None)): item
        for item in tuple(getattr(snapshot, "instruments", ()) or ())
    }


def _apply_option_runtime_status(
    view: DashboardOptionChainView,
    status,
    *,
    all_option_statuses=(),
    clock=None,
) -> DashboardOptionChainView:
    rows = _option_runtime_rows(all_option_statuses, clock=clock)
    events = _option_event_rows(all_option_statuses)
    if status is None:
        return DashboardOptionChainView(
            **{
                **_option_view_values(view),
                "runtime_rows": rows,
                "event_rows": events,
            }
        )
    error = _safe_error(getattr(status, "last_error", None))
    runtime_status = _derived_option_runtime_status(view, status, error, clock=clock)
    message = _option_runtime_message(status, runtime_status, error)
    subscribed = getattr(status, "option_token_count", 0) if getattr(status, "subscriptions_active", False) else 0
    return DashboardOptionChainView(
        **_option_view_values(view),
        runtime_status=runtime_status,
        runtime_message=message,
        runtime_underlying=_enum_text(getattr(status, "underlying", None)),
        runtime_expiry=getattr(status, "last_expiry", None),
        runtime_subscribed_contracts=subscribed,
        runtime_last_update=getattr(status, "last_updated_at", None),
        runtime_last_error=error,
        current_spot=getattr(status, "current_spot", None),
        runtime_atm_strike=getattr(status, "atm_strike", None),
        contracts_resolved=getattr(status, "option_token_count", 0) if getattr(status, "contracts_resolved", False) else 0,
        option_ticks_received=getattr(status, "option_ticks_received", 0),
        last_spot_tick_at=getattr(status, "last_spot_tick_at", None),
        last_option_tick_at=getattr(status, "last_option_tick_at", None),
        analytics_updated=bool(getattr(status, "analytics_updated", False)),
        health_market_feed=True,
        health_spot_feed=getattr(status, "last_spot_tick_at", None) is not None,
        health_discovery=bool(getattr(status, "discovery_ready", False)),
        health_subscription=bool(getattr(status, "subscriptions_active", False)),
        health_option_feed=getattr(status, "option_ticks_received", 0) > 0,
        health_analytics=bool(getattr(status, "analytics_updated", False)),
        health_dashboard=view.available,
        runtime_events=tuple(getattr(status, "events", ()) or ()),
        runtime_rows=rows,
        event_rows=events,
    )


def _option_view_values(view: DashboardOptionChainView) -> dict[str, object]:
    return {
        "symbol": view.symbol,
        "available": view.available,
        "exchange": view.exchange,
        "expiry_date": view.expiry_date,
        "timestamp": view.timestamp,
        "underlying_price": view.underlying_price,
        "atm_strike": view.atm_strike,
        "strike_count": view.strike_count,
        "total_call_oi": view.total_call_oi,
        "total_put_oi": view.total_put_oi,
        "total_call_change_oi": view.total_call_change_oi,
        "total_put_change_oi": view.total_put_change_oi,
        "oi_pcr": view.oi_pcr,
        "change_oi_pcr": view.change_oi_pcr,
        "max_call_oi_strike": view.max_call_oi_strike,
        "max_call_oi_value": view.max_call_oi_value,
        "max_put_oi_strike": view.max_put_oi_strike,
        "max_put_oi_value": view.max_put_oi_value,
        "max_call_change_oi_strike": view.max_call_change_oi_strike,
        "max_call_change_oi_value": view.max_call_change_oi_value,
        "max_put_change_oi_strike": view.max_put_change_oi_strike,
        "max_put_change_oi_value": view.max_put_change_oi_value,
        "resistance_strike": view.resistance_strike,
        "support_strike": view.support_strike,
        "max_pain_strike": view.max_pain_strike,
        "call_pressure": view.call_pressure,
        "put_pressure": view.put_pressure,
        "positioning_bias": view.positioning_bias,
        "strikes": view.strikes,
    }


def _derived_option_runtime_status(view, status, error: str | None, *, clock=None) -> str:
    if error:
        return "Error"
    raw = _enum_text(getattr(status, "state", None))
    if raw == "Disabled":
        return "Disabled"
    if raw == "Starting":
        return "Starting"
    if not getattr(status, "last_spot_tick_at", None):
        return "Waiting For Spot"
    if not getattr(status, "contracts_resolved", False):
        return "Discovering"
    if not getattr(status, "subscriptions_active", False):
        return "Subscribing"
    option_ticks = getattr(status, "option_ticks_received", 0)
    if option_ticks <= 0:
        return "Waiting For Option Ticks"
    if _option_chain_is_stale(getattr(status, "last_option_tick_at", None), clock):
        return "Stale"
    if not view.available:
        return "Analytics Waiting"
    return "Receiving" if getattr(status, "analytics_updated", False) else "Analytics Waiting"


def _option_chain_is_stale(last_option_tick_at, clock) -> bool:
    if last_option_tick_at is None or clock is None:
        return False
    try:
        now = _clock_now(clock)
    except Exception:
        return False
    return (now - last_option_tick_at.astimezone(IST)).total_seconds() > OPTION_CHAIN_STALE_SECONDS


def _option_runtime_rows(statuses, *, clock=None) -> tuple[DashboardOptionChainRuntimeRowView, ...]:
    rows = []
    by_symbol = {
        _enum_text(getattr(status, "underlying", None)): status
        for status in tuple(statuses or ())
        if status is not None
    }
    for symbol in INSTRUMENT_ORDER:
        status = by_symbol.get(symbol)
        state = _derived_option_runtime_row_status(status, clock=clock) if status is not None else "Disabled"
        rows.append(
            DashboardOptionChainRuntimeRowView(
                instrument=symbol,
                state=state,
                expiry=getattr(status, "last_expiry", None),
                contracts=getattr(status, "option_token_count", 0) if status is not None else 0,
                option_ticks=getattr(status, "option_ticks_received", 0) if status is not None else 0,
                last_update=getattr(status, "last_updated_at", None),
                last_error=_safe_error(getattr(status, "last_error", None)),
            )
        )
    return tuple(rows)


def _option_event_rows(statuses) -> tuple[DashboardOptionChainEventView, ...]:
    rows = []
    for status in tuple(statuses or ()):
        if status is None:
            continue
        instrument = _enum_text(getattr(status, "underlying", None))
        state = _enum_text(getattr(status, "state", None))
        for item in tuple(getattr(status, "events", ()) or ()):
            text = str(item)
            parts = text.split(" ", 1)
            rows.append(
                DashboardOptionChainEventView(
                    timestamp=parts[0] if parts else MISSING,
                    instrument=instrument,
                    state=state,
                    message=parts[1] if len(parts) > 1 else text,
                )
            )
    return tuple(rows[-24:])


def _derived_option_runtime_row_status(status, *, clock=None) -> str:
    error = _safe_error(getattr(status, "last_error", None))
    if error:
        return "Error"
    raw = _enum_text(getattr(status, "state", None))
    if raw == "Disabled":
        return "Disabled"
    if raw == "Starting":
        return "Starting"
    if not getattr(status, "last_spot_tick_at", None):
        return "Waiting For Spot"
    if not getattr(status, "contracts_resolved", False):
        return "Discovering"
    if not getattr(status, "subscriptions_active", False):
        return "Subscribing"
    option_ticks = getattr(status, "option_ticks_received", 0)
    if option_ticks <= 0:
        return "Waiting For Option Ticks"
    if _option_chain_is_stale(getattr(status, "last_option_tick_at", None), clock):
        return "Stale"
    return "Receiving" if getattr(status, "analytics_updated", False) else "Analytics Waiting"


def _option_runtime_message(status, runtime_status: str, error: str | None) -> str:
    if error:
        return error
    if runtime_status == "Disabled":
        return "Set LIVE_OPTION_CHAIN_ENABLED=true"
    if runtime_status == "Waiting For Spot":
        return f"Waiting for first {_enum_text(getattr(status, 'underlying', None))} spot tick"
    if runtime_status == "Discovering Contracts":
        return "Resolving contracts..."
    if runtime_status == "Discovering":
        return "Discovering contracts"
    if runtime_status == "Subscribing":
        return "Subscribing to option contracts"
    if runtime_status == "Waiting For Option Ticks":
        return "Waiting for first option tick"
    if runtime_status == "Analytics Waiting":
        return "Analytics waiting for sufficient option ticks"
    if runtime_status == "Stale":
        return "Last option tick is stale"
    if runtime_status == "Receiving":
        return "Receiving live option-chain ticks"
    if runtime_status == "Starting":
        return "Starting live option-chain runtime"
    return runtime_status


def _swing_price(swing) -> float | None:
    return getattr(swing, "price", None)


def _clock_now(clock) -> datetime:
    if clock is None:
        raise ValueError("clock is required for market session rendering")
    value = clock()
    if not isinstance(value, datetime):
        raise TypeError("clock result must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock result must be timezone-aware")
    return value.astimezone(IST)


def _market_status(now: datetime) -> tuple[str, str, str]:
    if now.weekday() >= 5:
        next_open = _next_open(now)
        return "NSE closed - weekend", "Closed", _next_open_text(next_open, include_day=True)
    current = now.time()
    today_open = now.replace(hour=MARKET_OPEN_TIME.hour, minute=MARKET_OPEN_TIME.minute, second=0, microsecond=0)
    if current < PRE_OPEN_TIME:
        return "Waiting for NSE to open", "Closed", _next_open_text(today_open)
    if PRE_OPEN_TIME <= current < MARKET_OPEN_TIME:
        return "NSE pre-open", "Pre-Open", _next_open_text(today_open)
    if MARKET_OPEN_TIME <= current <= MARKET_CLOSE_TIME:
        return "NSE market open", "Live", MISSING
    next_open = _next_open(now)
    return "NSE closed for the day", "Closed", _next_open_text(next_open, include_day=next_open.date() != now.date())


def _next_open(now: datetime) -> datetime:
    candidate = now.replace(hour=MARKET_OPEN_TIME.hour, minute=MARKET_OPEN_TIME.minute, second=0, microsecond=0)
    if now.weekday() < 5 and now.time() < MARKET_OPEN_TIME:
        return candidate
    candidate = candidate + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _next_open_text(value: datetime, *, include_day: bool = False) -> str:
    prefix = f"{value.strftime('%A')} " if include_day else ""
    return f"{prefix}{value.strftime('%H:%M')} IST"


def _time_text(value: datetime) -> str:
    if not isinstance(value, datetime):
        return MISSING
    if value.tzinfo is None or value.utcoffset() is None:
        return MISSING
    return f"{value.astimezone(IST).strftime('%H:%M')} IST"


def _stable_runtime_snapshots(runtime_snapshots) -> tuple[RuntimeSnapshot, ...]:
    order = {symbol: index for index, symbol in enumerate(INSTRUMENT_ORDER)}
    return tuple(
        sorted(
            tuple(runtime_snapshots),
            key=lambda snapshot: (order.get(_enum_text(snapshot.symbol), len(order)), _enum_text(snapshot.symbol)),
        )
    )
