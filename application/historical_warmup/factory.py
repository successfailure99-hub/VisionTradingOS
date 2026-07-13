"""
Historical warm-up coordinator factory.
"""

from application.historical_warmup.configuration import HistoricalWarmupConfiguration
from application.historical_warmup.coordinator import HistoricalWarmupCoordinator
from application.lifecycle_manager import ApplicationLifecycleManager
from brokers.zerodha.historical import ZerodhaHistoricalDataManager
from brokers.zerodha.instruments import ZerodhaInstrumentResolution


class HistoricalWarmupCoordinatorFactory:
    def create(
        self,
        *,
        lifecycle: ApplicationLifecycleManager,
        historical_manager: ZerodhaHistoricalDataManager,
        resolutions: tuple[ZerodhaInstrumentResolution, ...],
        configuration: HistoricalWarmupConfiguration | None = None,
    ) -> HistoricalWarmupCoordinator:
        return HistoricalWarmupCoordinator(
            lifecycle=lifecycle,
            historical_manager=historical_manager,
            resolutions=resolutions,
            configuration=configuration,
        )
