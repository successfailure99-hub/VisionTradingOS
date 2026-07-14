"""
Factory for Execution Runtime V1.
"""

from application.execution_runtime_v1.configuration import ExecutionRuntimeV1Configuration
from application.execution_runtime_v1.runtime import ExecutionRuntimeV1
from core.enums.instrument import Instrument
from core.event_bus import EventBus


class ExecutionRuntimeV1Factory:
    def create(
        self,
        *,
        instrument: Instrument,
        configuration: ExecutionRuntimeV1Configuration | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ) -> ExecutionRuntimeV1:
        return ExecutionRuntimeV1(
            instrument=instrument,
            configuration=configuration,
            event_bus=event_bus,
            clock=clock,
        )
