from datetime import UTC, date, datetime

import pytest

from application.option_chain_analytics_integration.adapters import (
    OptionChainAnalyticsSnapshotDeliveryAdapter,
    analytics_input_from_live_integration_snapshot,
)
from application.option_chain_analytics_integration.enums import (
    OptionChainAnalyticsProcessingResult,
)
from tests.test_option_chain_analytics_integration_processing import build_running_stack


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def test_snapshot_extraction_and_delivery_adapter():
    stack = build_running_stack()
    live = stack["live_coordinator"]
    live.deliver_underlying_price(25050, timestamp=NOW)
    live.deliver_option_ticks(stack["raw_batch"]((100, 200, 300, 400), NOW))
    live_snapshot = live.snapshot()
    source, analysis = analytics_input_from_live_integration_snapshot(live_snapshot)
    assert source.timestamp == analysis.timestamp

    coordinator = stack["analytics_coordinator"]
    coordinator.start()
    adapter = OptionChainAnalyticsSnapshotDeliveryAdapter(coordinator)
    assert adapter.coordinator is coordinator
    outcome = adapter(live_snapshot)
    assert outcome.result is OptionChainAnalyticsProcessingResult.PROCESSED

    with pytest.raises(TypeError):
        analytics_input_from_live_integration_snapshot(object())
