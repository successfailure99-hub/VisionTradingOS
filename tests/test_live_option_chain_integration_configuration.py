from dataclasses import FrozenInstanceError

import pytest

from application.live_option_chain_integration import LiveOptionChainIntegrationConfiguration


def test_defaults_are_offline_safe_and_validated():
    config = LiveOptionChainIntegrationConfiguration()
    assert config.require_application_running is True
    assert config.require_live_market_data_running_for_spot is False
    assert config.stop_live_option_runtime_on_shutdown is True
    assert config.deactivate_option_subscriptions_on_shutdown is False
    assert not hasattr(config, "api_key")
    assert not hasattr(config, "access_token")
    assert not hasattr(config, "instrument_token")
    with pytest.raises(FrozenInstanceError):
        config.require_application_running = False
    with pytest.raises(TypeError):
        LiveOptionChainIntegrationConfiguration(require_application_running=1)
