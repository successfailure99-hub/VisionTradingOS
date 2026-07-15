from engines.trade_journal_v1 import TradeJournalStatus, TradeJournalV1Engine
from tests.test_trade_journal_v1_integration import closed_lifecycle


def test_trade_journal_v1_transitions_and_streaks():
    engine = TradeJournalV1Engine()
    assert engine.snapshot().status is TradeJournalStatus.CREATED

    engine.start()
    engine.record(closed_lifecycle(exit_price=120.0))
    engine.record(closed_lifecycle(exit_price=90.0))

    stats = engine.analytics_snapshot().overall
    assert stats.trade_count == 2
    assert stats.maximum_winning_streak == 1
    assert stats.maximum_losing_streak == 1
    assert stats.maximum_drawdown_amount > 0.0

    engine.stop()
    assert engine.clear().trade_count == 0
