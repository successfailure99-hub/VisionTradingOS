import pytest

from application.enums import ExecutionSafetyMode
from application.trade_journal_runtime_integration_v1 import TradeJournalRuntimeIntegrationV1Configuration
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument


def test_configuration_defaults_and_validation():
    config = TradeJournalRuntimeIntegrationV1Configuration()

    assert config.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert config.broker_mode is BrokerExecutionMode.DRY_RUN
    assert config.enabled_instruments == (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)
    assert config.history_limit == 120
    assert not any("path" in field or "database" in field or "credential" in field for field in config.__dataclass_fields__)

    with pytest.raises(ValueError):
        TradeJournalRuntimeIntegrationV1Configuration(enabled_instruments=(Instrument.NIFTY, Instrument.NIFTY))
    with pytest.raises(ValueError):
        TradeJournalRuntimeIntegrationV1Configuration(enabled_instruments=(Instrument.FINNIFTY,))
    with pytest.raises(TypeError):
        TradeJournalRuntimeIntegrationV1Configuration(auto_start_journal=1)
    with pytest.raises(TypeError):
        TradeJournalRuntimeIntegrationV1Configuration(history_limit=True)
