"""
Pure dashboard presentation builders.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from application.lifecycle_manager import LifecycleSnapshot
from application.exchange_calendar import DEFAULT_EXCHANGE_CALENDAR, ExchangeSessionPhase
from application.live_market_data import LiveMarketDataRuntimeSnapshot
from application.models import RuntimeSnapshot
from dashboard import formatters
from dashboard.models import (
    DashboardAIView,
    DashboardAnalyticsMetricView,
    DashboardAnalyticsRowView,
    DashboardAnalyticsView,
    DashboardBacktestView,
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
    DashboardRuntimeComponentHealthView,
    DashboardRuntimeHealthSummary,
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
MARKET_OPEN_TIME = time(9, 15)
OPTION_CHAIN_STALE_SECONDS = 60


def _snapshot_generation_id(runtime_snapshot: RuntimeSnapshot) -> str:
    created_at = getattr(runtime_snapshot, "snapshot_created_at", None) or getattr(runtime_snapshot, "updated_at", None)
    timestamp = formatters.timestamp(created_at) if created_at is not None else "-"
    return f"{_enum_text(runtime_snapshot.symbol)}:{runtime_snapshot.timeframe}:{timestamp}"


def _runtime_market_timestamp(runtime_snapshot: RuntimeSnapshot) -> datetime | None:
    return (
        getattr(runtime_snapshot, "latest_tick_at", None)
        or getattr(runtime_snapshot, "latest_closed_candle_at", None)
        or getattr(runtime_snapshot, "latest_analysis_at", None)
        or getattr(runtime_snapshot, "updated_at", None)
    )


def _vision_decision_timestamp(runtime_snapshot: RuntimeSnapshot) -> datetime | None:
    vision_snapshot = getattr(runtime_snapshot, "vision_method_snapshot", None)
    if vision_snapshot is not None:
        return getattr(vision_snapshot, "timestamp", None)
    candidate = getattr(runtime_snapshot, "vision_trade_candidate", None)
    return getattr(candidate, "timestamp", None)


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
        markets=tuple(build_market_view(snapshot, clock=clock) for snapshot in runtime_snapshots),
        price_actions=tuple(build_price_action_view(snapshot) for snapshot in runtime_snapshots),
        ai=tuple(build_ai_view(snapshot) for snapshot in runtime_snapshots),
        strategies=tuple(build_strategy_view(snapshot) for snapshot in runtime_snapshots),
        positions=tuple(build_position_view(snapshot) for snapshot in runtime_snapshots),
        journals=tuple(build_journal_view(snapshot) for snapshot in runtime_snapshots),
        analytics=tuple(build_analytics_view(snapshot) for snapshot in runtime_snapshots),
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
        backtest=build_backtest_view(lifecycle_snapshot),
    )


def build_backtest_view(lifecycle_snapshot: LifecycleSnapshot) -> DashboardBacktestView:
    backtest = getattr(lifecycle_snapshot.orchestrator_snapshot, "deterministic_backtest", None)
    analytics = getattr(backtest, "aggregate_analytics", None)
    progress = getattr(backtest, "current_progress", None)
    findings = tuple(getattr(backtest, "findings", ()) or ())
    return DashboardBacktestView(
        enabled=bool(getattr(backtest, "enabled", False)),
        lifecycle_state=_enum_text(getattr(backtest, "lifecycle_state", None)),
        mode=_enum_text(getattr(backtest, "mode", None)),
        current_session=_enum_text(getattr(progress, "session_id", None)),
        completed_sessions=getattr(backtest, "completed_sessions", 0),
        total_sessions=getattr(backtest, "total_sessions", 0),
        current_replay_progress=getattr(progress, "progress_percentage", 0.0),
        closed_trades=getattr(analytics, "trade_count", 0),
        net_pnl=getattr(analytics, "net_pnl", None),
        win_rate=getattr(analytics, "win_rate", None),
        drawdown=getattr(analytics, "maximum_observed_session_drawdown", None),
        reproducibility_status=_enum_text(getattr(backtest, "reproducibility_status", None)),
        last_finding=_enum_text(getattr(findings[-1], "code", None)) if findings else "-",
        final_outcome=_enum_text(getattr(backtest, "outcome", None)),
        report_path=_source_name(getattr(backtest, "report_path", None)),
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
        feed_delay_text=_feed_delay_text(getattr(websocket, "last_tick_at", None), clock),
        connection_state=_enum_text(getattr(websocket, "status", None)),
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
    validation = getattr(orchestrator, "live_validation", None)
    replay = getattr(orchestrator, "historical_replay", None)
    latency = tuple(getattr(validation, "latency_summaries", ()) or ())
    p95 = max((item.p95_ms for item in latency), default=None)
    runtime_snapshots = tuple(getattr(orchestrator, "runtime_snapshots", ()) or ())
    operational = next((getattr(snapshot, "operational_readiness", None) for snapshot in runtime_snapshots if getattr(snapshot, "operational_readiness", None) is not None), None)
    journal_persistence = next((getattr(snapshot, "journal_persistence", None) for snapshot in runtime_snapshots if getattr(snapshot, "journal_persistence", None) is not None), None)
    canonical_journal_ready = bool(journal_persistence is not None and getattr(journal_persistence, "operational_state", "") in {"READY_EMPTY", "READY_WITH_RECORDS"})
    broker_account = getattr(orchestrator, "broker_account", None)
    component_health = _runtime_component_health(orchestrator)
    primary_blocker = _enum_text(getattr(operational, "primary_blocker", None))
    return DashboardRuntimeView(
        application_status=_enum_text(lifecycle_snapshot.status),
        broker_mode=_enum_text(orchestrator.broker_mode),
        safety_mode=_enum_text(orchestrator.safety_mode),
        configured_instruments=tuple(_enum_text(instrument) for instrument in orchestrator.configured_instruments),
        market_data_ready=orchestrator.shared_market_data_ready,
        trade_journal_ready=canonical_journal_ready,
        start_count=lifecycle_snapshot.start_count,
        stop_count=lifecycle_snapshot.stop_count,
        restart_count=lifecycle_snapshot.restart_count,
        last_started_at=lifecycle_snapshot.last_started_at,
        last_stopped_at=lifecycle_snapshot.last_stopped_at,
        last_error=lifecycle_snapshot.last_error,
        validation_mode=_enum_text(getattr(validation, "mode", None)),
        validation_state=_enum_text(getattr(validation, "lifecycle_state", None)),
        validation_health=_enum_text(getattr(validation, "overall_health", None)),
        validation_findings=len(tuple(getattr(validation, "active_findings", ()) or ())),
        validation_reconnects=getattr(getattr(validation, "reconnect_summary", None), "reconnect_count", 0),
        validation_p95_latency_ms=p95,
        validation_broker_order_calls=getattr(getattr(validation, "counters", None), "broker_order_calls", 0),
        replay_state=_enum_text(getattr(replay, "lifecycle_state", None)),
        replay_mode=_enum_text(getattr(replay, "mode", None)),
        replay_session_id=_enum_text(getattr(replay, "session_id", None)),
        replay_source=_source_name(getattr(replay, "source_path", None)),
        replay_instruments=tuple(_enum_text(instrument) for instrument in tuple(getattr(replay, "instruments", ()) or ())),
        replay_trading_date=getattr(replay, "trading_date", None),
        replay_sequence=getattr(replay, "current_sequence", None),
        replay_published_records=getattr(replay, "published_records", 0),
        replay_total_records=getattr(replay, "total_records", 0),
        replay_progress_percentage=getattr(replay, "progress_percentage", 0.0),
        replay_speed_multiplier=getattr(replay, "speed_multiplier", 0.0),
        replay_current_timestamp=getattr(replay, "current_event_timestamp", None),
        replay_outcome=_enum_text(getattr(replay, "final_outcome", None)),
        replay_findings=len(tuple(getattr(replay, "active_findings", ()) or ())),
        replay_failure_summary=getattr(replay, "failure_reason", None),
        broker_account_broker=_enum_text(getattr(broker_account, "broker", None)),
        broker_account_id=_enum_text(getattr(broker_account, "account_id_masked", None)),
        broker_authentication=_enum_text(getattr(broker_account, "authentication_state", None)),
        broker_connection=_enum_text(getattr(broker_account, "connection_state", None)),
        broker_last_refresh=getattr(broker_account, "latest_refresh_timestamp", None),
        broker_data_age_seconds=getattr(broker_account, "data_age", None),
        broker_available_margin=getattr(broker_account, "total_available_margin", None),
        broker_used_margin=(getattr(broker_account, "equity_used", 0.0) or 0.0) + (getattr(broker_account, "commodity_used", 0.0) or 0.0),
        broker_open_positions=len(tuple(getattr(broker_account, "positions", ()) or ())),
        broker_holdings_count=len(tuple(getattr(broker_account, "holdings", ()) or ())),
        broker_orders_count=len(tuple(getattr(broker_account, "orders", ()) or ())),
        broker_blocking_reason=_enum_text(getattr(broker_account, "blocking_reason", None)),
        broker_mutation_mode=_enum_text(getattr(broker_account, "mutation_mode", None)),
        broker_session_token_valid=bool(getattr(getattr(orchestrator, "broker_session", None), "token_valid", False)),
        broker_session_expires_at=getattr(getattr(orchestrator, "broker_session", None), "expires_at", None),
        broker_session_last_refresh=getattr(getattr(orchestrator, "broker_session", None), "last_refresh", None),
        broker_session_connection=_enum_text(getattr(getattr(orchestrator, "broker_session", None), "connection_state", None)),
        market_session_state=_enum_text(getattr(getattr(operational, "session", None), "status", None)),
        analysis_readiness=_enum_text(getattr(operational, "overall_state", None)),
        vision_readiness="READY" if bool(getattr(operational, "vision_evaluation_ready", False)) else "WAITING_FOR_DATA",
        paper_readiness="READY" if bool(getattr(operational, "paper_trading_ready", False)) else "NOT_APPLICABLE",
        journal_persistence_status=_enum_text(getattr(journal_persistence, "operational_state", None)),
        broker_read_only_sync="READY" if _broker_account_ready(broker_account) else "AUTH_REQUIRED",
        primary_blocker=primary_blocker,
        component_health=component_health,
        runtime_health_summary=_runtime_health_summary(
            component_health,
            application_status=_enum_text(lifecycle_snapshot.status),
            primary_blocker=primary_blocker,
            runtime_snapshots=runtime_snapshots,
        ),
    )


def _broker_account_ready(account) -> bool:
    if account is None or bool(getattr(account, "is_stale", False)):
        return False
    authenticated = _plain_text(getattr(account, "authentication_state", None)).casefold() == "authenticated"
    connected = _plain_text(getattr(account, "connection_state", None)).casefold() == "ready"
    return authenticated and connected and getattr(account, "latest_refresh_timestamp", None) is not None


def _runtime_component_health(orchestrator) -> tuple[DashboardRuntimeComponentHealthView, ...]:
    snapshots = tuple(getattr(orchestrator, "runtime_snapshots", ()) or ())

    def any_snapshot(field_name: str) -> bool:
        return any(getattr(snapshot, field_name, None) is not None for snapshot in snapshots)

    def ready_row(name: str, ready: bool, detail: str = "-") -> DashboardRuntimeComponentHealthView:
        return DashboardRuntimeComponentHealthView(
            name=name,
            status="Ready" if ready else "Waiting",
            detail=detail,
        )

    return (
        _runtime_contract_health_row(snapshots),
        ready_row("Candle", any_snapshot("latest_candle")),
        ready_row("Market Data", bool(getattr(orchestrator, "shared_market_data_ready", False))),
        ready_row("CPR", any_snapshot("cpr")),
        ready_row("Camarilla", any_snapshot("camarilla")),
        _vwap_health_row(snapshots),
        _adr_health_row(snapshots),
        ready_row("Price Action", any_snapshot("price_action")),
        _option_chain_health_row(snapshots),
        ready_row("TradingView Evidence", any_snapshot("tradingview_evidence")),
        ready_row("Fusion", any_snapshot("multi_timeframe_evidence")),
        ready_row("Market State", any_snapshot("market_state")),
        ready_row("Expert Setup", any_snapshot("setup_classification")),
        ready_row("Chart Explanation", any_snapshot("chart_explanation")),
        ready_row("AI Reasoning", any_snapshot("ai_reasoning_v2") or any_snapshot("ai_reasoning")),
        ready_row("Strategy", any_snapshot("strategy_decision_v2") or any_snapshot("strategy")),
        ready_row("Risk", any_snapshot("risk_management_v2") or any_snapshot("risk")),
        _lifecycle_health_row(snapshots),
        _journal_health_row(snapshots),
        *_broker_account_health_rows(orchestrator),
        _broker_session_health_row(orchestrator),
        _replay_health_row(orchestrator),
        *_runtime_verification_health_rows(snapshots),
        _journal_health_row(snapshots),
        *_vision_runtime_health_rows(snapshots),
        *_runtime_diagnostic_rows(snapshots),
    )


def _broker_account_health_rows(orchestrator) -> tuple[DashboardRuntimeComponentHealthView, ...]:
    rows = []
    for stage in tuple(getattr(orchestrator, "broker_account_verification_report", ()) or ()):
        age = getattr(stage, "data_age", None)
        age_text = "-" if age is None else f"{age:.0f}s"
        detail = " | ".join(
            (
                f"Owner={_plain_text(getattr(stage, 'owner', None))}",
                f"Producer={_plain_text(getattr(stage, 'producer', None))}",
                f"Consumer={_plain_text(getattr(stage, 'consumer', None))}",
                f"Timestamp={_enum_text(getattr(stage, 'timestamp', None))}",
                f"DataAge={age_text}",
                f"Recovery={_enum_text(getattr(stage, 'recovery_state', None))}",
                f"Reason={_enum_text(getattr(stage, 'blocking_reason', None))}",
            )
        )
        rows.append(
            DashboardRuntimeComponentHealthView(
                _plain_text(getattr(stage, "stage", "Broker Account")),
                _enum_text(getattr(stage, "status", None)),
                detail,
                owner=_plain_text(getattr(stage, "owner", None)),
                producer=_plain_text(getattr(stage, "producer", None)),
                consumer=_plain_text(getattr(stage, "consumer", None)),
                timestamp=getattr(stage, "timestamp", None),
            )
        )
    return tuple(rows)


def _broker_session_health_row(orchestrator) -> DashboardRuntimeComponentHealthView:
    session = getattr(orchestrator, "broker_session", None)
    token_valid = bool(getattr(session, "token_valid", False))
    status = "READY" if token_valid else "LOGIN_REQUIRED"
    detail = " | ".join(
        (
            f"Authenticated={bool(getattr(session, 'authenticated', False))}",
            f"TokenValid={token_valid}",
            f"Expires={_enum_text(getattr(session, 'expires_at', None))}",
            f"Connection={_enum_text(getattr(session, 'connection_state', None))}",
            f"LastRefresh={_enum_text(getattr(session, 'last_refresh', None))}",
            f"Reason={_enum_text(getattr(session, 'blocking_reason', None))}",
        )
    )
    return DashboardRuntimeComponentHealthView(
        "Broker Session",
        status,
        detail,
        owner="ApplicationOrchestrator",
        producer="BrokerSessionStore",
        consumer="Broker Runtime",
        timestamp=getattr(session, "last_refresh", None),
    )


_RUNTIME_FAILURE_STATUSES = {"FAILED", "ERROR"}
_RUNTIME_DEGRADED_STATUSES = {"DEGRADED", "PARTIAL", "STALE", "RECOVERY_PENDING"}
_RUNTIME_EXPECTED_OPERATIONAL_STATUSES = {
    "AUTH_REQUIRED",
    "DISABLED",
    "LOGIN_REQUIRED",
    "MARKET_CLOSED",
    "NO_ACTIONABLE_CANDIDATE",
    "NOT_APPLICABLE",
    "READY_EMPTY",
    "WAITING",
    "WAITING_FOR_DATA",
    "WAITING_FOR_OPTION_TICKS",
    "WAITING_FOR_TICK",
}
_RUNTIME_FAILURE_PRIORITY = (
    "Runtime Contract",
    "Runtime Integrity",
    "Market Data",
    "Candle",
    "Runtime Session",
    "CPR",
    "Camarilla",
    "ADR",
    "VWAP",
    "Vision Daily Context",
    "Vision Opening Range",
    "Vision Structure",
    "Vision Liquidity",
    "Vision Structure Events",
    "Vision Setup Qualification",
    "Vision Option Confirmation",
    "Vision Method Calculator",
    "Vision Validation",
    "Vision Runtime Adapter",
    "TradeCandidate",
    "Risk",
    "Lifecycle",
    "Paper Position",
    "Vision Paper Handoff",
    "Journal",
)


def _runtime_health_summary(
    rows: tuple[DashboardRuntimeComponentHealthView, ...],
    *,
    application_status: str,
    primary_blocker: str,
    runtime_snapshots: tuple[RuntimeSnapshot, ...],
) -> DashboardRuntimeHealthSummary:
    failures = tuple(row for row in rows if _status_key(row.status) in _RUNTIME_FAILURE_STATUSES)
    failures = tuple(sorted(failures, key=_runtime_failure_rank))
    degraded = tuple(row for row in rows if _is_runtime_degraded(row))
    updated_at = _runtime_health_updated_at(failures, rows, runtime_snapshots)
    blocker = _runtime_blocker_text(primary_blocker)
    app_status = _status_key(application_status)
    if failures:
        primary = failures[0]
        reason = _runtime_failure_reason(failures)
        return DashboardRuntimeHealthSummary(
            "FAILED",
            primary_failure=primary.name if len(failures) == 1 else "Multiple",
            failure_reason=reason,
            blocking=True,
            failed_component_count=len(failures),
            degraded_component_count=len(degraded),
            updated_at=updated_at,
            tooltip=_runtime_summary_tooltip(
                "Multiple" if len(failures) > 1 else primary.name,
                "FAILED",
                reason,
                updated_at,
                True,
            ),
            failed_components=failures,
        )
    if app_status not in {"RUNNING", "READY", "CREATED"}:
        reason = f"Application status is {application_status}."
        return DashboardRuntimeHealthSummary(
            "DEGRADED",
            primary_failure="Application",
            failure_reason=reason,
            blocking=True,
            degraded_component_count=len(degraded) + 1,
            updated_at=updated_at,
            tooltip=_runtime_summary_tooltip("Application", "DEGRADED", reason, updated_at, True),
        )
    if blocker != "none":
        return DashboardRuntimeHealthSummary(
            "DEGRADED",
            primary_failure="Primary Blocker",
            failure_reason=blocker,
            blocking=True,
            degraded_component_count=len(degraded) + 1,
            updated_at=updated_at,
            tooltip=_runtime_summary_tooltip("Primary Blocker", "DEGRADED", blocker, updated_at, True),
        )
    if degraded:
        primary = degraded[0]
        reason = _runtime_failure_reason(degraded)
        return DashboardRuntimeHealthSummary(
            "DEGRADED",
            primary_failure=primary.name if len(degraded) == 1 else "Multiple",
            failure_reason=reason,
            blocking=False,
            degraded_component_count=len(degraded),
            updated_at=updated_at,
            tooltip=_runtime_summary_tooltip(
                "Multiple" if len(degraded) > 1 else primary.name,
                "DEGRADED",
                reason,
                updated_at,
                False,
            ),
        )
    return DashboardRuntimeHealthSummary(
        "READY",
        updated_at=updated_at,
        tooltip=_runtime_summary_tooltip("Runtime", "READY", "None", updated_at, False),
    )


def _status_key(value) -> str:
    return "_".join(part for part in str(value or "-").strip().upper().replace("-", "_").split() if part)


def _is_runtime_degraded(row: DashboardRuntimeComponentHealthView) -> bool:
    status = _status_key(row.status)
    if status in _RUNTIME_DEGRADED_STATUSES:
        return True
    if status in _RUNTIME_EXPECTED_OPERATIONAL_STATUSES:
        return False
    if status == "BLOCKED":
        detail = str(row.detail).strip().casefold()
        return not (
            detail.startswith("no actionable")
            or detail.startswith("no strategy")
            or detail.startswith("no candidate")
            or "no actionable vision candidate" in detail
        )
    return False


def _runtime_failure_rank(row: DashboardRuntimeComponentHealthView) -> tuple[int, str]:
    name = str(row.name)
    for index, prefix in enumerate(_RUNTIME_FAILURE_PRIORITY):
        if name == prefix or name.endswith(f" {prefix}") or name.startswith(prefix):
            return (index, name)
    return (len(_RUNTIME_FAILURE_PRIORITY), name)


def _runtime_failure_reason(rows: tuple[DashboardRuntimeComponentHealthView, ...]) -> str:
    if len(rows) == 1:
        return rows[0].detail if rows[0].detail != "-" else rows[0].status
    return "\n".join(f"{index}. {row.name}: {row.detail}" for index, row in enumerate(rows, start=1))


def _runtime_health_updated_at(
    prioritized_rows: tuple[DashboardRuntimeComponentHealthView, ...],
    all_rows: tuple[DashboardRuntimeComponentHealthView, ...],
    runtime_snapshots: tuple[RuntimeSnapshot, ...],
):
    for row in prioritized_rows + all_rows:
        if row.timestamp is not None:
            return row.timestamp
    return next((getattr(snapshot, "timestamp", None) for snapshot in runtime_snapshots if getattr(snapshot, "timestamp", None) is not None), None)


def _runtime_blocker_text(primary_blocker: str) -> str:
    value = str(primary_blocker or "-").strip()
    return "none" if value in {"", "-", "none", "None", "NONE"} else value


def _runtime_summary_tooltip(component: str, status: str, reason: str, updated_at, blocking: bool) -> str:
    return "\n".join(
        (
            f"Component: {component}",
            f"Status: {status}",
            f"Reason: {reason if reason and reason != '-' else 'None'}",
            f"Updated: {_enum_text(updated_at)}",
            f"Blocking: {'Yes' if blocking else 'No'}",
        )
    )


def _runtime_contract_health_row(snapshots) -> DashboardRuntimeComponentHealthView:
    reports = tuple(getattr(snapshot, "runtime_contract_report", None) for snapshot in snapshots)
    report = next((item for item in reports if item is not None), None)
    if report is None:
        return DashboardRuntimeComponentHealthView(
            "Runtime Contract",
            "WAITING_FOR_DATA",
            "Runtime contract report unavailable.",
            owner="SymbolRuntime",
            producer="RuntimeContractValidator",
            consumer="Dashboard",
        )
    violations = tuple(getattr(report, "violations", ()) or ())
    if not violations:
        return DashboardRuntimeComponentHealthView(
            "Runtime Contract",
            "READY",
            "Runtime contract valid.",
            owner=getattr(report, "owner", "SymbolRuntime"),
            producer=getattr(report, "producer", "RuntimeContractValidator"),
            consumer=getattr(report, "consumer", "Dashboard"),
            timestamp=getattr(report, "checked_at", None),
        )
    first = violations[0]
    detail = (
        "Runtime Contract Failed | "
        f"Reason={_plain_text(getattr(first, 'reason', None))} | "
        f"Owner={_plain_text(getattr(first, 'owner', None))} | "
        f"Producer={_plain_text(getattr(first, 'producer', None))} | "
        f"Consumer={_plain_text(getattr(first, 'consumer', None))} | "
        f"Object={_plain_text(getattr(first, 'object_name', None))} | "
        f"Expected={_plain_text(getattr(first, 'expected', None))} | "
        f"Actual={_plain_text(getattr(first, 'actual', None))}"
    )
    return DashboardRuntimeComponentHealthView(
        "Runtime Contract",
        "FAILED",
        detail,
        owner=_plain_text(getattr(first, "owner", None)),
        producer=_plain_text(getattr(first, "producer", None)),
        consumer=_plain_text(getattr(first, "consumer", None)),
        timestamp=getattr(report, "checked_at", None),
    )


def _adr_health_detail(snapshots) -> str:
    diagnostics = next((getattr(snapshot, "adr_diagnostics", None) for snapshot in snapshots if getattr(snapshot, "adr_diagnostics", None) is not None), None)
    if diagnostics is None:
        return "-"
    if getattr(diagnostics, "last_snapshot", None) is not None:
        return "AVAILABLE"
    error = getattr(diagnostics, "last_error", None)
    period = getattr(diagnostics, "period", None)
    if error:
        return f"WAITING_HISTORY: {error}"
    return f"WAITING_HISTORY: required={period}" if period else "WAITING_HISTORY"


def _adr_health_row(snapshots) -> DashboardRuntimeComponentHealthView:
    status = next((getattr(snapshot, "adr_runtime", None) for snapshot in snapshots if getattr(snapshot, "adr_runtime", None) is not None), None)
    if status is None:
        if any(getattr(snapshot, "adr", None) is not None for snapshot in snapshots):
            return DashboardRuntimeComponentHealthView("ADR", "Ready", "AVAILABLE")
        return DashboardRuntimeComponentHealthView("ADR", "WAITING_FOR_DATA", "ADR runtime status unavailable.")
    detail = (
        f"{status.blocking_reason} | "
        f"Loaded={status.valid_sessions}/{status.required_sessions} | "
        f"LatestHistory={_enum_text(status.latest_history_date)} | "
        f"Recovery={status.recovery_condition}"
    )
    return DashboardRuntimeComponentHealthView(
        "ADR",
        status.state,
        detail,
        owner=status.owner,
        producer=status.producer,
        consumer=status.consumer,
    )


def _vwap_health_row(snapshots) -> DashboardRuntimeComponentHealthView:
    source = next((getattr(snapshot, "vwap_source", None) for snapshot in snapshots if getattr(snapshot, "vwap_source", None) is not None), None)
    if source is None:
        return DashboardRuntimeComponentHealthView("VWAP", "WAITING_FOR_DATA", "VWAP source status unavailable.")
    if source.ready:
        state = "READY"
        detail = f"{source.message} | Source={source.source_type} | Volume={source.cumulative_volume}"
    else:
        state = "WAITING_FOR_DATA" if source.state in {"Unavailable", "-"} else source.state.upper()
        detail = source.message or source.unavailable_reason or "VWAP source unavailable."
    return DashboardRuntimeComponentHealthView("VWAP", state, detail, owner="SymbolRuntime", producer="VWAPEngine", consumer="Vision Level Context")


def _option_chain_health_row(snapshots) -> DashboardRuntimeComponentHealthView:
    status = next((getattr(snapshot, "option_chain_runtime", None) for snapshot in snapshots if getattr(snapshot, "option_chain_runtime", None) is not None), None)
    if status is None:
        return DashboardRuntimeComponentHealthView("Option Chain", "DISABLED", "Live option-chain runtime is not configured.")
    detail = f"{status.blocking_reason} | Snapshot={status.snapshot_status} | Analytics={status.analytics_status} | Recovery={status.recovery_condition}"
    return DashboardRuntimeComponentHealthView("Option Chain", status.state, detail, owner="SymbolRuntime", producer="OptionChainRuntime", consumer="Vision Option Confirmation", timestamp=status.last_update)


def _journal_health_row(snapshots) -> DashboardRuntimeComponentHealthView:
    persistence = next((getattr(snapshot, "journal_persistence", None) for snapshot in snapshots if getattr(snapshot, "journal_persistence", None) is not None), None)
    if persistence is None:
        return DashboardRuntimeComponentHealthView("Journal", "WAITING_FOR_DATA", "TradeJournalV1 persistence status unavailable.")
    return DashboardRuntimeComponentHealthView("Journal", persistence.operational_state, persistence.operational_message, owner="SymbolRuntime", producer="TradeJournalV1", consumer="Dashboard", timestamp=persistence.journal_write_timestamp)


def _lifecycle_health_row(snapshots) -> DashboardRuntimeComponentHealthView:
    stage = next((stage for snapshot in snapshots for stage in tuple(getattr(snapshot, "runtime_verification_report", ()) or ()) if getattr(stage, "stage", None) == "Lifecycle"), None)
    if stage is None:
        return DashboardRuntimeComponentHealthView("Lifecycle", "Ready" if snapshots else "NOT_APPLICABLE", "Lifecycle snapshot available." if snapshots else "Lifecycle has not been invoked.")
    return DashboardRuntimeComponentHealthView("Lifecycle", _enum_text(getattr(stage, "status", None)), _verification_detail(stage), owner=stage.owner, producer=stage.producer, consumer=stage.consumer, timestamp=stage.timestamp)


def _replay_health_row(orchestrator) -> DashboardRuntimeComponentHealthView:
    replay = getattr(orchestrator, "historical_replay", None)
    state = _enum_text(getattr(replay, "lifecycle_state", None))
    mode = _enum_text(getattr(replay, "mode", None))
    if mode in {"Off", "OFF", "-"}:
        status = "DISABLED"
        detail = "Historical replay is disabled by configuration."
    elif state in {"Idle", "IDLE"}:
        status = "NOT_APPLICABLE"
        detail = "No replay session is running."
    else:
        status = state.upper()
        detail = f"Mode={mode}"
    return DashboardRuntimeComponentHealthView("Replay", status, detail, owner="ApplicationOrchestrator", producer="HistoricalMarketReplayEngine", consumer="Dashboard")


def _vision_runtime_health_rows(snapshots) -> tuple[DashboardRuntimeComponentHealthView, ...]:
    if any(tuple(getattr(snapshot, "runtime_verification_report", ()) or ()) for snapshot in snapshots):
        return ()
    rows = []
    for snapshot in snapshots:
        prefix = _enum_text(getattr(snapshot, "symbol", None))
        diagnostics = getattr(snapshot, "runtime_diagnostics", None)
        reason = _vision_health_detail("-", diagnostics)
        candidate = getattr(snapshot, "vision_trade_candidate", None)
        candidate_ready = candidate is not None
        rows.extend((
            _health_row(f"{prefix} Vision Daily Context", getattr(snapshot, "cpr", None) is not None and getattr(snapshot, "camarilla", None) is not None, reason),
            _health_row(f"{prefix} Vision Level Context", candidate_ready, reason),
            _health_row(f"{prefix} Vision Opening Range", candidate_ready, reason),
            _health_row(f"{prefix} Vision Structure", candidate_ready, reason),
            _health_row(f"{prefix} Vision Liquidity", candidate_ready, reason),
            _health_row(f"{prefix} Vision Structure Events", candidate_ready, reason),
            _health_row(f"{prefix} Vision Setup Qualification", candidate_ready, reason),
            _health_row(f"{prefix} Vision Option Confirmation", candidate_ready, reason),
            _health_row(f"{prefix} Vision Method Calculator", candidate_ready, reason),
            _health_row(f"{prefix} Vision Validation", diagnostics is not None and diagnostics.last_validation != "-", getattr(diagnostics, "last_validation", "-")),
            _health_row(f"{prefix} Vision Runtime Adapter", candidate_ready, getattr(getattr(candidate, "candidate_state", None), "value", "-")),
            _health_row(f"{prefix} Strategy Gate", getattr(snapshot, "strategy_decision_v2", None) is not None, "no actionable Vision candidate" if getattr(snapshot, "strategy_decision_v2", None) is None else "ready"),
            _health_row(f"{prefix} Risk Gate", getattr(snapshot, "risk_management_v2", None) is not None, "no strategy decision" if getattr(snapshot, "strategy_decision_v2", None) is None else "ready"),
        ))
    return tuple(rows)


def _runtime_verification_health_rows(snapshots) -> tuple[DashboardRuntimeComponentHealthView, ...]:
    rows = []
    for snapshot in snapshots:
        for stage in tuple(getattr(snapshot, "runtime_verification_report", ()) or ()):
            timestamp = getattr(stage, "timestamp", None)
            rows.append(
                DashboardRuntimeComponentHealthView(
                    _verification_health_name(getattr(stage, "stage", "-")),
                    _enum_text(getattr(stage, "status", None)),
                    _verification_detail(stage),
                    owner=_plain_text(getattr(stage, "owner", None)),
                    producer=_plain_text(getattr(stage, "producer", None)),
                    consumer=_plain_text(getattr(stage, "consumer", None)),
                    timestamp=timestamp,
                )
            )
    return tuple(rows)


def _verification_health_name(stage: str) -> str:
    normalized = str(stage).strip()
    mapping = {
        "Reference Data": "Reference Data",
        "Daily Context": "Vision Daily Context",
        "Opening Range": "Vision Opening Range",
        "Structure": "Vision Structure",
        "Liquidity": "Vision Liquidity",
        "Structure Events": "Vision Structure Events",
        "Setup Qualification": "Vision Setup Qualification",
        "Option Confirmation": "Vision Option Confirmation",
        "Vision Method": "Vision Method Calculator",
        "Validation": "Vision Validation",
        "Runtime Adapter": "Vision Runtime Adapter",
        "TradeCandidate": "TradeCandidate",
        "Paper Position": "Paper Position",
        "Paper Trade": "Vision Paper Handoff",
        "AI Explanation": "AI Explanation",
    }
    return mapping.get(normalized, normalized)


def _verification_detail(stage) -> str:
    session = getattr(stage, "session", None)
    session_date = getattr(session, "trading_date", None)
    reason = getattr(stage, "blocking_reason", "-")
    latency = getattr(stage, "latency_ms", None)
    latency_text = "-" if latency is None else f"{latency:.0f}ms"
    prerequisites = tuple(getattr(stage, "prerequisites", ()) or ())
    readiness = tuple(getattr(stage, "readiness_conditions", ()) or ())
    blocking = tuple(getattr(stage, "blocking_conditions", ()) or ())
    parts = (
        f"Owner={_plain_text(getattr(stage, 'owner', None))}",
        f"Producer={_plain_text(getattr(stage, 'producer', None))}",
        f"Consumer={_plain_text(getattr(stage, 'consumer', None))}",
        f"Dependency={', '.join(prerequisites) if prerequisites else '-'}",
        f"Expected={'; '.join(readiness) if readiness else '-'}",
        f"Actual={_enum_text(getattr(stage, 'status', None))}",
        f"Timestamp={_enum_text(getattr(stage, 'timestamp', None))}",
        f"Session={_enum_text(session_date)}",
        f"Latency={latency_text}",
        f"Recovery={_enum_text(getattr(stage, 'recovery_state', None))}",
        f"Reason={_enum_text(reason)}",
        f"Suggested Action={'; '.join(blocking) if blocking else '-'}",
    )
    return " | ".join(parts)


def _vision_health_detail(reason: str, diagnostics) -> str:
    if reason and reason != "-":
        return reason
    if diagnostics is None:
        return "-"
    blocking_stage = getattr(diagnostics, "blocking_stage", "-")
    current_stage = getattr(diagnostics, "current_stage", "-")
    if blocking_stage and blocking_stage != "-":
        return blocking_stage
    return current_stage if current_stage else "-"


def _health_row(name: str, ready: bool, detail: str) -> DashboardRuntimeComponentHealthView:
    status = "READY" if ready else "WAITING"
    detail_text = str(detail) if detail else "-"
    lowered = detail_text.lower()
    if lowered.startswith("no "):
        status = "BLOCKED" if "candidate" in str(detail).lower() else "NOT_APPLICABLE"
    elif "failed" in lowered or "error" in lowered:
        status = "FAILED"
    elif "unavailable" in lowered or "missing" in lowered or "insufficient" in lowered:
        status = "DEGRADED"
    return DashboardRuntimeComponentHealthView(name, status, detail_text)


def _runtime_diagnostic_rows(snapshots) -> tuple[DashboardRuntimeComponentHealthView, ...]:
    rows = []
    for snapshot in snapshots:
        diagnostics = getattr(snapshot, "runtime_diagnostics", None)
        if diagnostics is None:
            continue
        prefix = _enum_text(getattr(snapshot, "symbol", None))
        rows.extend(
            (
                DashboardRuntimeComponentHealthView(f"{prefix} Base Timeframe", "Ready", getattr(snapshot, "base_timeframe", "-")),
                DashboardRuntimeComponentHealthView(f"{prefix} Vision Decision Timeframe", "Ready", getattr(snapshot, "vision_decision_timeframe", "-")),
                DashboardRuntimeComponentHealthView(f"{prefix} Confirmation Timeframe", "Ready", getattr(snapshot, "confirmation_timeframe", None) or "unavailable"),
                DashboardRuntimeComponentHealthView(f"{prefix} Current Stage", "Ready", diagnostics.current_stage),
                DashboardRuntimeComponentHealthView(f"{prefix} Blocking Stage", "Ready", diagnostics.blocking_stage),
                DashboardRuntimeComponentHealthView(f"{prefix} Current Candidate", "Ready", diagnostics.current_candidate),
                DashboardRuntimeComponentHealthView(f"{prefix} Paper Trade State", "Ready", diagnostics.paper_trade_state),
                DashboardRuntimeComponentHealthView(f"{prefix} Journal State", "Ready", diagnostics.journal_state),
                DashboardRuntimeComponentHealthView(f"{prefix} Last Snapshot", "Ready", diagnostics.last_successful_snapshot),
                DashboardRuntimeComponentHealthView(f"{prefix} Last Validation", "Ready", diagnostics.last_validation),
            )
        )
        counters = getattr(snapshot, "vision_forensic_counters", None)
        if counters is not None:
            rows.extend(
                (
                    DashboardRuntimeComponentHealthView(f"{prefix} 5m Candles Evaluated", "Ready", str(counters.candles_evaluated)),
                    DashboardRuntimeComponentHealthView(f"{prefix} Qualified Setups", "Ready", str(counters.qualified_setups)),
                    DashboardRuntimeComponentHealthView(f"{prefix} Prepare Long", "Ready", str(counters.prepare_long)),
                    DashboardRuntimeComponentHealthView(f"{prefix} Prepare Short", "Ready", str(counters.prepare_short)),
                    DashboardRuntimeComponentHealthView(f"{prefix} Long Eligible", "Ready", str(counters.long_eligible)),
                    DashboardRuntimeComponentHealthView(f"{prefix} Short Eligible", "Ready", str(counters.short_eligible)),
                    DashboardRuntimeComponentHealthView(f"{prefix} Trade Candidates Created", "Ready", str(counters.trade_candidates_created)),
                    DashboardRuntimeComponentHealthView(f"{prefix} Risk Approved", "Ready", str(counters.risk_approved)),
                    DashboardRuntimeComponentHealthView(f"{prefix} Risk Rejected", "Ready", str(counters.risk_rejected)),
                    DashboardRuntimeComponentHealthView(f"{prefix} Paper Positions Opened", "Ready", str(counters.paper_positions_opened)),
                    DashboardRuntimeComponentHealthView(f"{prefix} Paper Positions Closed", "Ready", str(counters.paper_positions_closed)),
                )
            )
        journal = getattr(snapshot, "trade_journal_v1", None)
        journal_analytics = getattr(journal, "analytics", None)
        journal_overall = getattr(journal_analytics, "overall", None)
        canonical_position = getattr(snapshot, "canonical_paper_position", None)
        rows.extend(
            (
                DashboardRuntimeComponentHealthView(
                    f"{prefix} Current Session Realized P&L",
                    "Ready",
                    str(getattr(journal_overall, "net_pnl", 0.0) if journal_overall is not None else 0.0),
                ),
                DashboardRuntimeComponentHealthView(
                    f"{prefix} Current Session Unrealized P&L",
                    "Ready",
                    str(getattr(canonical_position, "unrealized_pnl", 0.0) if canonical_position is not None else 0.0),
                ),
            )
        )
    return tuple(rows)


def build_market_view(runtime_snapshot: RuntimeSnapshot, *, clock=None) -> DashboardMarketView:
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
        vwap_historical_seed_complete=bool(getattr(vwap_source, "historical_seed_complete", False)),
        vwap_bootstrap_time=getattr(vwap_source, "bootstrap_time", None),
        vwap_live_tick_count=getattr(vwap_source, "live_tick_count", 0) if vwap_source is not None else 0,
        vwap_last_live_volume=getattr(vwap_source, "last_live_volume", 0) if vwap_source is not None else 0,
        vwap_last_delta_volume=getattr(vwap_source, "last_delta_volume", 0) if vwap_source is not None else 0,
        vwap_last_live_tick=getattr(vwap_source, "last_live_tick", None),
        vwap_current_accumulated_volume=getattr(vwap_source, "current_accumulated_volume", 0) if vwap_source is not None else 0,
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
        live_tick_at=getattr(runtime_snapshot, "latest_tick_at", None) or getattr(tick, "timestamp", None),
        closed_candle_at=getattr(runtime_snapshot, "latest_closed_candle_at", None),
        analysis_updated_at=getattr(runtime_snapshot, "latest_analysis_at", None),
        snapshot_created_at=getattr(runtime_snapshot, "snapshot_created_at", None),
        dashboard_rendered_at=_safe_clock_now(clock),
        feed_delay_text=_feed_delay_text(getattr(runtime_snapshot, "latest_tick_at", None) or getattr(tick, "timestamp", None), clock),
        analysis_basis=f"Analysis based on latest closed {runtime_snapshot.timeframe} candle",
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
    canonical_status=None,
) -> DashboardOptionChainView:
    state = runtime_snapshot.option_chain
    symbol = _enum_text(runtime_snapshot.symbol)
    if state is None:
        return _apply_option_runtime_status(
            unavailable_option_chain_view(symbol),
            runtime_status,
            all_option_statuses=all_option_statuses,
            clock=clock,
            canonical_status=getattr(runtime_snapshot, "option_chain_runtime", None),
        )
    if _enum_text(state.symbol) != symbol:
        return _apply_option_runtime_status(
            unavailable_option_chain_view(symbol),
            runtime_status,
            all_option_statuses=all_option_statuses,
            clock=clock,
            canonical_status=getattr(runtime_snapshot, "option_chain_runtime", None),
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
    ), runtime_status, all_option_statuses=all_option_statuses, clock=clock, canonical_status=getattr(runtime_snapshot, "option_chain_runtime", None))


def build_ai_view(runtime_snapshot: RuntimeSnapshot) -> DashboardAIView:
    candidate = getattr(runtime_snapshot, "vision_trade_candidate", None)
    generation_id = _snapshot_generation_id(runtime_snapshot)
    snapshot_created_at = getattr(runtime_snapshot, "snapshot_created_at", None) or getattr(runtime_snapshot, "updated_at", None)
    runtime_market_timestamp = _runtime_market_timestamp(runtime_snapshot)
    vision_decision_timestamp = _vision_decision_timestamp(runtime_snapshot)
    if candidate is not None:
        audit = getattr(runtime_snapshot, "decision_audit", None)
        return DashboardAIView(
            symbol=_enum_text(runtime_snapshot.symbol),
            market_summary=f"Vision Method: {_enum_text(candidate.candidate_state)}",
            confidence=str(getattr(candidate, "confidence", MISSING)),
            agreement="Vision Method",
            conflict=getattr(audit, "reason", MISSING) if getattr(audit, "rejected", False) else "None",
            trading_suitability=_enum_text(candidate.candidate_state),
            explanation=getattr(runtime_snapshot, "vision_ai_explanation", None) or getattr(candidate, "reason", MISSING),
            missing_information=(getattr(audit, "reason", MISSING),) if getattr(audit, "rejected", False) else (),
            snapshot_generation_id=generation_id,
            snapshot_created_at=snapshot_created_at,
            runtime_market_timestamp=runtime_market_timestamp,
            vision_decision_timestamp=vision_decision_timestamp,
        )
    ai = runtime_snapshot.ai_reasoning_v2 or runtime_snapshot.ai_reasoning
    return DashboardAIView(
        symbol=_enum_text(runtime_snapshot.symbol),
        market_summary=_ai_market_summary(ai),
        confidence=_ai_confidence(ai),
        agreement="LEGACY_DIAGNOSTIC" if ai is not None else _ai_agreement(ai),
        conflict=_ai_conflict(ai),
        trading_suitability=_ai_suitability(ai),
        explanation=_ai_explanation(ai),
        missing_information=_ai_missing_information(ai),
        snapshot_generation_id=generation_id,
        snapshot_created_at=snapshot_created_at,
        runtime_market_timestamp=runtime_market_timestamp,
        vision_decision_timestamp=vision_decision_timestamp,
    )


def _ai_market_summary(ai) -> str:
    return _enum_text(getattr(ai, "market_summary", None) or getattr(ai, "summary", None))


def _ai_confidence(ai) -> str:
    conviction = getattr(ai, "conviction", None)
    if conviction is not None:
        return _enum_text(conviction)
    return _enum_text(getattr(ai, "confidence", None))


def _ai_agreement(ai) -> str:
    legacy = getattr(ai, "agreement_summary", None)
    if legacy is not None:
        return _enum_text(legacy)
    fusion = getattr(ai, "multi_timeframe_evidence", None)
    return _enum_text(getattr(fusion, "evidence_agreement", None))


def _ai_conflict(ai) -> str:
    legacy = getattr(ai, "conflict_summary", None)
    if legacy is not None:
        return _enum_text(legacy)
    fusion = getattr(ai, "multi_timeframe_evidence", None)
    return _enum_text(getattr(fusion, "evidence_conflict", None))


def _ai_suitability(ai) -> str:
    suitability = getattr(ai, "trading_suitability", None)
    if suitability is not None:
        return _enum_text(suitability)
    return _enum_text(getattr(ai, "reasoning_state", None))


def _ai_explanation(ai) -> str:
    return (
        getattr(ai, "explanation", None)
        or getattr(ai, "primary_thesis", None)
        or getattr(ai, "summary", None)
        or MISSING
    )


def _ai_missing_information(ai) -> tuple[str, ...]:
    missing = getattr(ai, "missing_information", None)
    if missing is not None:
        return tuple(missing or ())
    cautions = tuple(getattr(ai, "cautions", ()) or ())
    return tuple(getattr(item, "message", str(item)) for item in cautions)


def _strategy_reference_text(strategy, kind: str) -> str:
    if kind == "entry":
        legacy = getattr(strategy, "entry_reference", None)
        if legacy is not None:
            return _enum_text(legacy)
        reference = getattr(strategy, "primary_reference", None)
    elif kind == "stop":
        legacy = getattr(strategy, "stop_reference", None)
        if legacy is not None:
            return _enum_text(legacy)
        reference = getattr(strategy, "invalidation_reference", None)
    else:
        legacy = getattr(strategy, "target_reference", None)
        if legacy is not None:
            return _enum_text(legacy)
        objectives = tuple(getattr(strategy, "objectives", ()) or ())
        reference = getattr(objectives[0], "reference", None) if objectives else None
    label = getattr(reference, "label", None)
    return _enum_text(label or getattr(reference, "reference_type", None))


def _strategy_block_reason(strategy) -> str:
    legacy = getattr(strategy, "block_reason", None)
    if legacy is not None:
        return _enum_text(legacy)
    warnings = tuple(getattr(strategy, "warnings", ()) or ())
    if warnings:
        return str(warnings[0])
    rationale = tuple(getattr(strategy, "rationale", ()) or ())
    if getattr(strategy, "eligible", None) is False and rationale:
        return str(rationale[0])
    return MISSING


def _risk_reason(risk) -> str:
    if risk is None:
        return MISSING
    warnings = tuple(getattr(risk, "warnings", ()) or ())
    if warnings:
        return str(warnings[0])
    failed = next(
        (
            item
            for item in tuple(getattr(risk, "rule_evaluations", ()) or ())
            if _enum_text(getattr(item, "result", None)) == "Failed"
        ),
        None,
    )
    if failed is not None:
        return str(getattr(failed, "message", MISSING))
    rationale = tuple(getattr(risk, "rationale", ()) or ())
    return str(rationale[0]) if rationale else MISSING


def build_strategy_view(runtime_snapshot: RuntimeSnapshot) -> DashboardStrategyView:
    candidate = getattr(runtime_snapshot, "vision_trade_candidate", None)
    canonical_position = getattr(runtime_snapshot, "canonical_paper_position", None)
    strategy = runtime_snapshot.strategy_decision_v2 or runtime_snapshot.strategy
    risk = runtime_snapshot.risk_management_v2 or runtime_snapshot.risk
    order = runtime_snapshot.latest_order
    recovered_note = "-"
    if candidate is None and canonical_position is not None and getattr(canonical_position, "recovery_status", "") == "RESTORED":
        recovered_note = f"Recovered position; original live StrategyDecision is unavailable. Checkpoint reference: {getattr(canonical_position, 'candidate_reference', '-')}"
    return DashboardStrategyView(
        symbol=_enum_text(runtime_snapshot.symbol),
        decision=_enum_text(getattr(strategy, "decision", None) or getattr(strategy, "action", None)),
        direction=_enum_text(getattr(strategy, "direction", None)),
        setup_quality=_enum_text(getattr(strategy, "setup_quality", None) or getattr(strategy, "quality", None)),
        entry_reference=_strategy_reference_text(strategy, "entry"),
        stop_reference=_strategy_reference_text(strategy, "stop"),
        target_reference=_strategy_reference_text(strategy, "target"),
        block_reason=_strategy_block_reason(strategy),
        risk_decision=_enum_text(getattr(risk, "decision", None)),
        approved_quantity=getattr(risk, "approved_quantity", None),
        risk_amount=getattr(risk, "estimated_risk_amount", None) or getattr(risk, "approved_risk_amount", None),
        reward_risk=getattr(risk, "reward_risk_ratio", None),
        entry_price=getattr(risk, "entry_price", None),
        stop_price=getattr(risk, "stop_price", None) or getattr(risk, "invalidation_price", None),
        target_price=getattr(risk, "target_price", None) or getattr(risk, "objective_price", None),
        lot_size=getattr(risk, "lot_size", None),
        approved_lots=getattr(risk, "approved_lots", None),
        plan_status=getattr(risk, "plan_status", None) or _enum_text(getattr(risk, "status", None)),
        plan_valid_until=getattr(risk, "valid_until", None),
        risk_reason=getattr(risk, "risk_reason", None) or _risk_reason(risk),
        latest_order_status="Trade Plan Ready" if bool(getattr(risk, "trade_plan_ready", False)) else _enum_text(getattr(order, "status", None)),
        candidate_state=_enum_text(getattr(candidate, "candidate_state", None)),
        candidate_direction=_enum_text(getattr(candidate, "direction", None)),
        candidate_quality=_enum_text(getattr(candidate, "confidence", None)),
        candidate_validation=_enum_text(getattr(getattr(runtime_snapshot, "vision_method_validation_report", None), "validation_result", None)),
        candidate_reference=getattr(candidate, "snapshot_reference", None) or getattr(canonical_position, "vision_method_snapshot_reference", "-"),
        candidate_reason=getattr(candidate, "reason", None) or getattr(canonical_position, "blocking_reason", "-"),
        candidate_source="VISION_METHOD" if candidate is not None or canonical_position is not None else "-",
        strategy_source=getattr(strategy, "trade_source", None) or ("LEGACY_DIAGNOSTIC" if runtime_snapshot.strategy is not None else "-"),
        recovered_position_note=recovered_note,
        snapshot_generation_id=_snapshot_generation_id(runtime_snapshot),
        snapshot_created_at=getattr(runtime_snapshot, "snapshot_created_at", None) or getattr(runtime_snapshot, "updated_at", None),
        runtime_market_timestamp=_runtime_market_timestamp(runtime_snapshot),
        vision_decision_timestamp=_vision_decision_timestamp(runtime_snapshot),
    )


def build_position_view(runtime_snapshot: RuntimeSnapshot) -> DashboardPositionView:
    canonical = getattr(runtime_snapshot, "canonical_paper_position", None)
    if canonical is not None:
        has_position = str(getattr(canonical, "status", "")).lower() in {"open", "partially_closed", "objective_reached"}
        source = getattr(canonical, "source", "-")
        is_option_paper = source == "VISION_METHOD_OPTION_SELLING_PAPER"
        return DashboardPositionView(
            symbol=_enum_text(runtime_snapshot.symbol),
            status=(
                "Paper Option Position Open"
                if has_position and is_option_paper
                else "Paper Option Position Closed"
                if is_option_paper
                else "Vision Paper Position Open"
                if has_position
                else "Vision Paper Position Closed"
            ),
            has_position=has_position,
            side=_enum_text(getattr(canonical, "direction", None)),
            quantity=getattr(canonical, "quantity", None),
            average_price=getattr(canonical, "entry_price", None),
            last_price=getattr(canonical, "current_price", None),
            unrealized_pnl=getattr(canonical, "unrealized_pnl", None),
            realized_pnl=getattr(canonical, "realized_pnl", None),
            stop_price=getattr(canonical, "stop_price", None),
            target_price=getattr(canonical, "target_price", None),
            entry_price=getattr(canonical, "entry_price", None),
            plan_id=_short_id(getattr(canonical, "candidate_reference", None)),
            opened_at=getattr(canonical, "entry_timestamp", None),
            closed_at=None if has_position else getattr(canonical, "updated_at", None),
            exit_type=_enum_text(getattr(canonical, "status", None)),
            trade_source=source,
            trade_id=getattr(canonical, "trade_id", None),
            candidate_state=getattr(canonical, "candidate_state", "-"),
            risk_state=getattr(canonical, "risk_state", "-"),
            lifecycle_state=getattr(canonical, "lifecycle_state", "-"),
            blocking_reason=getattr(canonical, "blocking_reason", "-"),
            recovery_status=getattr(canonical, "recovery_status", "-"),
            gross_pnl=getattr(canonical, "gross_pnl", None),
            fees=getattr(canonical, "fees", None),
            slippage=getattr(canonical, "slippage", None),
            net_pnl=getattr(canonical, "net_pnl", None),
        )
    position = runtime_snapshot.position
    tick = runtime_snapshot.latest_tick
    paper = runtime_snapshot.paper_trading
    paper_order = getattr(paper, "order", None)
    paper_position = getattr(paper, "position", None)
    latest_record = getattr(getattr(paper, "journal_summary", None), "latest_record", None)
    if paper_order is not None and getattr(paper_order, "state", None).value == "pending":
        return DashboardPositionView(
            symbol=_enum_text(runtime_snapshot.symbol),
            status="Pending Paper Entry",
            has_position=False,
            side=_enum_text(getattr(paper_order, "direction", None)),
            quantity=getattr(paper_order, "quantity", None),
            average_price=None,
            last_price=getattr(tick, "last_price", None),
            unrealized_pnl=None,
            realized_pnl=None,
            stop_price=getattr(paper_order, "stop_price", None),
            target_price=getattr(paper_order, "target_price", None),
            entry_price=getattr(paper_order, "entry_price", None),
            valid_until=getattr(paper_order, "valid_until", None),
            plan_id=_short_id(getattr(paper_order, "plan_id", None)),
        )
    if paper_position is not None:
        return DashboardPositionView(
            symbol=_enum_text(runtime_snapshot.symbol),
            status="Paper Position Open",
            has_position=True,
            side=_enum_text(getattr(paper_position, "direction", None)),
            quantity=getattr(paper_position, "quantity", None),
            average_price=getattr(paper_position, "entry_price", None),
            last_price=getattr(paper_position, "last_price", None),
            unrealized_pnl=getattr(paper_position, "unrealized_pnl", None),
            realized_pnl=None,
            stop_price=getattr(paper_position, "stop_price", None),
            target_price=getattr(paper_position, "target_price", None),
            entry_price=getattr(paper_position, "entry_price", None),
            plan_id=_short_id(getattr(paper_position, "plan_id", None)),
            opened_at=getattr(paper_position, "opened_at", None),
            mfe=getattr(paper_position, "maximum_favourable_excursion", None),
            mae=getattr(paper_position, "maximum_adverse_excursion", None),
        )
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
        realized_pnl=getattr(latest_record, "net_pnl", None) if latest_record is not None and not has_position else getattr(position, "realized_pnl", None),
        stop_price=getattr(runtime_snapshot.risk, "stop_price", None),
        target_price=getattr(runtime_snapshot.risk, "target_price", None),
        closed_at=getattr(latest_record, "exit_time", None),
        exit_type=_enum_text(getattr(latest_record, "exit_type", None)),
        mfe=getattr(latest_record, "maximum_favourable_excursion", None),
        mae=getattr(latest_record, "maximum_adverse_excursion", None),
    )


def build_journal_view(runtime_snapshot: RuntimeSnapshot) -> DashboardJournalView:
    persistence = getattr(runtime_snapshot, "journal_persistence", None)
    v1 = getattr(runtime_snapshot, "trade_journal_v1", None)
    v1_entry = getattr(v1, "latest_entry", None)
    legacy_paper_record = getattr(getattr(runtime_snapshot.paper_trading, "journal_summary", None), "latest_record", None)
    if v1 is not None and v1_entry is None and legacy_paper_record is None:
        return DashboardJournalView(
            symbol=_enum_text(runtime_snapshot.symbol),
            status=getattr(persistence, "operational_state", "READY_EMPTY"),
            records=getattr(v1, "trade_count", 0),
            message=getattr(persistence, "operational_message", "Ready - No completed Vision paper trades"),
            latest_trade_id=None,
            latest_trade_source="VISION_METHOD",
            persistence_status=getattr(persistence, "persistence_status", "-"),
            active_checkpoint_status=getattr(persistence, "active_checkpoint_status", "-"),
            recovery_status=getattr(persistence, "recovery_status", "-"),
            recovery_reason=getattr(persistence, "recovery_reason", "-"),
            journal_blocking_reason=getattr(persistence, "journal_blocking_reason", "-"),
            latest_exit_type="-",
            latest_realized_pnl=None,
            latest_opened_at=None,
            latest_closed_at=None,
        )
    if v1_entry is not None:
        return DashboardJournalView(
            symbol=_enum_text(runtime_snapshot.symbol),
            status="Ready",
            records=getattr(getattr(runtime_snapshot, "trade_journal_v1", None), "trade_count", 1),
            message=getattr(persistence, "operational_message", "Latest completed Vision paper trade"),
            latest_trade_id=getattr(v1_entry, "trade_id", None),
            latest_trade_source=getattr(v1_entry, "trade_source", "-"),
            persistence_status=getattr(persistence, "persistence_status", "-"),
            active_checkpoint_status=getattr(persistence, "active_checkpoint_status", "-"),
            recovery_status=getattr(persistence, "recovery_status", "-"),
            recovery_reason=getattr(persistence, "recovery_reason", "-"),
            journal_blocking_reason=getattr(persistence, "journal_blocking_reason", "-"),
            latest_exit_type=_enum_text(getattr(v1_entry, "exit_reason", None)),
            latest_realized_pnl=getattr(v1_entry, "realized_pnl", None),
            latest_opened_at=getattr(v1_entry, "opened_at", None),
            latest_closed_at=getattr(v1_entry, "closed_at", None),
            latest_instrument=_enum_text(getattr(v1_entry, "instrument", None)),
            latest_side=_enum_text(getattr(v1_entry, "direction", None)),
            latest_quantity=getattr(v1_entry, "closed_quantity", None),
            latest_entry_price=getattr(v1_entry, "entry_price", None),
            latest_exit_price=getattr(v1_entry, "average_exit_price", None),
            latest_holding_seconds=int(getattr(v1_entry, "duration_seconds", 0)),
            daily_pnl=getattr(
                getattr(getattr(getattr(runtime_snapshot, "trade_journal_v1", None), "analytics", None), "overall", None),
                "net_pnl",
                None,
            ),
        )
    paper_summary = getattr(getattr(runtime_snapshot, "paper_trading", None), "journal_summary", None)
    if paper_summary is not None:
        record = paper_summary.latest_record
        return DashboardJournalView(
            symbol=_enum_text(runtime_snapshot.symbol),
            status="Ready",
            records=paper_summary.record_count,
            message="Latest completed DRY_RUN trade" if record is not None else "No completed DRY_RUN trades",
            latest_trade_id=getattr(record, "trade_id", None),
            latest_trade_source="-",
            persistence_status=getattr(persistence, "persistence_status", "-"),
            active_checkpoint_status=getattr(persistence, "active_checkpoint_status", "-"),
            recovery_status=getattr(persistence, "recovery_status", "-"),
            recovery_reason=getattr(persistence, "recovery_reason", "-"),
            journal_blocking_reason=getattr(persistence, "journal_blocking_reason", "-"),
            latest_exit_type=_enum_text(getattr(record, "exit_type", None)),
            latest_realized_pnl=getattr(record, "net_pnl", None),
            latest_opened_at=getattr(record, "entry_time", None),
            latest_closed_at=getattr(record, "exit_time", None),
            latest_instrument=getattr(record, "instrument", "-") if record is not None else "-",
            latest_side=_enum_text(getattr(record, "direction", None)),
            latest_quantity=getattr(record, "quantity", None),
            latest_entry_price=getattr(record, "entry_price", None),
            latest_exit_price=getattr(record, "exit_price", None),
            latest_holding_seconds=getattr(record, "holding_seconds", None),
            latest_mfe=getattr(record, "maximum_favourable_excursion", None),
            latest_mae=getattr(record, "maximum_adverse_excursion", None),
            daily_pnl=paper_summary.daily_realized_pnl,
            wins=paper_summary.winning_trades,
            losses=paper_summary.losing_trades,
            win_rate=paper_summary.win_rate,
            profit_factor=paper_summary.profit_factor,
        )
    record = runtime_snapshot.latest_journal_record
    has_record = record is not None
    return DashboardJournalView(
        symbol=_enum_text(runtime_snapshot.symbol),
        status="Ready",
        records=1 if has_record else 0,
        message="Latest completed DRY_RUN trade" if has_record else "No completed DRY_RUN trades",
        latest_trade_id=getattr(record, "trade_id", None),
        latest_trade_source="-",
        latest_exit_type=_enum_text(getattr(record, "exit_type", None)),
        latest_realized_pnl=getattr(record, "realized_gross_pnl", None),
        latest_opened_at=getattr(record, "opened_at", None),
        latest_closed_at=getattr(record, "closed_at", None),
    )


def build_analytics_view(runtime_snapshot: RuntimeSnapshot) -> DashboardAnalyticsView:
    snapshot = getattr(runtime_snapshot, "performance_analytics", None)
    symbol = _enum_text(runtime_snapshot.symbol)
    if snapshot is None:
        return DashboardAnalyticsView(
            symbol=symbol,
            status="Disabled",
            selected_instrument=symbol,
            total_trades=0,
            net_pnl=0.0,
            daily_pnl=0.0,
            weekly_pnl=0.0,
            monthly_pnl=0.0,
            win_rate=None,
            loss_rate=None,
            profit_factor=None,
            expectancy=None,
            average_r=None,
            maximum_drawdown=0.0,
            current_streak="-",
            maximum_consecutive_wins=0,
            maximum_consecutive_losses=0,
            average_holding_seconds=None,
            best_setup="-",
            weakest_setup="-",
            last_error=None,
        )
    summary = snapshot.selected_instrument
    daily = snapshot.daily_performance[-1].summary.net_profit if snapshot.daily_performance else 0.0
    weekly = snapshot.weekly_performance[-1].summary.net_profit if snapshot.weekly_performance else 0.0
    monthly = snapshot.monthly_performance[-1].summary.net_profit if snapshot.monthly_performance else 0.0
    best_setup, weakest_setup = _setup_extremes(snapshot.setup_statistics)
    status = "Error" if snapshot.diagnostics.last_error else "Ready"
    return DashboardAnalyticsView(
        symbol=symbol,
        status=status,
        selected_instrument=symbol,
        total_trades=summary.record_count,
        net_pnl=summary.net_profit,
        daily_pnl=daily,
        weekly_pnl=weekly,
        monthly_pnl=monthly,
        win_rate=summary.win_rate,
        loss_rate=summary.loss_rate,
        profit_factor=summary.profit_factor,
        expectancy=summary.expectancy,
        average_r=summary.average_r,
        maximum_drawdown=summary.maximum_drawdown,
        current_streak=_current_streak(summary),
        maximum_consecutive_wins=summary.maximum_consecutive_wins,
        maximum_consecutive_losses=summary.maximum_consecutive_losses,
        average_holding_seconds=summary.average_holding_seconds,
        best_setup=best_setup,
        weakest_setup=weakest_setup,
        last_error=snapshot.diagnostics.last_error,
        metric_cards=(
            DashboardAnalyticsMetricView("Total Trades", formatters.integer(summary.record_count)),
            DashboardAnalyticsMetricView("Net P&L", formatters.price(summary.net_profit), formatters.pnl_kind(summary.net_profit)),
            DashboardAnalyticsMetricView("Daily P&L", formatters.price(daily), formatters.pnl_kind(daily)),
            DashboardAnalyticsMetricView("Weekly P&L", formatters.price(weekly), formatters.pnl_kind(weekly)),
            DashboardAnalyticsMetricView("Monthly P&L", formatters.price(monthly), formatters.pnl_kind(monthly)),
            DashboardAnalyticsMetricView("Win Rate", formatters.ratio(summary.win_rate)),
            DashboardAnalyticsMetricView("Profit Factor", formatters.ratio(summary.profit_factor)),
            DashboardAnalyticsMetricView("Max Drawdown", formatters.price(summary.maximum_drawdown), "warning" if summary.maximum_drawdown else "neutral"),
        ),
        recent_trades=tuple(
            DashboardAnalyticsRowView(
                (
                    record.trade_id,
                    record.instrument,
                    _enum_text(record.direction),
                    formatters.price(record.net_pnl),
                    formatters.timestamp(record.exit_time),
                )
            )
            for record in snapshot.latest_records[:10]
        ),
        equity_curve=tuple(
            DashboardAnalyticsRowView((str(point.sequence), point.trade_id, formatters.price(point.cumulative_pnl), formatters.price(point.drawdown)))
            for point in snapshot.equity_curve[-20:]
        ),
        period_performance=tuple(
            DashboardAnalyticsRowView((item.label, formatters.integer(item.summary.record_count), formatters.price(item.summary.net_profit), formatters.ratio(item.summary.win_rate)))
            for item in snapshot.daily_performance[-10:]
        ),
        setup_statistics=tuple(
            DashboardAnalyticsRowView((item.group_key, formatters.integer(item.summary.record_count), formatters.price(item.summary.net_profit), formatters.ratio(item.summary.win_rate)))
            for item in snapshot.setup_statistics
        ),
        time_of_day_statistics=tuple(
            DashboardAnalyticsRowView((item.group_key, formatters.integer(item.summary.record_count), formatters.price(item.summary.net_profit), formatters.ratio(item.summary.win_rate)))
            for item in snapshot.time_of_day_statistics
        ),
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


def _plain_text(value) -> str:
    if value is None:
        return MISSING
    raw = getattr(value, "value", value)
    text = str(raw).strip()
    return text or MISSING


def _safe_error(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return value.__class__.__name__
    return value


def _short_id(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    return normalized if len(normalized) <= 18 else f"{normalized[:8]}...{normalized[-6:]}"


def _source_name(value) -> str:
    if value is None:
        return MISSING
    name = getattr(value, "name", value)
    return _enum_text(name)


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
    canonical_status=None,
) -> DashboardOptionChainView:
    rows = _option_runtime_rows(all_option_statuses, clock=clock)
    events = _option_event_rows(all_option_statuses)
    if status is None:
        return DashboardOptionChainView(
            **{
                **_option_view_values(view),
                "runtime_rows": rows,
                "event_rows": events,
                **_canonical_option_runtime_values(canonical_status),
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
        **_canonical_option_runtime_values(canonical_status),
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



def _canonical_option_runtime_values(status) -> dict[str, object]:
    if status is None:
        return {}
    return {
        "runtime_snapshot_status": _enum_text(getattr(status, "snapshot_status", None)),
        "runtime_analytics_status": _enum_text(getattr(status, "analytics_status", None)),
        "snapshot_age_seconds": getattr(status, "age_seconds", None),
        "runtime_latency_ms": getattr(status, "latency_ms", None),
        "runtime_synchronization_status": str(getattr(status, "synchronization_status", None) or "-"),
        "runtime_blocking_reason": _enum_text(getattr(status, "blocking_reason", None)),
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


def _safe_clock_now(clock) -> datetime | None:
    if clock is None:
        return None
    try:
        return _clock_now(clock)
    except Exception:
        return None


def _feed_delay_text(timestamp, clock) -> str:
    now = _safe_clock_now(clock)
    if timestamp is None or now is None:
        return MISSING
    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return MISSING
    delay_ms = max(0.0, (now - timestamp.astimezone(IST)).total_seconds() * 1000.0)
    if delay_ms < 1000.0:
        return f"{delay_ms:.0f} ms"
    return f"{delay_ms / 1000.0:.1f} s"


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
    session = DEFAULT_EXCHANGE_CALENDAR.resolve_active_session(now, "NSE")
    if session.phase is ExchangeSessionPhase.NON_TRADING_DAY:
        next_open = _session_open_for(session.next_trading_date)
        status = "NSE closed - weekend" if "weekend" in session.reason.lower() else "NSE closed - non-trading day"
        return status, "Closed", _next_open_text(next_open, include_day=True)
    if session.phase is ExchangeSessionPhase.CLOSED:
        return "Waiting for NSE to open", "Closed", _next_open_text(session.session_open)
    if session.phase is ExchangeSessionPhase.PRE_MARKET:
        return "NSE pre-open", "Pre-Open", _next_open_text(session.session_open)
    if session.phase is ExchangeSessionPhase.OPEN:
        return "NSE market open", "Live", MISSING
    next_open = _session_open_for(session.next_trading_date)
    return "NSE closed for the day", "Closed", _next_open_text(next_open, include_day=next_open.date() != now.date())


def _next_open(now: datetime) -> datetime:
    session = DEFAULT_EXCHANGE_CALENDAR.resolve_active_session(now, "NSE")
    if session.session_open is not None and session.phase in {ExchangeSessionPhase.CLOSED, ExchangeSessionPhase.PRE_MARKET}:
        return session.session_open
    return _session_open_for(session.next_trading_date)


def _session_open_for(trading_date) -> datetime:
    return datetime.combine(trading_date, MARKET_OPEN_TIME, tzinfo=IST)


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


def _current_streak(summary) -> str:
    if summary.consecutive_wins:
        return f"{summary.consecutive_wins} Wins"
    if summary.consecutive_losses:
        return f"{summary.consecutive_losses} Losses"
    return "-"


def _setup_extremes(items) -> tuple[str, str]:
    populated = tuple(item for item in items if item.summary.record_count)
    if not populated:
        return "-", "-"
    best = max(populated, key=lambda item: item.summary.net_profit)
    weakest = min(populated, key=lambda item: item.summary.net_profit)
    return best.group_key, weakest.group_key
