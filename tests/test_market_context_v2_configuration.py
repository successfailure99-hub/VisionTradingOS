import pytest

from engines.market_context_v2 import MarketContextV2Configuration


def test_defaults_are_frozen_slotted_and_primary_weighted():
    config = MarketContextV2Configuration()
    assert config.price_action_weight == 4
    assert config.option_chain_weight == 4
    assert config.vwap_weight == 1
    assert hasattr(MarketContextV2Configuration, "__slots__")
    with pytest.raises(Exception):
        config.history_limit = 1


def test_invalid_weights_and_booleans_are_rejected():
    with pytest.raises(ValueError):
        MarketContextV2Configuration(price_action_weight=0)
    with pytest.raises(TypeError):
        MarketContextV2Configuration(vwap_weight=True)
    with pytest.raises(ValueError):
        MarketContextV2Configuration(price_action_weight=1, camarilla_weight=2)
    with pytest.raises(ValueError):
        MarketContextV2Configuration(option_chain_weight=1, cpr_weight=2)


def test_threshold_primary_and_history_validation():
    with pytest.raises(ValueError):
        MarketContextV2Configuration(strong_direction_score=2, minimum_direction_score=2)
    with pytest.raises(ValueError):
        MarketContextV2Configuration(high_conflict_score=0)
    with pytest.raises(ValueError):
        MarketContextV2Configuration(minimum_primary_sources=3)
    with pytest.raises(TypeError):
        MarketContextV2Configuration(require_price_action_or_option_chain=1)
    with pytest.raises(ValueError):
        MarketContextV2Configuration(history_limit=0)


def test_no_credentials_or_environment_fields():
    fields = set(MarketContextV2Configuration.__dataclass_fields__)
    assert not any("token" in name.lower() for name in fields)
    assert not any("credential" in name.lower() for name in fields)
    assert not any("env" in name.lower() for name in fields)
