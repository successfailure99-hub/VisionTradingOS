import pytest

from application.enums import ExecutionSafetyMode
from application.trade_lifecycle_v1 import TradeLifecycleV1Configuration
from brokers.zerodha.enums import BrokerExecutionMode


def test_defaults_are_analysis_only_dry_run_and_offline():
    cfg = TradeLifecycleV1Configuration()
    assert cfg.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert cfg.broker_mode is BrokerExecutionMode.DRY_RUN
    assert cfg.auto_submit_risk_approved_execution is True
    assert not any("credential" in field or "client" in field for field in cfg.__dataclass_fields__)


def test_rejects_live_modes_bad_booleans_and_history_limit():
    with pytest.raises(ValueError):
        TradeLifecycleV1Configuration(safety_mode=ExecutionSafetyMode.DRY_RUN)
    with pytest.raises(ValueError):
        TradeLifecycleV1Configuration(broker_mode=BrokerExecutionMode.CLIENT)
    with pytest.raises(TypeError):
        TradeLifecycleV1Configuration(auto_open_position_on_fill=1)
    with pytest.raises(TypeError):
        TradeLifecycleV1Configuration(history_limit=True)
    with pytest.raises(ValueError):
        TradeLifecycleV1Configuration(history_limit=0)
