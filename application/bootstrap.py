"""
Application Bootstrap V1 composition root.
"""

from application.lifecycle_manager import ApplicationLifecycleManager
from application.models import RuntimeConfiguration
from application.orchestrator import ApplicationOrchestrator
from core.event_bus import EventBus


class ApplicationBootstrap:
    """
    Production composition root for the synchronous backend runtime.

    The bootstrap creates exactly one EventBus, one ApplicationOrchestrator,
    and one ApplicationLifecycleManager for a bootstrap instance. It performs
    no engine business logic and does not start the application unless
    bootstrap() is explicitly called.
    """

    def __init__(
        self,
        configuration: RuntimeConfiguration | None = None,
        *,
        event_bus=None,
        orchestrator_factory=None,
    ):
        if configuration is None:
            configuration = RuntimeConfiguration()
        if not isinstance(configuration, RuntimeConfiguration):
            raise TypeError("configuration must be a RuntimeConfiguration.")
        if event_bus is not None and not isinstance(event_bus, EventBus):
            raise TypeError("event_bus must be an EventBus.")
        if orchestrator_factory is not None and not callable(orchestrator_factory):
            raise TypeError("orchestrator_factory must be callable.")

        self._configuration = configuration
        self._injected_event_bus = event_bus
        self._orchestrator_factory = orchestrator_factory
        self._event_bus: EventBus | None = None
        self._orchestrator: ApplicationOrchestrator | None = None
        self._manager: ApplicationLifecycleManager | None = None

    @property
    def configuration(self) -> RuntimeConfiguration:
        return self._configuration

    def create_application(self) -> ApplicationLifecycleManager:
        if self._manager is not None:
            return self._manager

        self._event_bus = self._injected_event_bus or EventBus()
        self._orchestrator = self._create_orchestrator(self._event_bus)
        self._manager = ApplicationLifecycleManager(self._orchestrator)
        return self._manager

    def bootstrap(self) -> ApplicationLifecycleManager:
        manager = self.create_application()
        manager.start()
        return manager

    def _create_orchestrator(self, event_bus: EventBus) -> ApplicationOrchestrator:
        if self._orchestrator_factory is None:
            return ApplicationOrchestrator(event_bus, self._configuration)

        orchestrator = self._orchestrator_factory(event_bus, self._configuration)
        if not isinstance(orchestrator, ApplicationOrchestrator):
            raise TypeError("orchestrator_factory must return an ApplicationOrchestrator.")
        return orchestrator


def create_application(
    configuration: RuntimeConfiguration | None = None,
) -> ApplicationLifecycleManager:
    return ApplicationBootstrap(configuration).create_application()
