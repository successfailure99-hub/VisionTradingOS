from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

import pytest

from application.bootstrap import ApplicationBootstrap
from application.enums import RuntimeInstrument
from application.models import RuntimeConfiguration
from core.event_bus import EventBus
from core.events import PAPER_TRADE_RECORDED
from dashboard.presenters import build_analytics_view
from engines.paper_trading.enums import PaperExitType
from engines.paper_trading.models import PaperTradeRecord
from engines.performance_analytics import (
    AnalyticsRecordStatus,
    PerformanceAnalyticsCalculator,
    PerformanceAnalyticsConfiguration,
    PerformanceAnalyticsEngine,
    PaperTradeJournalRepository,
    ReviewClassification,
)
from engines.strategy.enums import TradeDirection


IST = timezone(timedelta(hours=5, minutes=30))
BASE = datetime(2026, 7, 14, 9, 20, tzinfo=IST)


def record(
    trade_id: str,
    pnl: float,
    *,
    instrument: str = "NIFTY",
    direction=TradeDirection.BULLISH,
    exit_time: datetime | None = None,
    setup: str = "Breakout",
    entry_type: str = "Retest",
    r: float | None = None,
):
    entry = (exit_time or BASE) - timedelta(minutes=10)
    exit_at = exit_time or BASE
    return PaperTradeRecord(
        trade_id=trade_id,
        position_id=f"pos-{trade_id}",
        paper_order_id=f"ord-{trade_id}",
        plan_id=f"plan-{trade_id}",
        instrument=instrument,
        direction=direction,
        quantity=10,
        lot_size=10,
        entry_time=entry,
        entry_price=100.0,
        exit_time=exit_at,
        exit_price=110.0 if pnl >= 0 else 95.0,
        stop_price=90.0,
        target_price=120.0,
        exit_type=PaperExitType.TARGET if pnl > 0 else PaperExitType.STOP_LOSS if pnl < 0 else PaperExitType.SESSION_CLOSE,
        gross_pnl=pnl,
        fees=0.0,
        net_pnl=pnl,
        reward_risk_planned=2.0,
        reward_risk_realized=r,
        maximum_favourable_excursion=max(pnl, 0.0) + 25.0,
        maximum_adverse_excursion=max(-pnl, 0.0) + 10.0,
        holding_seconds=600,
        strategy_setup=setup,
        strategy_confidence="High",
        strategy_reasoning=("rule",),
        trading_date=exit_at.astimezone(IST).date(),
        entry_type=entry_type,
        timeframe="1m",
        ai_confidence=0.8,
        ai_decision="ALLOW",
        ai_reasoning_summary="Stored facts only",
        camarilla_relationship="H4 Break",
        cpr_relationship="Above CPR",
    )


def test_models_are_immutable_and_validate_numbers():
    snap = PerformanceAnalyticsCalculator().calculate((), PerformanceAnalyticsConfiguration(), generated_at=BASE)
    with pytest.raises(FrozenInstanceError):
        snap.overall.record_count = 1
    with pytest.raises(ValueError):
        PerformanceAnalyticsConfiguration(starting_equity=0)
    with pytest.raises(ValueError):
        PerformanceAnalyticsConfiguration(starting_equity=float("nan"))


def test_dataset_a_core_metrics_and_equity_curve():
    records = tuple(record(f"t{i}", pnl, r=r) for i, (pnl, r) in enumerate(((100, 1.0), (-50, -0.5), (200, 2.0), (-100, -1.0), (0, 0.0)), start=1))
    snap = PerformanceAnalyticsCalculator().calculate(records, PerformanceAnalyticsConfiguration(starting_equity=1000), generated_at=BASE)
    s = snap.selected_instrument
    assert s.record_count == 5
    assert s.winning_trades == 2
    assert s.losing_trades == 2
    assert s.breakeven_trades == 1
    assert s.win_rate == 40
    assert s.loss_rate == 40
    assert s.gross_profit == 300
    assert s.gross_loss == 150
    assert s.net_profit == 150
    assert s.average_trade == 30
    assert s.average_win == 150
    assert s.average_loss == -75
    assert s.profit_factor == 2
    assert s.maximum_consecutive_wins == 1
    assert s.maximum_consecutive_losses == 1
    assert tuple(point.cumulative_pnl for point in snap.equity_curve) == (100, 50, 250, 150, 150)
    assert max(point.drawdown for point in snap.equity_curve) == 100


def test_streak_drawdown_empty_all_wins_losses_and_breakeven():
    cfg = PerformanceAnalyticsConfiguration(starting_equity=1000)
    dataset_b = tuple(record(f"b{i}", pnl) for i, pnl in enumerate((-100, -50, 25, 25, 25, -10), start=1))
    s = PerformanceAnalyticsCalculator().calculate(dataset_b, cfg, generated_at=BASE).selected_instrument
    assert s.consecutive_losses == 1
    assert s.maximum_consecutive_wins == 3
    assert s.maximum_consecutive_losses == 2
    assert s.maximum_drawdown == 150
    assert s.current_drawdown == 85
    assert PerformanceAnalyticsCalculator().calculate((record("w", 10),), cfg, generated_at=BASE).selected_instrument.profit_factor is None
    assert PerformanceAnalyticsCalculator().calculate((record("l", -10),), cfg, generated_at=BASE).selected_instrument.profit_factor == 0
    empty = PerformanceAnalyticsCalculator().calculate((), cfg, generated_at=BASE).selected_instrument
    assert empty.record_count == 0
    assert empty.profit_factor is None
    flat = PerformanceAnalyticsCalculator().calculate((record("f", 0),), cfg, generated_at=BASE).selected_instrument
    assert flat.breakeven_trades == 1


