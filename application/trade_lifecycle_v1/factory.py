"""
Factory for Trade Lifecycle Coordinator V1.
"""

from application.execution_runtime_v1 import ExecutionRuntimeV1
from application.trade_lifecycle_v1.configuration import TradeLifecycleV1Configuration
from application.trade_lifecycle_v1.coordinator import TradeLifecycleCoordinatorV1
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from engines.position_management_v1 import PositionManagementV1Engine


class TradeLifecycleCoordinatorV1Factory:
    def create(
        self,
        *,
        instrument: Instrument,
        execution_runtime: ExecutionRuntimeV1,
        position_engine: PositionManagementV1Engine,
        configuration: TradeLifecycleV1Configuration | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ) -> TradeLifecycleCoordinatorV1:
        return TradeLifecycleCoordinatorV1(
            instrument=instrument,
            execution_runtime=execution_runtime,
            position_engine=position_engine,
            configuration=configuration,
            event_bus=event_bus,
            clock=clock,
        )
