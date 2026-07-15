from engines.trade_journal_v1 import (
    TradeJournalEntryBuilder,
    TradeJournalV1Configuration,
    TradePerformanceAnalyticsCalculator,
)
from tests.test_trade_journal_v1_integration import NOW, closed_lifecycle


def test_analytics_calculates_core_performance_metrics():
    builder = TradeJournalEntryBuilder()
    entries = (
        builder.build(closed_lifecycle(exit_price=120.0)),
        builder.build(closed_lifecycle(exit_price=90.0)),
        builder.build(closed_lifecycle(exit_price=108.0)),
    )

    snapshot = TradePerformanceAnalyticsCalculator().calculate(
        entries,
        TradeJournalV1Configuration(minimum_trades_for_trend=3),
        timestamp=NOW,
    )

    assert snapshot.overall.trade_count == 3
    assert snapshot.overall.win_count == 1
    assert snapshot.overall.loss_count == 1
    assert snapshot.overall.flat_count == 1
    assert snapshot.overall.win_rate == 1 / 3
    assert snapshot.overall.profit_factor is not None
    assert snapshot.equity_curve[-1].cumulative_pnl == snapshot.overall.total_pnl
    assert snapshot.by_instrument[0].instrument is entries[0].instrument
    assert snapshot.by_setup[0].setup_family is entries[0].setup_family
    assert len(snapshot.by_confidence) == 4
