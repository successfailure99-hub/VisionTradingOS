from application.trade_journal_runtime_integration_v1 import (
    TradeJournalIntegrationChange,
    TradeJournalRoutingResult,
    TradeJournalRuntimeIntegrationStatus,
)


def test_trade_journal_runtime_integration_enum_values_are_stable():
    assert TradeJournalRuntimeIntegrationStatus.CREATED.value == "created"
    assert TradeJournalRuntimeIntegrationStatus.RUNNING.value == "running"
    assert TradeJournalRoutingResult.RECORDED.value == "recorded"
    assert TradeJournalRoutingResult.DUPLICATE.value == "duplicate"
    assert TradeJournalRoutingResult.NOT_CLOSED.value == "not_closed"
    assert TradeJournalIntegrationChange.TRADE_RECORDED.value == "trade_recorded"
    assert TradeJournalIntegrationChange.DUPLICATE_SUPPRESSED.value == "duplicate_suppressed"
    assert len({item.value for item in TradeJournalRoutingResult}) == len(TradeJournalRoutingResult)
