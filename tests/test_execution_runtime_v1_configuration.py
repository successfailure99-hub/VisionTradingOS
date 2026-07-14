import pytest

from application.enums import ExecutionSafetyMode
from application.execution_runtime_v1 import ExecutionFillPolicy, ExecutionRuntimeV1Configuration
from brokers.zerodha.enums import BrokerExecutionMode


def test_defaults_are_dry_run_analysis_only_and_manual():
    cfg = ExecutionRuntimeV1Configuration()
    assert cfg.broker_mode is BrokerExecutionMode.DRY_RUN
    assert cfg.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert cfg.fill_policy is ExecutionFillPolicy.MANUAL_CONFIRMATION
    assert not any("credential" in field or "client" in field for field in cfg.__dataclass_fields__)


def test_rejects_live_modes_bad_booleans_caps_and_manual_inconsistency():
    with pytest.raises(ValueError):
        ExecutionRuntimeV1Configuration(broker_mode=BrokerExecutionMode.CLIENT)
    with pytest.raises(ValueError):
        ExecutionRuntimeV1Configuration(safety_mode=ExecutionSafetyMode.DRY_RUN)
    with pytest.raises(TypeError):
        ExecutionRuntimeV1Configuration(allow_partial_fill=1)
    with pytest.raises(TypeError):
        ExecutionRuntimeV1Configuration(maximum_open_intents=True)
    with pytest.raises(ValueError):
        ExecutionRuntimeV1Configuration(history_limit=0)
    with pytest.raises(ValueError):
        ExecutionRuntimeV1Configuration(require_manual_fill_confirmation=False)
