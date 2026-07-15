from dataclasses import FrozenInstanceError

import pytest

from engines.trade_journal_v1 import (
    PerformanceTrend,
    TradeJournalEntryBuilder,
    TradePerformanceStatistics,
)
from tests.test_trade_journal_v1_integration import closed_lifecycle


def test_trade_journal_entry_model_is_immutable_and_authoritative():
    lifecycle = closed_lifecycle(exit_price=120.0)
    entry = TradeJournalEntryBuilder().build(lifecycle)

    assert entry.realized_pnl == lifecycle.position_result.position.realized_pnl
    assert entry.trade_id
    assert entry.closed_quantity == entry.initial_quantity
    with pytest.raises(FrozenInstanceError):
        entry.realized_pnl = 0.0
    assert not any("broker_order" in field or "credential" in field for field in entry.__dataclass_fields__)


def test_performance_statistics_consistency_validation():
    stats = TradePerformanceStatistics(
        1, 1, 0, 0, 1.0, 0.0, 10.0, 10.0, 0.0, 10.0,
        10.0, 10.0, None, 10.0, None, 10.0, None,
        1.0, 1.0, 1.0, 0.0, None, 1, 0, 1, 0,
        PerformanceTrend.INSUFFICIENT_DATA,
    )

    assert stats.trade_count == 1
    with pytest.raises(ValueError):
        TradePerformanceStatistics(
            2, 1, 0, 0, None, None, 0.0, 0.0, 0.0, 0.0,
            None, None, None, None, None, None, None,
            None, None, None, 0.0, None, 0, 0, 0, 0,
            PerformanceTrend.INSUFFICIENT_DATA,
        )
