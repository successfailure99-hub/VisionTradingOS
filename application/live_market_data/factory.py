"""
Live market-data runtime factory.
"""

from datetime import UTC, datetime
from threading import RLock

from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data.configuration import LiveMarketDataConfiguration
from application.live_market_data.models import LiveMarketDataDeliverySnapshot
from application.live_market_data.runtime import LiveMarketDataRuntime
from application.models import RuntimeSnapshot
from brokers.zerodha.auth import ZerodhaSessionManager
from brokers.zerodha.market_data import ZerodhaTickerClientProtocol, ZerodhaWebSocketManager
from core.models.tick import Tick


def _default_clock() -> datetime:
    return datetime.now(UTC)


class _OrchestratorTickConsumer:
    def __init__(self, orchestrator):
        if not hasattr(orchestrator, "process_tick") or not callable(orchestrator.process_tick):
            raise TypeError("orchestrator must expose process_tick")
        self._orchestrator = orchestrator
        self._lock = RLock()
        self._latest_delivery: LiveMarketDataDeliverySnapshot | None = None

    @property
    def latest_delivery(self) -> LiveMarketDataDeliverySnapshot | None:
        with self._lock:
            return self._latest_delivery

    def __call__(self, tick: Tick) -> RuntimeSnapshot:
        if not isinstance(tick, Tick):
            raise TypeError("tick must be Tick")
        try:
            snapshot = self._orchestrator.process_tick(tick)
            if not isinstance(snapshot, RuntimeSnapshot):
                raise TypeError("orchestrator.process_tick must return RuntimeSnapshot")
            delivery = LiveMarketDataDeliverySnapshot(
                symbol=tick.symbol,
                accepted=True,
                runtime_snapshot=snapshot,
                error=None,
            )
        except Exception as exc:
            with self._lock:
                self._latest_delivery = LiveMarketDataDeliverySnapshot(
                    symbol=tick.symbol,
                    accepted=False,
                    runtime_snapshot=None,
                    error=f"{exc.__class__.__name__}: {exc}",
                )
            raise
        with self._lock:
            self._latest_delivery = delivery
        return snapshot


class LiveMarketDataRuntimeFactory:
    def __init__(
        self,
        *,
        websocket_manager_factory=None,
        clock=None,
    ):
        if websocket_manager_factory is not None and not callable(websocket_manager_factory):
            raise TypeError("websocket_manager_factory must be callable")
        self._websocket_manager_factory = websocket_manager_factory or ZerodhaWebSocketManager
        self._clock = clock or _default_clock

    def create(
        self,
        *,
        lifecycle: ApplicationLifecycleManager,
        session_manager: ZerodhaSessionManager,
        configuration: LiveMarketDataConfiguration,
        ticker_client: ZerodhaTickerClientProtocol | None = None,
    ) -> LiveMarketDataRuntime:
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be ApplicationLifecycleManager")
        if not isinstance(session_manager, ZerodhaSessionManager):
            raise TypeError("session_manager must be ZerodhaSessionManager")
        if not isinstance(configuration, LiveMarketDataConfiguration):
            raise TypeError("configuration must be LiveMarketDataConfiguration")
        if not session_manager.is_authenticated() or session_manager.session is None:
            raise RuntimeError("authenticated Zerodha session is required")
        session = session_manager.session
        if session.is_expired(self._clock()):
            raise RuntimeError("Zerodha session is expired")
        consumer = _OrchestratorTickConsumer(lifecycle.orchestrator)
        websocket_kwargs = {
            "api_key": configuration.api_key,
            "session": session,
            "tick_consumer": consumer,
            "subscriptions": configuration.subscriptions,
            "clock": self._clock,
        }
        if ticker_client is not None:
            websocket_kwargs["client"] = ticker_client
        websocket_manager = self._websocket_manager_factory(**websocket_kwargs)
        runtime = LiveMarketDataRuntime(
            lifecycle=lifecycle,
            session_manager=session_manager,
            configuration=configuration,
            websocket_manager=websocket_manager,
            clock=self._clock,
        )
        if configuration.auto_connect:
            runtime.validate()
            runtime.start()
        return runtime
