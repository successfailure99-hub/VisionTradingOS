from dataclasses import FrozenInstanceError

import pytest

from application.live_option_chain import LiveOptionChainConfiguration


def test_defaults_are_offline_and_strict():
    config = LiveOptionChainConfiguration()
    assert config.require_all_pairs is True
    assert config.maximum_quote_age_seconds == 15
    assert config.reject_crossed_market is True
    assert config.publish_on_every_accepted_batch is True
    assert not hasattr(config, "api_key")
    assert not hasattr(config, "access_token")


def test_frozen_slotted_and_validation():
    config = LiveOptionChainConfiguration()
    with pytest.raises(FrozenInstanceError):
        config.maximum_quote_age_seconds = 1
    with pytest.raises(TypeError):
        LiveOptionChainConfiguration(require_all_pairs=1)
    with pytest.raises(TypeError):
        LiveOptionChainConfiguration(maximum_quote_age_seconds=True)
    with pytest.raises(ValueError):
        LiveOptionChainConfiguration(maximum_quote_age_seconds=0)
