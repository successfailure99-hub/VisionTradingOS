"""
Synchronous coordinator for live option-chain runtime integration.
"""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from math import isfinite
from numbers import Real
from threading import RLock

from application.enums import RuntimeStatus
from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data import LiveMarketDataRuntime
from application.live_market_data.enums import LiveMarketDataRuntimeStatus
from application.live_option_chain import LiveOptionChainRuntime, LiveOptionChainStatus
from application.live_option_chain_integration.configuration import (
    LiveOptionChainIntegrationConfiguration,
)
from application.live_option_chain_integration.enums import (
    LiveOptionChainDeliveryKind,
    LiveOptionChainIntegrationStatus,
)
from application.live_option_chain_integration.models import (
    LiveOptionChainDeliveryResult,
    LiveOptionChainIntegrationSnapshot,
)
from brokers.zerodha.option_market_data import ZerodhaOptionMarketDataSubscriptionManager
from brokers.zerodha.options.models import SUPPORTED_UNDERLYINGS
from core.models.tick import Tick


class LiveOptionChainIntegrationCoordinator:
    def __init__(
        self,
        *,
        lifecycle: ApplicationLifecycleManager,
        subscription_manager: ZerodhaOptionMarketDataSubscriptionManager,
        live_option_chain_runtime: LiveOptionChainRuntime,
        live_market_data_runtime: LiveMarketDataRuntime | None = None,
        configuration: LiveOptionChainIntegrationConfiguration | None = None,
        clock=None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be ApplicationLifecycleManager")
        if not isinstance(subscription_manager, ZerodhaOptionMarketDataSubscriptionManager):
            raise TypeError("subscription_manager must be ZerodhaOptionMarketDataSubscriptionManager")
        if not isinstance(live_option_chain_runtime, LiveOptionChainRuntime):
            raise TypeError("live_option_chain_runtime must be LiveOptionChainRuntime")
        if live_market_data_runtime is not None and not isinstance(live_market_data_runtime, LiveMarketDataRuntime):
            raise TypeError("live_market_data_runtime must be LiveMarketDataRuntime or None")
        self._lifecycle = lifecycle
        self._subscription_manager = subscription_manager
        self._live_option_chain_runtime = live_option_chain_runtime
        self._live_market_data_runtime = live_market_data_runtime
        self._configuration = configuration or LiveOptionChainIntegrationConfiguration()
        if not isinstance(self._configuration, LiveOptionChainIntegrationConfiguration):
            raise TypeError("configuration must be LiveOptionChainIntegrationConfiguration")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()
        self._status = LiveOptionChainIntegrationStatus.CREATED
        self._start_count = 0
        self._stop_count = 0
        self._validation_count = 0
        self._underlying_price_delivery_count = 0
        self._option_batch_delivery_count = 0
        self._delivered_option_tick_count = 0
        self._rejected_option_tick_count = 0
        self._last_started_at: datetime | None = None
        self._last_stopped_at: datetime | None = None
        self._last_delivery_at: datetime | None = None
        self._last_delivery: LiveOptionChainDeliveryResult | None = None
        self._last_error: str | None = None
        self._validate_static_identity()

    @property
    def lifecycle(self) -> ApplicationLifecycleManager:
        return self._lifecycle

    @property
    def subscription_manager(
        self,
    ) -> ZerodhaOptionMarketDataSubscriptionManager:
        return self._subscription_manager

    @property
    def live_option_chain_runtime(self) -> LiveOptionChainRuntime:
        return self._live_option_chain_runtime

    @property
    def live_market_data_runtime(self) -> LiveMarketDataRuntime | None:
        return self._live_market_data_runtime

    def validate(self) -> LiveOptionChainIntegrationSnapshot:
        with self._lock:
            self._status = LiveOptionChainIntegrationStatus.VALIDATING
            try:
                lifecycle_snapshot = self._lifecycle.snapshot()
                subscription_snapshot = self._subscription_manager.snapshot()
                option_snapshot = self._live_option_chain_runtime.snapshot()
                market_snapshot = (
                    self._live_market_data_runtime.snapshot()
                    if self._live_market_data_runtime is not None
                    else None
                )
                self._validate_snapshots(
                    lifecycle_snapshot,
                    subscription_snapshot,
                    option_snapshot,
                    market_snapshot,
                )
            except Exception as exc:
                self._status = LiveOptionChainIntegrationStatus.ERROR
                self._last_error = _safe_error(exc)
                raise
            self._validation_count += 1
            self._last_error = None
            self._status = LiveOptionChainIntegrationStatus.READY
            return self._build_snapshot(
                lifecycle_snapshot,
                subscription_snapshot,
                option_snapshot,
                market_snapshot,
            )

    def start(self) -> LiveOptionChainIntegrationSnapshot:
        with self._lock:
            if self._status is LiveOptionChainIntegrationStatus.RUNNING:
                return self.snapshot()
            started = False
            try:
                self.validate()
                self._status = LiveOptionChainIntegrationStatus.STARTING
                option_snapshot = self._live_option_chain_runtime.start()
                started = True
                if option_snapshot.status not in {
                    LiveOptionChainStatus.COLLECTING,
                    LiveOptionChainStatus.PARTIAL,
                    LiveOptionChainStatus.READY,
                    LiveOptionChainStatus.STALE,
                }:
                    raise RuntimeError("live option runtime did not enter a running state")
                started_at = self._now()
            except Exception as exc:
                cleanup_error = None
                if started:
                    try:
                        self._live_option_chain_runtime.stop()
                    except Exception as cleanup_exc:
                        cleanup_error = cleanup_exc
                self._status = LiveOptionChainIntegrationStatus.ERROR
                self._last_error = _format_error(exc, cleanup_error)
                raise
            self._start_count += 1
            self._last_started_at = started_at
            self._last_error = None
            self._status = LiveOptionChainIntegrationStatus.RUNNING
            return self.snapshot()

    def stop(self) -> LiveOptionChainIntegrationSnapshot:
        with self._lock:
            if self._status in {
                LiveOptionChainIntegrationStatus.STOPPED,
                LiveOptionChainIntegrationStatus.CREATED,
                LiveOptionChainIntegrationStatus.CLEARED,
            }:
                self._status = LiveOptionChainIntegrationStatus.STOPPED
                return self.snapshot()
            try:
                self._status = LiveOptionChainIntegrationStatus.STOPPING
                if self._configuration.stop_live_option_runtime_on_shutdown:
                    self._live_option_chain_runtime.stop()
                stopped_at = self._now()
                if self._configuration.deactivate_option_subscriptions_on_shutdown:
                    self._subscription_manager.deactivate()
            except Exception as exc:
                self._status = LiveOptionChainIntegrationStatus.ERROR
                self._last_error = _safe_error(exc)
                raise
            self._stop_count += 1
            self._last_stopped_at = stopped_at
            self._status = LiveOptionChainIntegrationStatus.STOPPED
            self._last_error = None
            return self.snapshot()

    def restart(self) -> LiveOptionChainIntegrationSnapshot:
        with self._lock:
            self.stop()
            self.validate()
            return self.start()

    def deliver_underlying_price(
        self,
        price: float,
        *,
        timestamp: datetime | None = None,
    ) -> LiveOptionChainDeliveryResult:
        with self._lock:
            self._require_running()
            value = _positive_float(price, "underlying price")
            completed_at = self._now()
            delivery_timestamp = timestamp or completed_at
            _aware(delivery_timestamp, "timestamp")
            try:
                option_snapshot = self._live_option_chain_runtime.set_underlying_price(
                    value,
                    timestamp=delivery_timestamp,
                )
            except Exception as exc:
                self._last_error = _safe_error(exc)
                raise
            result = LiveOptionChainDeliveryResult(
                kind=LiveOptionChainDeliveryKind.UNDERLYING_PRICE,
                accepted=True,
                delivered_count=1,
                rejected_count=0,
                runtime_status=option_snapshot.status,
                completed_at=completed_at,
            )
            self._underlying_price_delivery_count += 1
            self._last_delivery_at = completed_at
            self._last_delivery = result
            self._last_error = None
            return result

    def deliver_underlying_tick(
        self,
        tick: Tick,
    ) -> LiveOptionChainDeliveryResult:
        if not isinstance(tick, Tick):
            raise TypeError("tick must be Tick")
        underlying = self._live_option_chain_runtime.snapshot().underlying
        if tick.symbol is not underlying:
            raise ValueError("tick instrument does not match live option-chain underlying")
        return self.deliver_underlying_price(tick.last_price, timestamp=tick.timestamp)

    def deliver_option_ticks(
        self,
        raw_ticks: Iterable[Mapping[str, object]],
    ) -> LiveOptionChainDeliveryResult:
        if isinstance(raw_ticks, (str, bytes, Mapping)):
            raise TypeError("raw_ticks must be an iterable of mappings")
        rows = tuple(raw_ticks)
        with self._lock:
            self._require_running()
            completed_at = self._now()
            try:
                batch = self._live_option_chain_runtime.process_raw_ticks(rows)
                option_snapshot = self._live_option_chain_runtime.snapshot()
            except Exception as exc:
                self._last_error = _safe_error(exc)
                raise
            delivered = len(batch.accepted_quotes)
            result = LiveOptionChainDeliveryResult(
                kind=LiveOptionChainDeliveryKind.OPTION_TICK_BATCH,
                accepted=delivered > 0,
                delivered_count=delivered,
                rejected_count=batch.rejected_count,
                runtime_status=option_snapshot.status,
                completed_at=completed_at,
                option_batch_result=batch,
            )
            self._option_batch_delivery_count += 1
            self._delivered_option_tick_count += delivered
            self._rejected_option_tick_count += batch.rejected_count
            self._last_delivery_at = completed_at
            self._last_delivery = result
            self._last_error = None
            return result

    def snapshot(self) -> LiveOptionChainIntegrationSnapshot:
        with self._lock:
            lifecycle_snapshot = self._lifecycle.snapshot()
            subscription_snapshot = self._subscription_manager.snapshot()
            option_snapshot = self._live_option_chain_runtime.snapshot()
            market_snapshot = (
                self._live_market_data_runtime.snapshot()
                if self._live_market_data_runtime is not None
                else None
            )
            return self._build_snapshot(
                lifecycle_snapshot,
                subscription_snapshot,
                option_snapshot,
                market_snapshot,
            )

    def clear(self) -> LiveOptionChainIntegrationSnapshot:
        with self._lock:
            if self._status is not LiveOptionChainIntegrationStatus.STOPPED:
                raise RuntimeError("clear requires stopped integration")
            self._live_option_chain_runtime.clear()
            self._start_count = 0
            self._stop_count = 0
            self._validation_count = 0
            self._underlying_price_delivery_count = 0
            self._option_batch_delivery_count = 0
            self._delivered_option_tick_count = 0
            self._rejected_option_tick_count = 0
            self._last_started_at = None
            self._last_stopped_at = None
            self._last_delivery_at = None
            self._last_delivery = None
            self._last_error = None
            self._status = LiveOptionChainIntegrationStatus.CLEARED
            return self.snapshot()

    def _validate_static_identity(self) -> None:
        if (
            self._live_market_data_runtime is not None
            and self._live_market_data_runtime.lifecycle is not self._lifecycle
        ):
            raise ValueError("live market-data runtime must use the same lifecycle")
        subscription_snapshot = self._subscription_manager.snapshot()
        option_snapshot = self._live_option_chain_runtime.snapshot()
        if option_snapshot.underlying not in SUPPORTED_UNDERLYINGS:
            raise ValueError("unsupported live option-chain underlying")
        if subscription_snapshot.entries:
            first = subscription_snapshot.entries[0]
            if first.contract.underlying is not option_snapshot.underlying:
                raise ValueError("option subscription underlying mismatch")
            if first.contract.expiry != option_snapshot.expiry:
                raise ValueError("option subscription expiry mismatch")
            if len(subscription_snapshot.entries) != option_snapshot.configured_token_count:
                raise ValueError("option subscription token count mismatch")

    def _validate_snapshots(
        self,
        lifecycle_snapshot,
        subscription_snapshot,
        option_snapshot,
        market_snapshot,
    ) -> None:
        if (
            self._configuration.require_application_running
            and lifecycle_snapshot.status is not RuntimeStatus.RUNNING
        ):
            raise RuntimeError("application lifecycle must be RUNNING")
        if not subscription_snapshot.active:
            raise RuntimeError("option subscriptions must be active")
        if option_snapshot.status in {LiveOptionChainStatus.ERROR, LiveOptionChainStatus.CLEARED}:
            raise RuntimeError("live option runtime is not valid for integration")
        if option_snapshot.underlying not in SUPPORTED_UNDERLYINGS:
            raise ValueError("unsupported live option-chain underlying")
        if subscription_snapshot.entries:
            first = subscription_snapshot.entries[0]
            if first.contract.underlying is not option_snapshot.underlying:
                raise ValueError("option subscription underlying mismatch")
            if first.contract.expiry != option_snapshot.expiry:
                raise ValueError("option subscription expiry mismatch")
            if len(subscription_snapshot.entries) != option_snapshot.configured_token_count:
                raise ValueError("option subscription token count mismatch")
        if (
            self._configuration.require_live_market_data_running_for_spot
            and (
                market_snapshot is None
                or market_snapshot.status is not LiveMarketDataRuntimeStatus.RUNNING
            )
        ):
            raise RuntimeError("live market-data runtime must be RUNNING")

    def _build_snapshot(
        self,
        lifecycle_snapshot,
        subscription_snapshot,
        option_snapshot,
        market_snapshot,
    ) -> LiveOptionChainIntegrationSnapshot:
        application_ready = (
            not self._configuration.require_application_running
            or lifecycle_snapshot.status is RuntimeStatus.RUNNING
        )
        option_runtime_startable = option_snapshot.status in {
            LiveOptionChainStatus.CREATED,
            LiveOptionChainStatus.CONFIGURED,
            LiveOptionChainStatus.COLLECTING,
            LiveOptionChainStatus.PARTIAL,
            LiveOptionChainStatus.READY,
            LiveOptionChainStatus.STALE,
        }
        ready = (
            self._status
            in {
                LiveOptionChainIntegrationStatus.READY,
                LiveOptionChainIntegrationStatus.RUNNING,
            }
            and application_ready
            and subscription_snapshot.active
            and option_runtime_startable
        )
        return LiveOptionChainIntegrationSnapshot(
            status=self._status,
            application_status=lifecycle_snapshot.status,
            live_market_data_status=market_snapshot.status if market_snapshot is not None else None,
            option_subscription_status=subscription_snapshot.status,
            option_subscriptions_active=subscription_snapshot.active,
            live_option_chain_status=option_snapshot.status,
            running=self._status is LiveOptionChainIntegrationStatus.RUNNING,
            ready=ready,
            underlying=option_snapshot.underlying,
            expiry=option_snapshot.expiry,
            configured_option_token_count=option_snapshot.configured_token_count,
            quoted_option_token_count=option_snapshot.quoted_token_count,
            complete_pair_count=option_snapshot.complete_pair_count,
            expected_pair_count=option_snapshot.expected_pair_count,
            underlying_price=option_snapshot.underlying_price,
            start_count=self._start_count,
            stop_count=self._stop_count,
            validation_count=self._validation_count,
            underlying_price_delivery_count=self._underlying_price_delivery_count,
            option_batch_delivery_count=self._option_batch_delivery_count,
            delivered_option_tick_count=self._delivered_option_tick_count,
            rejected_option_tick_count=self._rejected_option_tick_count,
            last_started_at=self._last_started_at,
            last_stopped_at=self._last_stopped_at,
            last_delivery_at=self._last_delivery_at,
            last_delivery=self._last_delivery,
            option_chain=option_snapshot,
            last_error=self._last_error,
        )

    def _require_running(self) -> None:
        if self._status is not LiveOptionChainIntegrationStatus.RUNNING:
            raise RuntimeError("live option-chain integration must be RUNNING")

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock result must be datetime")
        return _aware(value, "clock result")


def _positive_float(value: Real, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be positive finite number")
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{field_name} must be positive finite number")
    return number


def _aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _safe_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message


def _format_error(original: Exception, cleanup: Exception | None) -> str:
    message = _safe_error(original)
    if cleanup is not None:
        message = f"{message}; cleanup failed: {_safe_error(cleanup)}"
    return message
