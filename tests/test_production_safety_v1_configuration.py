import pytest

from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.production_safety_v1 import ProductionSafetyV1Configuration


def test_configuration_defaults_and_validation():
    config = ProductionSafetyV1Configuration()

    assert config.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert config.broker_mode is BrokerExecutionMode.DRY_RUN
    assert config.enabled_instruments == (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)
    assert config.market_data_warning_after_seconds < config.market_data_stale_after_seconds
    assert not any("path" in field or "database" in field or "credential" in field for field in config.__dataclass_fields__)

    with pytest.raises(ValueError):
        ProductionSafetyV1Configuration(maximum_daily_loss_fraction=0.2, maximum_account_drawdown_fraction=0.1)
    with pytest.raises(TypeError):
        ProductionSafetyV1Configuration(maximum_trades_per_day=True)
    with pytest.raises(ValueError):
        ProductionSafetyV1Configuration(enabled_instruments=(Instrument.NIFTY, Instrument.NIFTY))
