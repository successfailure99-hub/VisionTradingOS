from application.trade_journal_runtime_integration_v1 import TradeJournalRoutingResult
from tests.test_trade_journal_runtime_integration_v1_end_to_end import closed_lifecycle, integration_stack


def test_duplicate_closed_lifecycle_does_not_change_analytics_trade_count():
    integration = integration_stack()[0]
    integration.start()
    lifecycle = closed_lifecycle()

    first = integration.route_if_closed(lifecycle)
    before = integration.snapshot().analytics_snapshot
    second = integration.route_if_closed(lifecycle)
    after = integration.snapshot().analytics_snapshot

    assert first.result is TradeJournalRoutingResult.RECORDED
    assert second.result is TradeJournalRoutingResult.DUPLICATE
    assert before.overall.trade_count == after.overall.trade_count == 1
    assert integration.snapshot().duplicate_count == 1
