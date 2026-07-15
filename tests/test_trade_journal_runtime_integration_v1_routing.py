from dataclasses import replace

import pytest

from application.trade_journal_runtime_integration_v1 import (
    TradeJournalRoutingRequest,
    TradeJournalRoutingResult,
)
from core.enums.instrument import Instrument
from tests.test_trade_journal_runtime_integration_v1_end_to_end import closed_lifecycle, integration_stack, open_lifecycle


def test_closed_not_closed_missing_and_wrong_instrument_routing():
    integration = integration_stack()[0]
    integration.start()

    recorded = integration.route_if_closed(closed_lifecycle())
    assert recorded.result is TradeJournalRoutingResult.RECORDED
    assert integration.snapshot().recorded_count == 1

    not_closed = integration.route_if_closed(open_lifecycle())
    assert not_closed.result is TradeJournalRoutingResult.NOT_CLOSED

    missing = replace(closed_lifecycle(), risk_decision=None)
    rejected = integration.route_if_closed(missing)
    assert rejected.result is TradeJournalRoutingResult.REJECTED

    with pytest.raises(ValueError):
        TradeJournalRoutingRequest(Instrument.BANKNIFTY, closed_lifecycle())
