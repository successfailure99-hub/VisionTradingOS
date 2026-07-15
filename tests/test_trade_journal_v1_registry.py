from threading import RLock

import pytest

from engines.trade_journal_v1 import TradeJournalEntryBuilder, TradeJournalRegistry, TradeRecordStatus
from tests.test_trade_journal_v1_integration import closed_lifecycle


def test_registry_add_get_duplicate_order_clear_and_rlock():
    entry = TradeJournalEntryBuilder().build(closed_lifecycle(exit_price=120.0))
    registry = TradeJournalRegistry()

    assert registry.add(entry).status is TradeRecordStatus.RECORDED
    assert registry.get(entry.trade_id) is entry
    assert registry.entries() == (entry,)
    assert registry.add(entry).status is TradeRecordStatus.DUPLICATE
    assert isinstance(registry._lock, RLock().__class__)

    with pytest.raises(ValueError):
        registry.get("missing")

    registry.clear()
    assert registry.entries() == ()
