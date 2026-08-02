from datetime import UTC, date, datetime, timedelta

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.event_bus import EventBus
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from dashboard.presenters import build_journal_view, build_runtime_view, build_strategy_view
from tests.test_dashboard_presenters import lifecycle
from tests.test_live_option_chain_runtime_gate_c import _analytics, _snapshot
from tests.test_vision_method_validation_v1 import snapshot as method_snapshot
from tests.test_vision_paper_trading_integration_v1 import process
from engines.vision_method import VisionCandidateState
from dataclasses import replace

NOW = datetime(2026, 7, 29, 10, 30, tzinfo=UTC)


def runtime(adr_period=20):
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,), adr_period=adr_period, option_expiry_date=date(2026, 7, 30)),
        RuntimeInstrument.NIFTY,
    )
    item.start()
    item._last_tick = Tick(Instrument.NIFTY, Exchange.NSE, NOW, 100.0, 100, 99.9, 100.1, 0)
    return item


def daily(day, base=100.0):
    return DailyOHLC(day, base, base + 10.0, base - 10.0, base + 2.0)


def candle(index, volume=100):
    start = NOW.replace(hour=9, minute=15) + timedelta(minutes=index)
    return Candle("NIFTY", "1m", start, start + timedelta(minutes=1), 100.0, 101.0, 99.0, 100.5, volume)


def test_rc4_empty_trade_journal_v1_is_ready_empty_and_dashboard_agrees():
    item = runtime()
    snap = item.snapshot()

    assert snap.journal_persistence.operational_state == "READY_EMPTY"
    assert snap.journal_persistence.operational_message == "Ready - No completed Vision paper trades"
    assert build_journal_view(snap).status == "READY_EMPTY"
    view = build_runtime_view(lifecycle(snap))
    assert view.trade_journal_ready is True
    rows = {row.name: row for row in view.component_health}
    assert rows["Journal"].status == "READY_EMPTY"


def test_rc4_adr_reports_loaded_required_counts_until_warmup_complete():
    item = runtime(adr_period=20)
    for offset in reversed(range(8)):
        item.process_daily_ohlc(daily(NOW.date() - timedelta(days=offset + 1)))

    status = item.snapshot().adr_runtime
    assert status.state == "INSUFFICIENT_HISTORY"
    assert status.valid_sessions == 8
    assert status.required_sessions == 20
    assert "8/20" in status.blocking_reason


def test_rc4_sufficient_daily_history_creates_adr_runtime_ready():
    item = runtime(adr_period=20)
    for offset in reversed(range(20)):
        item.process_daily_ohlc(daily(NOW.date() - timedelta(days=offset + 1), 100.0 + offset))

    snap = item.snapshot()
    assert snap.adr is not None
    assert snap.adr_runtime.state == "READY"


def test_rc4_vwap_reports_unavailable_zero_volume_and_ready_positive_history():
    empty = runtime()
    assert empty.snapshot().vwap_source.ready is False
    empty.warm_up_candles((candle(1, volume=0),))
    assert empty.snapshot().vwap_source.ready is False

    seeded = runtime()
    seeded.warm_up_candles((candle(1, volume=100),))
    assert seeded.snapshot().vwap_source.ready is True
    rows = {row.name: row for row in build_runtime_view(lifecycle(seeded.snapshot())).component_health}
    assert rows["VWAP"].status == "READY"


def test_rc4_option_chain_states_distinguish_waiting_and_ready():
    item = runtime()
    waiting = item.snapshot().option_chain_runtime
    assert waiting.state == "WAITING_FOR_OPTION_TICKS"
    assert waiting.recovery_condition

    option_snapshot = _snapshot(NOW)
    analytics = _analytics(option_snapshot)
    ready = item.process_option_chain_runtime(option_snapshot, analytics)
    assert ready.option_chain_runtime.state == "READY"


def test_rc4_non_actionable_candidate_marks_risk_lifecycle_not_applicable():
    item = runtime()
    process(item, replace(method_snapshot(), candidate_state=VisionCandidateState.WAIT))
    rows = {stage.stage: stage for stage in item.snapshot().runtime_verification_report}

    assert rows["TradeCandidate"].status == "NO_ACTIONABLE_CANDIDATE"
    assert rows["Risk"].status == "NOT_APPLICABLE"
    assert rows["Lifecycle"].status == "NOT_APPLICABLE"


def test_rc4_strategy_panel_shows_vision_candidate_without_strategy_decision():
    item = runtime()
    process(item, replace(method_snapshot(), candidate_state=VisionCandidateState.WAIT))
    view = build_strategy_view(item.snapshot())

    assert view.candidate_source == "VISION_METHOD"
    assert view.candidate_state != "-"
    assert view.decision == "-"
    assert "No trade candidate" in view.candidate_reason or view.candidate_reason != "-"
