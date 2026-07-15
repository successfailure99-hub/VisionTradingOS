import pytest

from engines.position_management_v1 import PositionExitReason
from engines.trade_journal_v1 import (
    TradeCloseCategory,
    TradeJournalEntryBuilder,
    TradeOutcome,
)
from tests.test_trade_journal_v1_integration import closed_lifecycle, open_lifecycle


def test_builder_creates_winning_losing_and_flat_entries():
    builder = TradeJournalEntryBuilder()

    win = builder.build(closed_lifecycle(exit_price=120.0))
    loss = builder.build(closed_lifecycle(exit_price=90.0))
    flat = builder.build(closed_lifecycle(exit_price=108.0))

    assert win.outcome is TradeOutcome.WIN
    assert loss.outcome is TradeOutcome.LOSS
    assert flat.outcome is TradeOutcome.FLAT
    assert win.r_multiple > 0
    assert loss.r_multiple < 0


def test_builder_maps_manual_close_and_rejects_open_lifecycle():
    entry = TradeJournalEntryBuilder().build(closed_lifecycle(exit_price=120.0))

    assert entry.exit_reason is PositionExitReason.MANUAL_DRY_RUN
    assert entry.close_category is TradeCloseCategory.MANUAL_DRY_RUN
    with pytest.raises(ValueError, match="closed position"):
        TradeJournalEntryBuilder().build(open_lifecycle())
