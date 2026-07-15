"""
Pure dashboard presentation builders.
"""

from application.lifecycle_manager import LifecycleSnapshot
from application.live_market_data import LiveMarketDataRuntimeSnapshot
from application.models import RuntimeSnapshot
from dashboard.models import (
    DashboardAIView,
    DashboardJournalView,
    DashboardLiveMarketDataView,
    DashboardLiveSubscriptionView,
    DashboardMarketView,
    DashboardOptionChainStrikeView,
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


def build_dashboard_view(
    lifecycle_snapshot: LifecycleSnapshot,
    live_market_data_snapshot: LiveMarketDataRuntimeSnapshot | None = None,
) -> DashboardView:
    runtime_snapshots = _stable_runtime_snapshots(lifecycle_snapshot.orchestrator_snapshot.runtime_snapshots)
    return DashboardView(
        runtime=build_runtime_view(lifecycle_snapshot),
        markets=tuple(build_market_view(snapshot) for snapshot in runtime_snapshots),
        price_actions=tuple(build_price_action_view(snapshot) for snapshot in runtime_snapshots),
        ai=tuple(build_ai_view(snapshot) for snapshot in runtime_snapshots),
        strategies=tuple(build_strategy_view(snapshot) for snapshot in runtime_snapshots),
        positions=tuple(build_position_view(snapshot) for snapshot in runtime_snapshots),
        journals=tuple(build_journal_view(snapshot) for snapshot in runtime_snapshots),
        option_chains=tuple(build_option_chain_view(snapshot) for snapshot in runtime_snapshots),
        live_market_data=build_live_market_data_view(live_market_data_snapshot),
    )


def build_live_market_data_view(
    snapshot: LiveMarketDataRuntimeSnapshot | None,
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


def build_price_action_view(runtime_snapshot: RuntimeSnapshot) -> DashboardPriceActionView:
    price_action = runtime_snapshot.price_action
    symbol = _enum_text(runtime_snapshot.symbol)
    if price_action is None:
        return unavailable_price_action_view(symbol)
    return DashboardPriceActionView(
        symbol=_enum_text(price_action.symbol),
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


def build_option_chain_view(runtime_snapshot: RuntimeSnapshot) -> DashboardOptionChainView:
    state = runtime_snapshot.option_chain
    if state is None:
        return unavailable_option_chain_view(_enum_text(runtime_snapshot.symbol))
    strikes = tuple(
        _build_option_chain_strike_view(strike, state.atm_strike)
        for strike in sorted(tuple(state.strikes), key=lambda strike: strike.strike_price)
    )
    return DashboardOptionChainView(
        symbol=_enum_text(state.symbol),
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
    )


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
    return DashboardPositionView(
        symbol=_enum_text(runtime_snapshot.symbol),
        has_position=position is not None and getattr(position, "absolute_quantity", 0) > 0,
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
    return DashboardJournalView(
        symbol=_enum_text(runtime_snapshot.symbol),
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


def _swing_price(swing) -> float | None:
    return getattr(swing, "price", None)


def _stable_runtime_snapshots(runtime_snapshots) -> tuple[RuntimeSnapshot, ...]:
    order = {symbol: index for index, symbol in enumerate(INSTRUMENT_ORDER)}
    return tuple(
        sorted(
            tuple(runtime_snapshots),
            key=lambda snapshot: (order.get(_enum_text(snapshot.symbol), len(order)), _enum_text(snapshot.symbol)),
        )
    )
