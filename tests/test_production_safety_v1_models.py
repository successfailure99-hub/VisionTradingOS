from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from application.enums import ExecutionSafetyMode, RuntimeStatus
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.production_safety_v1 import (
    ManualSafetyCommand,
    ProductionSafetyV1Input,
    SafetyScope,
)
from tests.test_market_context_v2_integration import NOW
from tests.test_production_safety_v1_integration import account, healthy_snapshots, session


def test_input_and_manual_command_validation_and_immutability():
    lifecycle, journal = healthy_snapshots()
    item = ProductionSafetyV1Input(
        NOW,
        RuntimeStatus.RUNNING,
        ExecutionSafetyMode.ANALYSIS_ONLY,
        BrokerExecutionMode.DRY_RUN,
        lifecycle,
        journal,
        account(),
        session(),
        ((Instrument.NIFTY, NOW - timedelta(seconds=1)),),
    )

    assert item.latest_market_data_at[0][0] is Instrument.NIFTY
    with pytest.raises(FrozenInstanceError):
        item.application_status = RuntimeStatus.ERROR
    with pytest.raises(ValueError):
        ManualSafetyCommand(NOW, SafetyScope.GLOBAL, Instrument.NIFTY, "bad")
    with pytest.raises(ValueError):
        ManualSafetyCommand(NOW, SafetyScope.INSTRUMENT, None, "bad")
