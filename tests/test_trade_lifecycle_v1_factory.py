import pytest

from application.trade_lifecycle_v1 import TradeLifecycleCoordinatorV1Factory, TradeLifecycleStatus
from core.enums.instrument import Instrument
from tests.test_trade_lifecycle_v1_coordinator import owners


def test_factory_reuses_exact_owners_and_does_not_start_or_process():
    execution, position = owners()
    coordinator = TradeLifecycleCoordinatorV1Factory().create(
        instrument=Instrument.NIFTY,
        execution_runtime=execution,
        position_engine=position,
    )

    assert coordinator.execution_runtime is execution
    assert coordinator.snapshot().lifecycle_status is TradeLifecycleStatus.CREATED
    assert coordinator.history() == ()


def test_factory_rejects_invalid_dependencies():
    execution, position = owners()
    with pytest.raises(TypeError):
        TradeLifecycleCoordinatorV1Factory().create(
            instrument=Instrument.NIFTY,
            execution_runtime=object(),
            position_engine=position,
        )
