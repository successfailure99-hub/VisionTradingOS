"""
Factory for Trade Lifecycle Runtime Integration V1.
"""

from application.lifecycle_manager import ApplicationLifecycleManager
from application.trade_lifecycle_runtime_integration_v1.configuration import TradeLifecycleRuntimeIntegrationV1Configuration
from application.trade_lifecycle_runtime_integration_v1.integration import TradeLifecycleRuntimeIntegrationV1
from application.trade_lifecycle_runtime_integration_v1.registry import TradeLifecycleCoordinatorRegistry
from application.trade_lifecycle_v1 import TradeLifecycleCoordinatorV1
from core.event_bus import EventBus


class TradeLifecycleRuntimeIntegrationV1Factory:
    def create(
        self,
        *,
        application_lifecycle,
        coordinators: tuple[TradeLifecycleCoordinatorV1, ...],
        configuration: TradeLifecycleRuntimeIntegrationV1Configuration | None = None,
        event_bus: EventBus | None = None,
        clock=None,
    ) -> TradeLifecycleRuntimeIntegrationV1:
        if not isinstance(application_lifecycle, ApplicationLifecycleManager):
            raise TypeError("application_lifecycle must be ApplicationLifecycleManager")
        registry = TradeLifecycleCoordinatorRegistry()
        for coordinator in coordinators:
            registry.register(coordinator.instrument, coordinator)
        return TradeLifecycleRuntimeIntegrationV1(
            application_lifecycle=application_lifecycle,
            registry=registry,
            configuration=configuration,
            event_bus=event_bus,
            clock=clock,
        )