def test_period_group_and_instrument_filtering():
    monday = datetime(2026, 12, 28, 9, 30, tzinfo=IST)
    records = (
        record("n", 100, instrument="NIFTY", exit_time=monday, setup="A", entry_type="Breakout"),
        record("b", -50, instrument="BANKNIFTY", direction=TradeDirection.BEARISH, exit_time=monday + timedelta(days=1), setup="B"),
        record("s", 25, instrument="SENSEX", exit_time=datetime(2027, 1, 2, 9, 30, tzinfo=IST), setup="A"),
    )
    snap = PerformanceAnalyticsCalculator().calculate(records, PerformanceAnalyticsConfiguration(), instrument="NIFTY", generated_at=BASE)
    assert snap.selected_instrument.record_count == 1
    assert {item.group_key for item in snap.instrument_statistics} == {"BANKNIFTY", "NIFTY", "SENSEX"}
    assert snap.weekly_performance[0].label == "2026-W53"
    assert snap.monthly_performance[0].label == "2026-12"
    assert any(item.group_key == "09:15-10:00" for item in snap.time_of_day_statistics)


def test_repository_persistence_duplicates_conflicts_and_corrupt_lines(tmp_path):
    path = tmp_path / "journal.jsonl"
    repo = PaperTradeJournalRepository(path=path)
    first = record("x", 100)
    assert repo.add(first).status is AnalyticsRecordStatus.ACCEPTED
    assert repo.add(first).status is AnalyticsRecordStatus.DUPLICATE
    assert repo.add(replace(first, net_pnl=101, gross_pnl=101)).status is AnalyticsRecordStatus.CONFLICT
    path.write_text(path.read_text(encoding="utf-8") + "{bad json}\n", encoding="utf-8")
    restarted = PaperTradeJournalRepository(path=path)
    assert restarted.load() == (first,)
    assert restarted.diagnostics.load_failures == 1
    assert restarted.records(instrument="NIFTY") == (first,)
    assert restarted.latest(1) == (first,)


def test_engine_event_ingestion_idempotent_reviews_replay_and_exports(tmp_path):
    bus = EventBus()
    engine = PerformanceAnalyticsEngine(
        configuration=PerformanceAnalyticsConfiguration(journal_path=tmp_path / "journal.jsonl", export_directory=tmp_path, starting_equity=1000),
        event_bus=bus,
        clock=lambda: BASE,
    )
    item = record("event", 100, r=1.0)
    bus.publish(PAPER_TRADE_RECORDED, item)
    bus.publish(PAPER_TRADE_RECORDED, item)
    snap = engine.snapshot()
    assert snap.overall.record_count == 1
    assert snap.diagnostics.accepted_records == 1
    assert snap.diagnostics.duplicate_records_ignored == 1
    assert snap.diagnostics.broker_order_calls == 0
    assert engine.post_trade_review("event").classification is ReviewClassification.WIN
    assert engine.replay_metadata("event").trade_id == "event"
    csv_result = engine.export_csv(tmp_path / "trades.csv", overwrite=True)
    xlsx_result = engine.export_excel(tmp_path / "analytics.xlsx", overwrite=True)
    assert csv_result.record_count == 1
    assert xlsx_result.record_count == 1
    assert "xl/workbook.xml" in ZipFile(xlsx_result.path).namelist()


def test_runtime_snapshot_exposes_portfolio_analytics(tmp_path):
    bus = EventBus()
    lifecycle = ApplicationBootstrap(
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX),
            performance_analytics_configuration=PerformanceAnalyticsConfiguration(journal_path=tmp_path / "journal.jsonl"),
        ),
        event_bus=bus,
    ).create_application()
    lifecycle.start()
    bus.publish(PAPER_TRADE_RECORDED, record("nifty", 100, instrument="NIFTY"))
    bus.publish(PAPER_TRADE_RECORDED, record("bank", -50, instrument="BANKNIFTY"))
    snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert snapshot.performance_analytics.overall.record_count == 2
    per_runtime = {item.symbol.value: item.performance_analytics.selected_instrument.record_count for item in snapshot.runtime_snapshots}
    assert per_runtime == {"NIFTY": 1, "BANKNIFTY": 1, "SENSEX": 0}
    lifecycle.stop()


def test_dashboard_presenter_maps_analytics_view(tmp_path):
    engine = PerformanceAnalyticsEngine(
        configuration=PerformanceAnalyticsConfiguration(journal_path=tmp_path / "journal.jsonl"),
        clock=lambda: BASE,
    )
    engine.record_trade(record("dash", 100))
    runtime = ApplicationBootstrap(
        RuntimeConfiguration(performance_analytics_configuration=PerformanceAnalyticsConfiguration(persistence_enabled=False))
    ).create_application().snapshot().orchestrator_snapshot.runtime_snapshots[0]
    view = build_analytics_view(replace(runtime, performance_analytics=engine.snapshot(instrument="NIFTY")))
    assert view.status == "Ready"
    assert view.total_trades == 1
    assert view.metric_cards
    assert view.recent_trades[0].columns[0] == "dash"

