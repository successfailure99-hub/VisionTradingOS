from datetime import timedelta

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from core.event_bus import EventBus
from core.models.daily_ohlc import DailyOHLC
from dashboard.presenters import build_runtime_view
from tests.test_dashboard_presenters import lifecycle
from tests.test_vision_method_validation_v1 import NOW, snapshot
from tests.test_vision_paper_trading_integration_v1 import process, tick


REQUIRED_VM16_STAGES = {
    "Application Startup",
    "Market Data",
    "Reference Data",
    "Daily Context",
    "Opening Range",
    "Structure",
    "Liquidity",
    "Structure Events",
    "Setup Qualification",
    "Option Confirmation",
    "Vision Method",
    "Validation",
    "Runtime Adapter",
    "TradeCandidate",
    "Risk",
    "Lifecycle",
    "Paper Position",
    "Journal",
    "AI Explanation",
}


def fresh_runtime() -> SymbolRuntime:
    item = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    item.start()
    return item


def warm_daily_context(item: SymbolRuntime, trading_day):
    previous_day = trading_day - timedelta(days=1)
    item.process_daily_ohlc(
        DailyOHLC(previous_day, 100.0, 110.0, 90.0, 105.0),
        levels_trading_date=trading_day,
    )


def test_vm16_live_session_runtime_report_covers_every_production_stage():
    item = fresh_runtime()
    trading_day = NOW.date()
    warm_daily_context(item, trading_day)
    item.process_tick(tick(timestamp=NOW.replace(hour=9, minute=15, second=0), price=100.0))
    item.process_tick(tick(timestamp=NOW.replace(hour=9, minute=31, second=0), price=103.0))
    candidate, report = process(item, snapshot())
    item._process_paper_tick(tick(103.5, timestamp=candidate.timestamp + timedelta(seconds=1)))

    view = item.snapshot()
    stages = {stage.stage: stage for stage in view.runtime_verification_report}

    assert REQUIRED_VM16_STAGES <= set(stages)
    assert stages["Application Startup"].status == "READY"
    assert stages["Reference Data"].status == "READY"
    assert stages["Daily Context"].session is view.runtime_session
    assert stages["Opening Range"].status == "READY"
    assert stages["Structure"].status == "READY"
    assert stages["Liquidity"].status == "READY"
    assert stages["Structure Events"].status == "READY"
    assert stages["Setup Qualification"].status == "READY"
    assert stages["Vision Method"].timestamp == view.vision_method_snapshot.timestamp
    assert stages["Validation"].timestamp == report.timestamp
    assert stages["TradeCandidate"].timestamp == candidate.timestamp
    assert stages["Risk"].status == "READY"
    assert stages["Lifecycle"].status == "READY"
    assert stages["Paper Position"].status == "READY"
    assert stages["AI Explanation"].status == "READY"
    for stage in stages.values():
        assert stage.owner
        assert stage.producer
        assert stage.consumer
        assert stage.session is view.runtime_session
        assert stage.recovery_state in {"NO_POSITION", "RESTORED", "CHECKPOINT_ACTIVE"}
        assert stage.latency_ms is None or stage.latency_ms >= 0.0


def test_vm16_market_open_waits_for_daily_context_before_ready():
    item = fresh_runtime()
    market_open = NOW.replace(hour=9, minute=15, second=0)
    item.process_tick(tick(timestamp=market_open, price=100.0))

    waiting_view = item.snapshot()
    waiting_stages = {stage.stage: stage for stage in waiting_view.runtime_verification_report}

    assert waiting_view.runtime_session.status == "WAITING_DAILY_CONTEXT"
    assert waiting_stages["Reference Data"].status == "BLOCKED"
    assert waiting_stages["Daily Context"].blocking_reason.startswith("Missing daily context")

    warm_daily_context(item, market_open.date())
    ready_view = item.snapshot()
    ready_stages = {stage.stage: stage for stage in ready_view.runtime_verification_report}

    assert ready_view.runtime_session.status == "READY"
    assert ready_stages["Reference Data"].status == "READY"
    assert ready_stages["Daily Context"].status == "READY"
    assert ready_view.runtime_session.cpr_trading_date == market_open.date()
    assert ready_view.runtime_session.camarilla_trading_date == market_open.date()


def test_vm16_session_rollover_refreshes_daily_context_and_avoids_stale_levels():
    item = fresh_runtime()
    day_one = NOW.date()
    day_two = day_one + timedelta(days=1)
    warm_daily_context(item, day_one)
    item.process_tick(tick(timestamp=NOW.replace(hour=15, minute=30, second=0), price=101.0))

    next_day_open = NOW.replace(day=NOW.day + 1, hour=9, minute=15, second=0)
    item.process_tick(tick(timestamp=next_day_open, price=102.0))
    ready_view = item.snapshot()
    rollover_stages = {stage.stage: stage for stage in ready_view.runtime_verification_report}

    assert ready_view.runtime_session.status == "READY"
    assert rollover_stages["Daily Context"].status == "READY"
    assert "Stale daily context" not in rollover_stages["Daily Context"].blocking_reason
    assert ready_view.runtime_session.trading_date == day_two
    assert ready_view.runtime_session.cpr_trading_date == day_two
    assert ready_view.runtime_session.camarilla_trading_date == day_two


def test_vm16_dashboard_runtime_health_uses_verification_report_only_for_stage_details():
    item = fresh_runtime()
    warm_daily_context(item, NOW.date())
    item.process_tick(tick(timestamp=NOW, price=100.0))
    process(item, snapshot())

    runtime_view = build_runtime_view(lifecycle(item.snapshot()))
    rows = {row.name: row for row in runtime_view.component_health}

    for name in (
        "Reference Data",
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
        "Paper Position",
        "AI Explanation",
    ):
        assert name in rows
        assert "Owner=" in rows[name].detail
        assert "Producer=" in rows[name].detail
        assert "Consumer=" in rows[name].detail
        assert "Latency=" in rows[name].detail
        assert "Recovery=" in rows[name].detail


def test_vm16_reconnect_recovery_does_not_duplicate_candidates_positions_or_journal():
    item = fresh_runtime()
    warm_daily_context(item, NOW.date())
    item.process_tick(tick(timestamp=NOW, price=100.0))
    method_snapshot = snapshot()
    process(item, method_snapshot)
    opened = item.snapshot()
    objective = opened.risk_management_v2.objective_price
    close_tick = tick(objective + 0.5, timestamp=opened.trade_lifecycle_v1.timestamp + timedelta(seconds=1))

    item._process_paper_tick(close_tick)
    first = item.snapshot()
    item.process_tick(tick(timestamp=NOW + timedelta(minutes=1), price=100.0))
    process(item, method_snapshot)
    item._process_paper_tick(close_tick)
    recovered = item.snapshot()

    assert recovered.vision_trade_candidate == first.vision_trade_candidate
    assert recovered.trade_journal_v1.trade_count == 1
    assert recovered.canonical_paper_position.trade_id == first.canonical_paper_position.trade_id
    assert recovered.runtime_diagnostics.journal_state == first.runtime_diagnostics.journal_state