from threading import RLock

import pytest

from application.execution_runtime_v1 import ExecutionRuntimeV1
from application.trade_lifecycle_v1 import TradeLifecycleCoordinatorV1, TradeLifecycleStatus
from core.enums.instrument import Instrument
from engines.position_management_v1 import PositionManagementV1Engine
from tests.test_trade_lifecycle_v1_models import request


def owners(instrument=Instrument.NIFTY):
    return (
        ExecutionRuntimeV1(instrument=instrument),
        PositionManagementV1Engine(instrument=instrument),
    )


def coordinator(instrument=Instrument.NIFTY):
    execution, position = owners(instrument)
    return TradeLifecycleCoordinatorV1(
        instrument=instrument,
        execution_runtime=execution,
        position_engine=position,
    )


def test_constructor_identity_initial_validate_start_stop_and_rlock():
    execution, position = owners()
    item = TradeLifecycleCoordinatorV1(
        instrument=Instrument.NIFTY,
        execution_runtime=execution,
        position_engine=position,
    )

    assert item.execution_runtime is execution
    assert item.position_engine is position
    assert item.snapshot().lifecycle_status is TradeLifecycleStatus.CREATED
    assert item.validate().lifecycle_status is TradeLifecycleStatus.READY
    assert item.start().running is True
    assert item.start().running is True
    assert isinstance(item._lock, RLock().__class__)
    item.stop()
    assert item.snapshot().lifecycle_status is TradeLifecycleStatus.STOPPED


def test_same_instrument_required_and_stop_blocks_active_execution_or_position():
    execution, position = owners()
    with pytest.raises(ValueError):
        TradeLifecycleCoordinatorV1(
            instrument=Instrument.BANKNIFTY,
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
