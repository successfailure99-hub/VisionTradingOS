"""
Pure dashboard presentation builders.
"""

from application.lifecycle_manager import LifecycleSnapshot
from application.models import RuntimeSnapshot
from dashboard.models import (
    DashboardAIView,
    DashboardJournalView,
    DashboardMarketView,
    DashboardPositionView,
    DashboardRuntimeView,
    DashboardStrategyView,
    DashboardView,
)


MISSING = "-"


def build_dashboard_view(lifecycle_snapshot: LifecycleSnapshot) -> DashboardView:
    runtime_snapshots = lifecycle_snapshot.orchestrator_snapshot.runtime_snapshots
    return DashboardView(
        runtime=build_runtime_view(lifecycle_snapshot),
        markets=tuple(build_market_view(snapshot) for snapshot in runtime_snapshots),
        ai=tuple(build_ai_view(snapshot) for snapshot in runtime_snapshots),
        strategies=tuple(build_strategy_view(snapshot) for snapshot in runtime_snapshots),
        positions=tuple(build_position_view(snapshot) for snapshot in runtime_snapshots),
        journals=tuple(build_journal_view(snapshot) for snapshot in runtime_snapshots),
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
