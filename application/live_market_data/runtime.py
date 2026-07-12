"""
Live market-data runtime integration.
"""

from datetime import UTC, datetime
from threading import RLock

from application.enums import RuntimeStatus
from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data.configuration import LiveMarketDataConfiguration
from application.live_market_data.enums import LiveMarketDataRuntimeStatus
from application.live_market_data.models import LiveMarketDataRuntimeSnapshot
from brokers.zerodha.auth import ZerodhaSessionManager
from brokers.zerodha.market_data import ZerodhaWebSocketManager, ZerodhaWebSocketStatus


def _default_clock() -> datetime:
    return datetime.now(UTC)


class LiveMarketDataRuntime:
    def __init__(
        self,
        *,
        lifecycle: ApplicationLifecycleManager,
        session_manager: ZerodhaSessionManager,
        configuration: LiveMarketDataConfiguration,
        websocket_manager: ZerodhaWebSocketManager,
        clock=None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be ApplicationLifecycleManager")
        if not isinstance(session_manager, ZerodhaSessionManager):
            raise TypeError("session_manager must be ZerodhaSessionManager")
        if not isinstance(configuration, LiveMarketDataConfiguration):
            raise TypeError("configuration must be LiveMarketDataConfiguration")
        if not isinstance(websocket_manager, ZerodhaWebSocketManager):
            raise TypeError("websocket_manager must be ZerodhaWebSocketManager")
        self._lifecycle = lifecycle
        self._session_manager = session_manager
        self._configuration = configuration
        self._websocket_manager = websocket_manager
        self._clock = clock or _default_clock
        self._lock = RLock()
        self._status = LiveMarketDataRuntimeStatus.CREATED
        self._start_count = 0
        self._stop_count = 0
        self._last_started_at: datetime | None = None
        self._last_stopped_at: datetime | None = None
        self._last_error: str | None = None
        self._validate_session_state()
        self._validate_registry_matches_configuration()

    @property
    def lifecycle(self) -> ApplicationLifecycleManager:
        return self._lifecycle

    @property
    def session_manager(self) -> ZerodhaSessionManager:
        return self._session_manager

    @property
    def configuration(self) -> LiveMarketDataConfiguration:
        return self._configuration

    @property
    def websocket_manager(self) -> ZerodhaWebSocketManager:
        return self._websocket_manager

    @property
    def status(self) -> LiveMarketDataRuntimeStatus:
        with self._lock:
            self._sync_status_unlocked()
            return self._status

    def validate(self) -> LiveMarketDataRuntimeSnapshot:
        with self._lock:
            try:
                self._validate_lifecycle_running()
                self._validate_session_state()
                self._validate_configured_instruments()
                self._validate_registry_matches_configuration()
            except Exception as exc:
                self._status = LiveMarketDataRuntimeStatus.ERROR
                self._last_error = self._safe_error(exc)
                raise
            self._status = LiveMarketDataRuntimeStatus.READY
            self._last_error = None
            return self._snapshot_unlocked()

    def start(self) -> LiveMarketDataRuntimeSnapshot:
        with self._lock:
            self._sync_status_unlocked()
            if self._status in {LiveMarketDataRuntimeStatus.RUNNING, LiveMarketDataRuntimeStatus.STARTING}:
                return self._snapshot_unlocked()
            self.validate()
            self._status = LiveMarketDataRuntimeStatus.STARTING
            try:
                self._websocket_manager.connect()
            except Exception as exc:
                self._status = LiveMarketDataRuntimeStatus.ERROR
                self._last_error = self._safe_error(exc)
                raise
            self._start_count += 1
            self._last_started_at = self._now()
            self._last_error = None
            self._sync_status_unlocked()
            return self._snapshot_unlocked()

    def stop(self) -> LiveMarketDataRuntimeSnapshot:
        with self._lock:
            self._sync_status_unlocked()
            if self._status in {
                LiveMarketDataRuntimeStatus.CREATED,
                LiveMarketDataRuntimeStatus.READY,
                LiveMarketDataRuntimeStatus.STOPPED,
            }:
                self._status = LiveMarketDataRuntimeStatus.STOPPED
                return self._snapshot_unlocked()
            try:
                self._status = LiveMarketDataRuntimeStatus.STOPPING
                self._websocket_manager.disconnect()
            except Exception as exc:
                self._status = LiveMarketDataRuntimeStatus.ERROR
                self._last_error = self._safe_error(exc)
                raise
            self._stop_count += 1
            self._last_stopped_at = self._now()
            self._sync_status_unlocked()
            return self._snapshot_unlocked()

    def restart(self) -> LiveMarketDataRuntimeSnapshot:
        with self._lock:
            websocket = self._websocket_manager
            self.stop()
            self.validate()
            snapshot = self.start()
            if self._websocket_manager is not websocket:
                raise RuntimeError("websocket manager changed during restart")
            return snapshot

    def snapshot(self) -> LiveMarketDataRuntimeSnapshot:
        with self._lock:
            self._sync_status_unlocked()
            return self._snapshot_unlocked()

    def is_ready(self) -> bool:
        return self.snapshot().ready

    def is_running(self) -> bool:
        return self.snapshot().running

    def _validate_lifecycle_running(self) -> None:
        if self._lifecycle.status is not RuntimeStatus.RUNNING:
            raise RuntimeError("application lifecycle must be RUNNING")

    def _validate_session_state(self) -> None:
        if not self._session_manager.is_authenticated():
            raise RuntimeError("Zerodha session manager must be authenticated")
        session = self._session_manager.session
        if session is None:
            raise RuntimeError("Zerodha session is required")
        if session.is_expired(self._now()):
            raise RuntimeError("Zerodha session is expired")

    def _validate_configured_instruments(self) -> None:
        configured = set(self._lifecycle.orchestrator.configuration.instruments)
        for subscription in self._configuration.subscriptions:
            if subscription.instrument.value not in {instrument.value for instrument in configured}:
                raise ValueError("subscription instrument is not configured in application runtime")

    def _validate_registry_matches_configuration(self) -> None:
        if self._websocket_manager.registry.all() != self._configuration.subscriptions:
            raise ValueError("WebSocket registry must exactly match live market-data configuration")

    def _sync_status_unlocked(self) -> None:
        websocket = self._websocket_manager.snapshot()
        if websocket.status is ZerodhaWebSocketStatus.CONNECTED and websocket.connected:
            self._status = LiveMarketDataRuntimeStatus.RUNNING
        elif websocket.status in {ZerodhaWebSocketStatus.CONNECTING, ZerodhaWebSocketStatus.RECONNECTING}:
            self._status = LiveMarketDataRuntimeStatus.STARTING
        elif websocket.status is ZerodhaWebSocketStatus.DISCONNECTING:
            self._status = LiveMarketDataRuntimeStatus.STOPPING
        elif websocket.status is ZerodhaWebSocketStatus.DISCONNECTED:
            self._status = LiveMarketDataRuntimeStatus.STOPPED
        elif websocket.status is ZerodhaWebSocketStatus.ERROR:
            self._status = LiveMarketDataRuntimeStatus.ERROR

    def _snapshot_unlocked(self) -> LiveMarketDataRuntimeSnapshot:
        websocket = self._websocket_manager.snapshot()
        return LiveMarketDataRuntimeSnapshot(
            status=self._status,
            ready=self._status in {
                LiveMarketDataRuntimeStatus.READY,
                LiveMarketDataRuntimeStatus.STARTING,
                LiveMarketDataRuntimeStatus.RUNNING,
                LiveMarketDataRuntimeStatus.STOPPING,
            },
            running=self._status is LiveMarketDataRuntimeStatus.RUNNING,
            configured_instruments=tuple(subscription.instrument for subscription in self._configuration.subscriptions),
            configured_tokens=tuple(subscription.instrument_token for subscription in self._configuration.subscriptions),
            websocket=websocket,
            start_count=self._start_count,
            stop_count=self._stop_count,
            last_started_at=self._last_started_at,
            last_stopped_at=self._last_stopped_at,
            last_error=self._last_error,
        )

    def _safe_error(self, exc: Exception) -> str:
        message = f"{exc.__class__.__name__}: {exc}"
        for secret in (self._configuration.api_key, getattr(self._session_manager.session, "access_token", None)):
            if secret:
                message = message.replace(secret, "[REDACTED]")
        return message

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock result must be datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock result must be timezone-aware")
        return value
