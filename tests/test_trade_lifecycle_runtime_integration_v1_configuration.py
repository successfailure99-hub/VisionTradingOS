import pytest

from application.enums import ExecutionSafetyMode
from application.trade_lifecycle_runtime_integration_v1 import (
    TradeLifecycleRuntimeIntegrationV1Configuration,
)
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument


def test_default_configuration_is_analysis_only_dry_run_and_supported():
    configuration = TradeLifecycleRuntimeIntegrationV1Configuration()

    assert configuration.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert configuration.broker_mode is BrokerExecutionMode.DRY_RUN
    assert configuration.enabled_instruments == (
        Instrument.NIFTY,
        Instrument.BANKNIFTY,
        Instrument.SENSEX,
    )
    assert configuration.auto_start_coordinators is True
    assert configuration.route_context_updates is True
    assert configuration.route_position_price_updates is True
    assert configuration.require_application_running is True
    assert configuration.reject_duplicate_context is True
    assert configuration.history_limit == 120


def test_configuration_rejects_unsupported_or_duplicate_instruments():
    with pytest.raises(ValueError, match="enabled instruments cannot be empty"):
        TradeLifecycleRuntimeIntegrationV1Configuration(enabled_instruments=())

    with pytest.raises(ValueError, match="enabled instruments must be unique"):
        TradeLifecycleRuntimeIntegrationV1Configuration(
            enabled_instruments=(Instrument.NIFTY, Instrument.NIFTY)
        )

    with pytest.raises(ValueError, match="NIFTY, BANKNIFTY or SENSEX"):
        TradeLifecycleRuntimeIntegrationV1Configuration(
            enabled_instruments=(Instrument.FINNIFTY,)
        )


def test_configuration_rejects_non_bool_flags_and_invalid_history_limit():
    with pytest.raises(TypeError, match="auto_start_coordinators"):
        TradeLifecycleRuntimeIntegrationV1Configuration(auto_start_coordinators=1)

    with pytest.raises(TypeError, match="history_limit"):
        TradeLifecycleRuntimeIntegrationV1Configuration(history_limit=True)

    with pytest.raises(ValueError, match="history_limit"):
        TradeLifecycleRuntimeIntegrationV1Configuration(history_limit=0)
