from dataclasses import FrozenInstanceError

import pytest

from application.trade_journal_runtime_integration_v1 import (
    TradeJournalRoutingRequest,
    TradeJournalRoutingResult,
    TradeJournalRuntimeIntegrationStatus,
)
from core.enums.instrument import Instrument
from tests.test_trade_journal_runtime_integration_v1_end_to_end import closed_lifecycle, integration_stack


def test_routing_request_and_snapshot_models_are_immutable():
    lifecycle = closed_lifecycle()
    request = TradeJournalRoutingRequest(Instrument.NIFTY, lifecycle)
    integration = integration_stack()[0]
    snapshot = integration.snapshot()

    assert request.lifecycle_snapshot is lifecycle
    assert snapshot.status is TradeJournalRuntimeIntegrationStatus.CREATED
    assert snapshot.instruments[0].instrument is Instrument.NIFTY
    with pytest.raises(FrozenInstanceError):
        request.instrument = Instrument.BANKNIFTY
    with pytest.raises(ValueError):
        TradeJournalRoutingRequest(Instrument.BANKNIFTY, lifecycle)
    assert not any("owner" in field or "broker" in field for field in request.__dataclass_fields__)


def test_routing_outcome_consistency_for_recorded_trade():
    integration = integration_stack()[0]
    integration.start()
    outcome = integration.route_if_closed(closed_lifecycle())

    assert outcome.result is TradeJournalRoutingResult.RECORDED
    assert outcome.journal_result is not None
