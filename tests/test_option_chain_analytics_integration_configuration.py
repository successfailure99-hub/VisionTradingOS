from dataclasses import FrozenInstanceError

import pytest

from application.option_chain_analytics_integration import (
    OptionChainAnalyticsIntegrationConfiguration,
)


def test_defaults_frozen_and_offline_safe():
    config = OptionChainAnalyticsIntegrationConfiguration()
    assert config.require_application_running is True
    assert config.require_live_option_integration_running is True
    assert config.process_only_ready_live_snapshots is True
    assert config.reset_analytics_on_clear is True
    assert not hasattr(config, "api_key")
    assert not hasattr(config, "instrument_token")
    with pytest.raises(FrozenInstanceError):
        config.require_application_running = False
    with pytest.raises(TypeError):
        OptionChainAnalyticsIntegrationConfiguration(require_application_running=1)
