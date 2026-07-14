import pytest

from application.option_chain_analytics_integration import (
    OptionChainAnalyticsIntegrationStatus,
)
from tests.test_option_chain_analytics_integration_processing import build_running_stack


def test_start_stop_restart_and_clear():
    stack = build_running_stack(start_analytics=False)
    coordinator = stack["analytics_coordinator"]
    assert coordinator.start().status is OptionChainAnalyticsIntegrationStatus.RUNNING
    assert coordinator.start().start_count == 1
    assert coordinator.stop().status is OptionChainAnalyticsIntegrationStatus.STOPPED
    assert stack["lifecycle"].is_running()
    assert stack["live_coordinator"].snapshot().running is True
    assert coordinator.restart().status is OptionChainAnalyticsIntegrationStatus.RUNNING


def test_processing_while_stopped_rejected():
    stack = build_running_stack(start_analytics=False)
    with pytest.raises(RuntimeError):
        stack["analytics_coordinator"].process_current()
