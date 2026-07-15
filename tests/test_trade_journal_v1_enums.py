from engines.trade_journal_v1 import (
    JournalChange,
    PerformanceTrend,
    TradeCloseCategory,
    TradeJournalStatus,
    TradeOutcome,
    TradeRecordStatus,
)


def test_trade_journal_v1_enum_values_are_stable():
    assert TradeOutcome.WIN.value == "win"
    assert TradeOutcome.LOSS.value == "loss"
    assert TradeOutcome.FLAT.value == "flat"
    assert TradeJournalStatus.CREATED.value == "created"
    assert TradeJournalStatus.RUNNING.value == "running"
    assert TradeRecordStatus.RECORDED.value == "recorded"
    assert TradeCloseCategory.MANUAL_DRY_RUN.value == "manual_dry_run"
    assert PerformanceTrend.INSUFFICIENT_DATA.value == "insufficient_data"
    assert JournalChange.TRADE_RECORDED.value == "trade_recorded"
