from dataclasses import FrozenInstanceError

import pytest

from application.execution_runtime_v1 import ExecutionRuntimeV1
from application.trade_lifecycle_v1 import (
    TradeLifecycleBlockSource,
    TradeLifecycleOutcome,
    TradeLifecycleStage,
    TradeLifecycleStageRecord,
    TradeLifecycleStatus,
    TradeLifecycleV1Request,
    TradeLifecycleV1Snapshot,
)
from core.enums.instrument import Instrument
from engines.position_management_v1 import PositionManagementV1Engine
from tests.test_ai_reasoning_v2_models import NOW
from tests.test_risk_management_v2_calculator import calculate, risk_input


def request(risk=None):
    risk = risk or calculate(risk_input(proposed_invalidation_price=83.0, proposed_objective_price=148.0))
    return TradeLifecycleV1Request(
        strategy_decision=risk.strategy,
        risk_decision=risk,
    )


def test_request_stage_record_and_snapshot_validation():
    req = request()
    record = TradeLifecycleStageRecord(1, NOW, TradeLifecycleStage.CONTEXT_RECEIVED, TradeLifecycleOutcome.IN_PROGRESS, "Context received.")
    execution_snapshot = ExecutionRuntimeV1(instrument=Instrument.NIFTY).snapshot()
    position_snapshot = PositionManagementV1Engine(instrument=Instrument.NIFTY).snapshot()
    snapshot = TradeLifecycleV1Snapshot(
        Instrument.NIFTY,
        NOW,
        TradeLifecycleStatus.CREATED,
        TradeLifecycleStage.IDLE,
        TradeLifecycleOutcome.IN_PROGRESS,
        __import__("application.trade_lifecycle_v1", fromlist=["TradeLifecycleChange"]).TradeLifecycleChange.INITIAL,
        TradeLifecycleBlockSource.NONE,
        req.strategy_decision,
        req.risk_decision,
        None,
        None,
        execution_snapshot,
        position_snapshot,
        (record,),
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        False,
        False,
        None,
        None,
        None,
        None,
    )

    assert req.instrument is Instrument.NIFTY
    assert snapshot.stage_records == (record,)
    with pytest.raises(FrozenInstanceError):
        snapshot.processing_count = 2
    with pytest.raises(ValueError):
        TradeLifecycleStageRecord(0, NOW, TradeLifecycleStage.IDLE, TradeLifecycleOutcome.IN_PROGRESS, "Bad.")
    assert not any("owner" in field or "credential" in field or "raw_tick" in field for field in req.__dataclass_fields__)
