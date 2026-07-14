import pytest

from engines.risk_management_v2 import PositionSizingMode, RiskManagementV2Configuration


def test_defaults_are_conservative_and_offline():
    cfg = RiskManagementV2Configuration()
    assert cfg.risk_per_trade_fraction == 0.005
    assert cfg.maximum_position_quantity == 1
    assert cfg.sizing_mode is PositionSizingMode.MINIMUM_OF_LIMITS
    assert not any("broker" in field or "credential" in field or "order" in field for field in cfg.__dataclass_fields__)


def test_fraction_threshold_integer_boolean_and_mode_validation():
    with pytest.raises(ValueError):
        RiskManagementV2Configuration(risk_per_trade_fraction=0.02, maximum_risk_per_trade_fraction=0.01)
    with pytest.raises(ValueError):
        RiskManagementV2Configuration(maximum_daily_loss_fraction=0.11, maximum_account_drawdown_fraction=0.10)
    with pytest.raises(ValueError):
        RiskManagementV2Configuration(maximum_instrument_exposure_fraction=0.30, maximum_total_exposure_fraction=0.25)
    with pytest.raises(TypeError):
        RiskManagementV2Configuration(maximum_position_quantity=True)
    with pytest.raises(ValueError):
        RiskManagementV2Configuration(reduced_size_fraction=1.0)
    with pytest.raises(TypeError):
        RiskManagementV2Configuration(sizing_mode="minimum")
    with pytest.raises(TypeError):
        RiskManagementV2Configuration(reject_low_quality_setups=1)
