"""
Zerodha live market-data WebSocket manager.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from threading import RLock
from time import perf_counter_ns

from brokers.zerodha.auth.models import ZerodhaSession
from brokers.zerodha.market_data.client import KiteTickerClient, ZerodhaTickerClientProtocol
from brokers.zerodha.market_data.enums import ZerodhaSubscriptionMode, ZerodhaWebSocketStatus
from brokers.zerodha.market_data.models import (
    TickConsumerProtocol,
    ZerodhaInstrumentSubscription,
    ZerodhaTickBatchResult,
    ZerodhaWebSocketSnapshot,
)
from brokers.zerodha.market_data.normalizer import ZerodhaTickNormalizer
from brokers.zerodha.market_data.subscription_registry import ZerodhaSubscriptionRegistry


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


class ZerodhaWebSocketManager:
    def __init__(
        self,
        *,
        api_key: str,
        session: ZerodhaSession,
        tick_consumer: TickConsumerProtocol,
        subscriptions: tuple[ZerodhaInstrumentSubscription, ...] = (),
        client: ZerodhaTickerClientProtocol | None = None,
        clock=None,
        reconnect_initial_delay_seconds: int = 1,
        reconnect_max_delay_seconds: int = 60,
    ):
        self._api_key = _require_text(api_key, "api_key")
        if not isinstance(session, ZerodhaSession):
            raise TypeError("session must be ZerodhaSession")
        self._session = session
        self._clock = clock or _default_clock
        self._reconnect_initial_delay_seconds = self._require_positive_int(
            reconnect_initial_delay_seconds,
            "reconnect_initial_delay_seconds",
        )
        self._reconnect_max_delay_seconds = self._require_positive_int(
            reconnect_max_delay_seconds,
            "reconnect_max_delay_seconds",
        )
        if self._reconnect_initial_delay_seconds > self._reconnect_max_delay_seconds:
            raise ValueError("reconnect_initial_delay_seconds must be <= reconnect_max_delay_seconds")
        if session.is_expired(self._now()):
            raise ValueError("Zerodha session is expired")
        if not callable(tick_consumer):
            raise TypeError("tick_consumer must be callable")
        self._tick_consumer = tick_consumer
        self._registry = ZerodhaSubscriptionRegistry(subscriptions)
        self._normalizer = ZerodhaTickNormalizer(self._registry, clock=self._clock)
        self._client = client or KiteTickerClient(
            api_key=self._api_key,
            access_token=session.access_token,
            reconnect=False,
            reconnect_max_delay=self._reconnect_max_delay_seconds,
        )
        self._lock = RLock()
        self._status = ZerodhaWebSocketStatus.CREATED
        self._connection_count = 0
        self._disconnection_count = 0
        self._reconnect_count = 0
        self._client_instances_created = 1
        self._connect_attempts = 0
        self._successful_connections = 0
        self._disconnect_callbacks = 0
        self._error_callbacks = 0
        self._retry_scheduled = 0
        self._subscriptions_applied = 0
        self._duplicate_callbacks_suppressed = 0
        self._raw_tick_count = 0
        self._normalized_tick_count = 0
        self._delivered_tick_count = 0
        self._rejected_tick_count = 0
        self._last_connected_at: datetime | None = None
        self._last_disconnected_at: datetime | None = None
        self._last_tick_at: datetime | None = None
        self._last_error: str | None = None
        self._disconnect_count_available = False
        self._retry_count = 0
        self._reconnect_delay_seconds = 0
        self._reconnect_due_at: datetime | None = None
        self._suppressed_error_count = 0
        self._last_error_fingerprint: str | None = None
        self._broker_received_at: datetime | None = None
        self._tick_exchange_timestamp: datetime | None = None
        self._tick_normalized_at: datetime | None = None
        self._event_published_at: datetime | None = None
        self._runtime_processed_at: datetime | None = None
        self._latest_tick_latency_ms: float | None = None
        self._max_tick_latency_ms: float | None = None
        self._subscriptions_applied_for_connection = False
        self._client.set_callbacks(
            on_connect=self._on_connect,
            on_ticks=self._on_ticks,
            on_close=self._on_close,
            on_error=self._on_error,
            on_reconnect=self._on_reconnect,
            on_noreconnect=self._on_noreconnect,
        )

    @property
    def status(self) -> ZerodhaWebSocketStatus:
        with self._lock:
            return self._status

    @property
    def registry(self) -> ZerodhaSubscriptionRegistry:
        return self._registry

    def connect(self) -> ZerodhaWebSocketSnapshot:
        with self._lock:
            self._reject_expired_session()
            if self._status in {
                ZerodhaWebSocketStatus.CONNECTED,
                ZerodhaWebSocketStatus.CONNECTING,
                ZerodhaWebSocketStatus.DISCONNECTING,
            }:
                return self.snapshot()
            if self._status is ZerodhaWebSocketStatus.RECONNECT_WAIT and not self._retry_due_unlocked():
                return self.snapshot()
            self._status = ZerodhaWebSocketStatus.CONNECTING
            self._subscriptions_applied_for_connection = False
            self._connect_attempts += 1
            try:
                self._client.connect(threaded=True)
            except Exception as exc:
                self._record_error_unlocked(exc)
                self._schedule_reconnect_unlocked()
                raise
            return self.snapshot()

    def retry_connect_if_due(self) -> ZerodhaWebSocketSnapshot:
        with self._lock:
            if self._status is not ZerodhaWebSocketStatus.RECONNECT_WAIT:
                return self.snapshot()
            if not self._retry_due_unlocked():
                return self.snapshot()
        return self.connect()

    def disconnect(self) -> ZerodhaWebSocketSnapshot:
        with self._lock:
            if self._status in {ZerodhaWebSocketStatus.CREATED, ZerodhaWebSocketStatus.DISCONNECTED, ZerodhaWebSocketStatus.STOPPED}:
                self._status = ZerodhaWebSocketStatus.STOPPED
                self._clear_retry_unlocked()
                return self.snapshot()
            self._status = ZerodhaWebSocketStatus.DISCONNECTING
            try:
                self._client.close()
            except Exception as exc:
                self._status = ZerodhaWebSocketStatus.ERROR
                self._record_error_unlocked(exc)
                raise
            self._status = ZerodhaWebSocketStatus.STOPPED
            self._clear_retry_unlocked()
            self._account_disconnect()
            return self.snapshot()

    def subscribe(
        self,
        subscription: ZerodhaInstrumentSubscription,
    ) -> ZerodhaWebSocketSnapshot:
        with self._lock:
            self._registry.add(subscription)
            if self.is_connected():
                try:
                    self._client.subscribe([subscription.instrument_token])
                    self._client.set_mode(self._mode_value(subscription.mode), [subscription.instrument_token])
                except Exception as exc:
                    self._registry.remove_by_token(subscription.instrument_token)
                    self._status = ZerodhaWebSocketStatus.ERROR
                    self._record_error_unlocked(exc)
                    raise
            return self.snapshot()

    def unsubscribe(
        self,
        instrument_token: int,
    ) -> ZerodhaWebSocketSnapshot:
        with self._lock:
            if self._registry.get_by_token(instrument_token) is None:
                raise ValueError("Unknown instrument token")
            if self.is_connected():
                try:
                    self._client.unsubscribe([instrument_token])
                except Exception as exc:
                    self._status = ZerodhaWebSocketStatus.ERROR
                    self._record_error_unlocked(exc)
                    raise
            self._registry.remove_by_token(instrument_token)
            return self.snapshot()

    def replace_subscriptions(
        self,
        subscriptions: tuple[ZerodhaInstrumentSubscription, ...],
    ) -> ZerodhaWebSocketSnapshot:
        proposed = ZerodhaSubscriptionRegistry(subscriptions)
        with self._lock:
            previous = self._registry.all()
            if self.is_connected():
                current_tokens = set(self._registry.tokens())
                proposed_tokens = set(proposed.tokens())
                to_unsubscribe = [token for token in self._registry.tokens() if token not in proposed_tokens]
                to_subscribe = [token for token in proposed.tokens() if token not in current_tokens]
                try:
                    if to_unsubscribe:
                        self._client.unsubscribe(to_unsubscribe)
                    if to_subscribe:
                        self._client.subscribe(to_subscribe)
                    for mode, tokens in self._mode_groups(proposed.all()).items():
                        changed = [
                            token
                            for token in tokens
                            if token in to_subscribe
                            or (
                                self._registry.get_by_token(token) is not None
                                and self._registry.get_by_token(token).mode is not proposed.get_by_token(token).mode
                            )
                        ]
                        if changed:
                            self._client.set_mode(self._mode_value(mode), changed)
                except Exception as exc:
                    self._registry.replace(previous)
                    self._status = ZerodhaWebSocketStatus.ERROR
                    self._record_error_unlocked(exc)
                    raise
            self._registry.replace(proposed.all())
            return self.snapshot()

    def process_raw_ticks(
        self,
        raw_ticks: Iterable[Mapping[str, object]],
    ) -> ZerodhaTickBatchResult:
        if isinstance(raw_ticks, (str, bytes, Mapping)):
            raise TypeError("raw_ticks must be an iterable batch of mappings")
        batch = tuple(raw_ticks)
        broker_received_at = self._now()
        broker_started_ns = perf_counter_ns()
        normalized_ticks = []
        delivered_ticks = []
        rejected = 0
        with self._lock:
            self._raw_tick_count += len(batch)
            self._broker_received_at = broker_received_at
            for raw_tick in batch:
                try:
                    tick = self._normalizer.normalize(raw_tick)
                    normalized_at = self._now()
                    normalized_ticks.append(tick)
                    self._normalized_tick_count += 1
                    self._last_tick_at = tick.timestamp
                    self._tick_exchange_timestamp = tick.timestamp
                    self._tick_normalized_at = normalized_at
                except Exception as exc:
                    rejected += 1
                    self._rejected_tick_count += 1
                    self._record_error_unlocked(exc)
                    continue
                try:
                    self._event_published_at = self._now()
                    self._tick_consumer(tick)
                    runtime_processed_at = self._now()
                    latency_ms = (perf_counter_ns() - broker_started_ns) / 1_000_000.0
                    self._runtime_processed_at = runtime_processed_at
                    self._latest_tick_latency_ms = latency_ms
                    self._max_tick_latency_ms = max(self._max_tick_latency_ms or 0.0, latency_ms)
                    delivered_ticks.append(tick)
                    self._delivered_tick_count += 1
                except Exception as exc:
                    rejected += 1
                    self._rejected_tick_count += 1
                    self._record_error_unlocked(exc)
                    continue
            return ZerodhaTickBatchResult(
                received_count=len(batch),
                normalized_ticks=tuple(normalized_ticks),
                delivered_ticks=tuple(delivered_ticks),
                rejected_count=rejected,
            )

    def snapshot(self) -> ZerodhaWebSocketSnapshot:
        with self._lock:
            return ZerodhaWebSocketSnapshot(
                status=self._status,
                connected=self._status is ZerodhaWebSocketStatus.CONNECTED,
                subscribed_instruments=self._registry.all(),
                connection_count=self._connection_count,
                disconnection_count=self._disconnection_count,
                reconnect_count=self._reconnect_count,
                raw_tick_count=self._raw_tick_count,
                normalized_tick_count=self._normalized_tick_count,
                delivered_tick_count=self._delivered_tick_count,
                rejected_tick_count=self._rejected_tick_count,
                retry_count=self._retry_count,
                reconnect_delay_seconds=self._reconnect_delay_seconds,
                suppressed_error_count=self._suppressed_error_count,
                client_instances_created=self._client_instances_created,
                connect_attempts=self._connect_attempts,
                successful_connections=self._successful_connections,
                disconnect_callbacks=self._disconnect_callbacks,
                error_callbacks=self._error_callbacks,
                retry_scheduled=self._retry_scheduled,
                subscriptions_applied=self._subscriptions_applied,
                duplicate_callbacks_suppressed=self._duplicate_callbacks_suppressed,
                last_connected_at=self._last_connected_at,
                last_disconnected_at=self._last_disconnected_at,
                reconnect_due_at=self._reconnect_due_at,
                last_tick_at=self._last_tick_at,
                last_error=self._last_error,
                broker_received_at=self._broker_received_at,
                tick_exchange_timestamp=self._tick_exchange_timestamp,
                tick_normalized_at=self._tick_normalized_at,
                event_published_at=self._event_published_at,
                runtime_processed_at=self._runtime_processed_at,
                latest_tick_latency_ms=self._latest_tick_latency_ms,
                max_tick_latency_ms=self._max_tick_latency_ms,
            )

    def is_connected(self) -> bool:
        with self._lock:
            return self._status is ZerodhaWebSocketStatus.CONNECTED

    def _on_connect(self, ws, response) -> None:
        with self._lock:
            if self._status is ZerodhaWebSocketStatus.CONNECTED and self._subscriptions_applied_for_connection:
                return
            self._status = ZerodhaWebSocketStatus.CONNECTED
            self._connection_count += 1
            self._successful_connections += 1
            self._disconnect_count_available = True
            self._last_connected_at = self._now()
            self._last_error = None
            self._last_error_fingerprint = None
            self._suppressed_error_count = 0
            self._clear_retry_unlocked()
            tokens = list(self._registry.tokens())
            try:
                if tokens:
                    self._client.subscribe(tokens)
                for mode, mode_tokens in self._mode_groups(self._registry.all()).items():
                    self._client.set_mode(self._mode_value(mode), list(mode_tokens))
                self._subscriptions_applied_for_connection = True
                self._subscriptions_applied += 1 if tokens else 0
            except Exception as exc:
                self._status = ZerodhaWebSocketStatus.ERROR
                self._record_error_unlocked(exc)
                raise

    def _on_ticks(self, ws, ticks) -> None:
        self.process_raw_ticks(ticks)

    def _on_close(self, ws, code, reason) -> None:
        with self._lock:
            self._disconnect_callbacks += 1
            if self._status in {ZerodhaWebSocketStatus.DISCONNECTING, ZerodhaWebSocketStatus.STOPPED}:
                self._status = ZerodhaWebSocketStatus.STOPPED
                self._clear_retry_unlocked()
                self._account_disconnect()
                return
            self._account_disconnect()
            self._record_error_unlocked(RuntimeError(f"WebSocket closed: {code} {reason}"))
            self._schedule_reconnect_unlocked()

    def _on_error(self, ws, code, reason) -> None:
        with self._lock:
            self._error_callbacks += 1
            if self._status in {ZerodhaWebSocketStatus.DISCONNECTING, ZerodhaWebSocketStatus.STOPPED}:
                return
            self._record_error_unlocked(RuntimeError(f"WebSocket error: {code} {reason}"))

    def _on_reconnect(self, ws, attempts_count) -> None:
        with self._lock:
            if self._status in {ZerodhaWebSocketStatus.DISCONNECTING, ZerodhaWebSocketStatus.STOPPED}:
                return
            self._schedule_reconnect_unlocked()

    def _on_noreconnect(self, ws) -> None:
        with self._lock:
            if self._status in {ZerodhaWebSocketStatus.DISCONNECTING, ZerodhaWebSocketStatus.STOPPED}:
                return
            self._status = ZerodhaWebSocketStatus.ERROR
            self._record_error_unlocked(RuntimeError("Zerodha WebSocket reconnect attempts exhausted"))

    def _mode_groups(
        self,
        subscriptions: tuple[ZerodhaInstrumentSubscription, ...],
    ) -> dict[ZerodhaSubscriptionMode, list[int]]:
        groups: dict[ZerodhaSubscriptionMode, list[int]] = defaultdict(list)
        for subscription in subscriptions:
            groups[subscription.mode].append(subscription.instrument_token)
        return dict(groups)

    def _mode_value(self, mode: ZerodhaSubscriptionMode) -> str:
        return {
            ZerodhaSubscriptionMode.LTP: KiteTickerClient.MODE_LTP,
            ZerodhaSubscriptionMode.QUOTE: KiteTickerClient.MODE_QUOTE,
            ZerodhaSubscriptionMode.FULL: KiteTickerClient.MODE_FULL,
        }[mode]

    def _reject_expired_session(self) -> None:
        if self._session.is_expired(self._now()):
            raise ValueError("Zerodha session is expired")

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock result must be datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock result must be timezone-aware")
        return value

    def _is_active_status(self) -> bool:
        return self._status in {
            ZerodhaWebSocketStatus.CONNECTING,
            ZerodhaWebSocketStatus.CONNECTED,
            ZerodhaWebSocketStatus.RECONNECTING,
            ZerodhaWebSocketStatus.RECONNECT_WAIT,
            ZerodhaWebSocketStatus.DISCONNECTING,
        }

    def _account_disconnect(self) -> None:
        if self._disconnect_count_available:
            self._disconnection_count += 1
            self._last_disconnected_at = self._now()
            self._disconnect_count_available = False

    def _safe_error(self, exc: Exception) -> str:
        message = f"{exc.__class__.__name__}: {exc}"
        for secret in (self._api_key, self._session.access_token):
            if secret:
                message = message.replace(secret, "[REDACTED]")
        if "{" in message or "}" in message:
            message = message.split("{", 1)[0].strip()
        return message

    def _record_error_unlocked(self, exc: Exception) -> None:
        message = self._safe_error(exc)
        if message == self._last_error_fingerprint:
            self._suppressed_error_count += 1
            self._duplicate_callbacks_suppressed += 1
            return
        self._last_error_fingerprint = message
        self._last_error = message

    def _schedule_reconnect_unlocked(self) -> None:
        if self._status in {ZerodhaWebSocketStatus.DISCONNECTING, ZerodhaWebSocketStatus.STOPPED}:
            return
        if self._status is ZerodhaWebSocketStatus.RECONNECT_WAIT:
            return
        self._status = ZerodhaWebSocketStatus.RECONNECT_WAIT
        self._reconnect_count += 1
        self._retry_count += 1
        self._retry_scheduled += 1
        delay = min(
            self._reconnect_initial_delay_seconds * (2 ** (self._retry_count - 1)),
            self._reconnect_max_delay_seconds,
        )
        self._reconnect_delay_seconds = delay
        self._reconnect_due_at = self._now() + timedelta(seconds=delay)
        self._subscriptions_applied_for_connection = False

    def _retry_due_unlocked(self) -> bool:
        return self._reconnect_due_at is None or self._now() >= self._reconnect_due_at

    def _clear_retry_unlocked(self) -> None:
        self._retry_count = 0
        self._reconnect_delay_seconds = 0
        self._reconnect_due_at = None

    def _require_positive_int(self, value: int, field_name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{field_name} must be a positive integer")
        return value
