from threading import RLock

import pytest

from application.execution_runtime_v1 import ExecutionRuntimeV1
from application.trade_lifecycle_v1 import TradeLifecycleCoordinatorV1, TradeLifecycleStatus
from core.enums.instrument import Instrument
from engines.ai_reasoning_v2 import AIReasoningV2Engine
from engines.position_management_v1 import PositionManagementV1Engine
from engines.risk_management_v2 import RiskManagementV2Configuration, RiskManagementV2Engine
from engines.strategy_decision_v2 import StrategyDecisionV2Engine
from tests.test_trade_lifecycle_v1_models import request


def owners(instrument=Instrument.NIFTY):
    return (
        AIReasoningV2Engine(instrument=instrument),
        StrategyDecisionV2Engine(instrument=instrument),
        RiskManagementV2Engine(instrument=instrument, configuration=RiskManagementV2Configuration(maximum_position_quantity=10)),
        ExecutionRuntimeV1(instrument=instrument),
        PositionManagementV1Engine(instrument=instrument),
    )


def coordinator(instrument=Instrument.NIFTY):
    ai, strategy, risk, execution, position = owners(instrument)
    return TradeLifecycleCoordinatorV1(
        instrument=instrument,
        ai_reasoning_engine=ai,
        strategy_engine=strategy,
        risk_engine=risk,
        execution_runtime=execution,
        position_engine=position,
    )


def test_constructor_identity_initial_validate_start_stop_and_rlock():
    ai, strategy, risk, execution, position = owners()
    item = TradeLifecycleCoordinatorV1(
        instrument=Instrument.NIFTY,
        ai_reasoning_engine=ai,
        strategy_engine=strategy,
        risk_engine=risk,
        execution_runtime=execution,
        position_engine=position,
    )

    assert item.ai_reasoning_engine is ai
    assert item.strategy_engine is strategy
    assert item.snapshot().lifecycle_status is TradeLifecycleStatus.CREATED
    assert item.validate().lifecycle_status is TradeLifecycleStatus.READY
    assert item.start().running is True
    assert item.start().running is True
    assert isinstance(item._lock, RLock().__class__)
    item.stop()
    assert item.snapshot().lifecycle_status is TradeLifecycleStatus.STOPPED


def test_same_instrument_required_and_stop_blocks_active_execution_or_position():
    ai, strategy, risk, execution, position = owners()
    with pytest.raises(ValueError):
        TradeLifecycleCoordinatorV1(
            instrument=Instrument.BANKNIFTY,
            ai_reasoning_engine=ai,
            strategy_engine=strategy,
            risk_engine=risk,
            execution_runtime=execution,
            position_engine=position,
        )
    item = coordinator()
    item.start()
    item.process(request())
    with pytest.raises(RuntimeError):
        item.stop()


def test_process_approved_reaches_acknowledged_and_duplicate_rejected():
    item = coordinator()
    item.start()
    snapshot = item.process(request())

    assert snapshot.stage.value == "execution_acknowledged"
    assert snapshot.execution_result is not None
    with pytest.raises(RuntimeError):
        item.process(request())
