"""
Live market-data runtime integration.
"""

from datetime import UTC, datetime
from threading import RLock

from application.enums import RuntimeStatus
from application.exchange_calendar import DEFAULT_EXCHANGE_CALENDAR, ExchangeSessionPhase
from application.feed_watchdog_worker import LiveFeedWatchdogWorker
from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data.configuration import LiveMarketDataConfiguration
from application.live_market_data.enums import LiveFeedWatchdogState, LiveMarketDataRuntimeStatus
from application.live_market_data.forensics import DEFAULT_FEED_TRACE_PATH, FeedIncidentTrace, FeedIncidentTraceEvent
from application.live_market_data.models import LiveMarketDataRuntimeSnapshot
from brokers.zerodha.auth import ZerodhaSessionManager
from brokers.zerodha.market_data import ZerodhaWebSocketManager, ZerodhaWebSocketStatus
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


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
        self._watchdog_state = LiveFeedWatchdogState.WAITING_FIRST_TICK
        self._watchdog_reason = "Waiting for first accepted market tick."
        self._stale_detected_at: datetime | None = None
        self._recovery_attempt = 0
        self._stale_baseline_market_timestamp: datetime | None = None
        self._last_delivered_market_timestamp: datetime | None = None
        self._last_progress_trace_delivered_count: int | None = None
        self._trace = FeedIncidentTrace(
            configuration.feed_trace_path or DEFAULT_FEED_TRACE_PATH,
            redactions=(configuration.api_key, getattr(session_manager.session, "access_token", None)),
        )
        self._watchdog_worker = LiveFeedWatchdogWorker(
            self.poll_watchdog,
            interval_seconds=configuration.watchdog_interval_seconds,
        )
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
            self._record_trace_unlocked("FEED_RUNTIME_STARTED")
            self._watchdog_worker.start()
            self._sync_status_unlocked()
            return self._snapshot_unlocked()

    def stop(self) -> LiveMarketDataRuntimeSnapshot:
        self._watchdog_worker.stop()
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
            self._watchdog_state = LiveFeedWatchdogState.MARKET_CLOSED
            self._watchdog_reason = "Live market-data runtime stopped."
            self._record_trace_unlocked("FEED_RUNTIME_STOPPED")
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

    @property
    def watchdog_worker_running(self) -> bool:
        return self._watchdog_worker.running

    @property
    def watchdog_worker_start_count(self) -> int:
        return self._watchdog_worker.start_count

    def poll_watchdog(self, *, instrument: Instrument = Instrument.NIFTY) -> LiveMarketDataRuntimeSnapshot:
        with self._lock:
            now = self._now()
            websocket = self._websocket_manager.snapshot()
            session = DEFAULT_EXCHANGE_CALENDAR.resolve_active_session(now, Exchange.NSE)
            subscription = self._subscription_for_instrument(instrument)
            if subscription is None:
                self._watchdog_state = LiveFeedWatchdogState.RECOVERY_FAILED
                self._watchdog_reason = f"No configured {instrument.value} live market-data subscription."
                self._last_error = self._watchdog_reason
                self._sync_status_unlocked()
                return self._snapshot_unlocked()
            last_market_timestamp = websocket.last_delivered_market_timestamp(subscription.instrument_token)
            if last_market_timestamp is not None:
                self._last_delivered_market_timestamp = last_market_timestamp
            if session.phase is not ExchangeSessionPhase.OPEN:
                self._watchdog_state = LiveFeedWatchdogState.MARKET_CLOSED
                self._watchdog_reason = session.reason
                self._sync_status_unlocked()
                return self._snapshot_unlocked()
            if websocket.status is ZerodhaWebSocketStatus.RECONNECT_WAIT:
                self._watchdog_state = LiveFeedWatchdogState.RECONNECT_SCHEDULED
                self._watchdog_reason = "Reconnect is scheduled."
                before_attempts = websocket.connect_attempts
                self._record_trace_unlocked("RECONNECT_ATTEMPT", websocket=websocket, instrument=instrument)
                snapshot = self._websocket_manager.retry_connect_if_due()
                if snapshot.connect_attempts > before_attempts:
                    self._watchdog_state = LiveFeedWatchdogState.RECONNECTING
                    self._watchdog_reason = "Reconnect attempt submitted."
                self._sync_status_unlocked()
                return self._snapshot_unlocked()
            if websocket.status is not ZerodhaWebSocketStatus.CONNECTED or not websocket.connected:
                self._watchdog_state = LiveFeedWatchdogState.RECONNECTING
                self._watchdog_reason = f"WebSocket status is {websocket.status.value}."
                self._sync_status_unlocked()
                return self._snapshot_unlocked()
            if last_market_timestamp is None:
                self._watchdog_state = LiveFeedWatchdogState.WAITING_FIRST_TICK
                self._watchdog_reason = "Waiting for first accepted market tick."
                self._sync_status_unlocked()
                return self._snapshot_unlocked()
            if self._stale_baseline_market_timestamp is not None:
                if last_market_timestamp > self._stale_baseline_market_timestamp:
                    self._watchdog_state = LiveFeedWatchdogState.RECOVERED
                    self._watchdog_reason = "Fresh market tick confirmed after reconnect."
                    self._stale_baseline_market_timestamp = None
                    self._stale_detected_at = None
                    self._record_trace_unlocked("FRESH_TICK_CONFIRMED", websocket=websocket, instrument=instrument)
                else:
                    self._watchdog_state = LiveFeedWatchdogState.VERIFYING_FRESH_TICK
                    self._watchdog_reason = "Waiting for newer market tick after reconnect."
                    self._sync_status_unlocked()
                    return self._snapshot_unlocked()
            age_seconds = (now - last_market_timestamp.astimezone(now.tzinfo)).total_seconds()
            if age_seconds > self._configuration.stale_data_seconds:
                self._watchdog_state = LiveFeedWatchdogState.STALE_DETECTED
                self._watchdog_reason = f"Accepted market tick is stale by {int(age_seconds)} seconds."
                self._stale_detected_at = now
                self._stale_baseline_market_timestamp = last_market_timestamp
                self._recovery_attempt += 1
                self._record_trace_unlocked("STALL_DETECTED", websocket=websocket, instrument=instrument)
                self._websocket_manager.recycle_stale_connection("silent live feed stall detected")
                self._watchdog_state = LiveFeedWatchdogState.RECONNECT_SCHEDULED
                self._watchdog_reason = "Silent live feed stall detected; reconnect scheduled."
                self._record_trace_unlocked("RECONNECT_SCHEDULED", websocket=websocket, instrument=instrument)
                self._sync_status_unlocked()
                return self._snapshot_unlocked()
            if self._watchdog_state is not LiveFeedWatchdogState.RECOVERED:
                self._watchdog_state = LiveFeedWatchdogState.HEALTHY
                self._watchdog_reason = "Accepted market ticks are advancing."
            if self._last_progress_trace_delivered_count != websocket.delivered_tick_count:
                self._last_progress_trace_delivered_count = websocket.delivered_tick_count
                self._record_trace_unlocked("NIFTY_DELIVERED_PROGRESS", websocket=websocket, instrument=instrument)
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

    def _subscription_for_instrument(self, instrument: Instrument):
        return next((item for item in self._configuration.subscriptions if item.instrument is instrument), None)

    def _sync_status_unlocked(self) -> None:
        websocket = self._websocket_manager.snapshot()
        if websocket.status is ZerodhaWebSocketStatus.CONNECTED and websocket.connected:
            self._status = LiveMarketDataRuntimeStatus.RUNNING
        elif websocket.status in {
            ZerodhaWebSocketStatus.CONNECTING,
            ZerodhaWebSocketStatus.RECONNECTING,
            ZerodhaWebSocketStatus.RECONNECT_WAIT,
        }:
            self._status = LiveMarketDataRuntimeStatus.STARTING
        elif websocket.status is ZerodhaWebSocketStatus.DISCONNECTING:
            self._status = LiveMarketDataRuntimeStatus.STOPPING
        elif websocket.status in {ZerodhaWebSocketStatus.DISCONNECTED, ZerodhaWebSocketStatus.STOPPED}:
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
            watchdog_state=self._watchdog_state,
            watchdog_reason=self._watchdog_reason,
            watchdog_blocks_decisions=self._watchdog_state
            in {
                LiveFeedWatchdogState.STALE_DETECTED,
                LiveFeedWatchdogState.RECONNECT_SCHEDULED,
                LiveFeedWatchdogState.RECONNECTING,
                LiveFeedWatchdogState.RESUBSCRIBING,
                LiveFeedWatchdogState.VERIFYING_FRESH_TICK,
                LiveFeedWatchdogState.RECOVERY_FAILED,
            },
            stale_data_seconds=self._configuration.stale_data_seconds,
            last_delivered_market_timestamp=self._last_delivered_market_timestamp,
            stale_detected_at=self._stale_detected_at,
            recovery_attempt=self._recovery_attempt,
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

    def _record_trace_unlocked(
        self,
        event: str,
        *,
        websocket=None,
        instrument: Instrument = Instrument.NIFTY,
        error: Exception | None = None,
    ) -> None:
        websocket = websocket or self._websocket_manager.snapshot()
        now = self._now()
        session = DEFAULT_EXCHANGE_CALENDAR.resolve_active_session(now, Exchange.NSE)
        subscription = next((item for item in self._configuration.subscriptions if item.instrument is instrument), None)
        self._trace.record(
            FeedIncidentTraceEvent(
                event_timestamp=now,
                trading_date=session.trading_date,
                runtime_session_id=f"{instrument.value}:{session.trading_date.isoformat() if session.trading_date else 'none'}",
                instrument=instrument.value,
                event=event,
                connection_generation=websocket.connection_count,
                subscription_generation=websocket.subscriptions_applied,
                instrument_token=None if subscription is None else subscription.instrument_token,
                exchange_timestamp=websocket.tick_exchange_timestamp,
                normalized_timestamp=websocket.tick_normalized_at,
                last_delivered_market_timestamp=None
                if subscription is None
                else websocket.last_delivered_market_timestamp(subscription.instrument_token),
                raw_count=websocket.raw_tick_count,
                normalized_count=websocket.normalized_tick_count,
                delivered_count=websocket.delivered_tick_count,
                rejected_count=websocket.rejected_tick_count,
                watchdog_state=self._watchdog_state.value,
                recovery_attempt=self._recovery_attempt,
                error_class=None if error is None else error.__class__.__name__,
                sanitized_error=None if error is None else self._safe_error(error),
            )
        )
