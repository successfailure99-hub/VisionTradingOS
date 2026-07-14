from dataclasses import FrozenInstanceError

import pytest

from engines.option_chain_analytics import OptionChainAnalyticsConfiguration


def test_defaults_frozen_and_validation():
    config = OptionChainAnalyticsConfiguration()
    assert config.minimum_price_change == 0.05
    assert config.minimum_oi_change == 1
    assert config.strong_pressure_ratio == 1.5
    assert config.strong_bias_score == 3
    assert config.history_limit == 120
    assert not hasattr(config, "api_key")
    assert not hasattr(config, "instrument_token")
    with pytest.raises(FrozenInstanceError):
        config.history_limit = 1
    with pytest.raises(TypeError):
        OptionChainAnalyticsConfiguration(minimum_oi_change=True)
    with pytest.raises(ValueError):
        OptionChainAnalyticsConfiguration(strong_pressure_ratio=1.0)
    with pytest.raises(ValueError):
        OptionChainAnalyticsConfiguration(history_limit=0)
