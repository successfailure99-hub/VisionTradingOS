import pytest

from engines.trade_journal_v1 import TradeJournalStatus, TradeJournalV1Engine, TradeRecordStatus
from tests.test_trade_journal_v1_integration import closed_lifecycle


def test_engine_start_record_duplicate_stop_and_clear():
    engine = TradeJournalV1Engine()
    lifecycle = closed_lifecycle(exit_price=120.0)

    with pytest.raises(RuntimeError):
        engine.record(lifecycle)

    assert engine.start().status is TradeJournalStatus.RUNNING
    result = engine.record(lifecycle)
    assert result.status is TradeRecordStatus.RECORDED
    assert engine.record(lifecycle).status is TradeRecordStatus.DUPLICATE
    assert engine.snapshot().trade_count == 1
    assert engine.snapshot().duplicate_count == 1
    assert engine.stop().status is TradeJournalStatus.STOPPED
    assert engine.clear().status is TradeJournalStatus.CLEARED
    assert engine.entries() == ()
