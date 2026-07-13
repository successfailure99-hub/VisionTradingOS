"""
Lifecycle manager for option market-data subscriptions.
"""

from datetime import UTC, datetime
from threading import RLock

from brokers.zerodha.market_data import ZerodhaSubscriptionMode
from brokers.zerodha.option_market_data.enums import (
    ZerodhaOptionSubscriptionOperation,
    ZerodhaOptionSubscriptionStatus,
)
from brokers.zerodha.option_market_data.models import (
    ZerodhaOptionSubscriptionBatchResult,
    ZerodhaOptionSubscriptionEntry,
    ZerodhaOptionSubscriptionSnapshot,
    entries_from_universe,
)
from brokers.zerodha.option_market_data.planner import ZerodhaOptionSubscriptionPlanner
from brokers.zerodha.option_market_data.registry import ZerodhaOptionSubscriptionRegistry
from brokers.zerodha.option_market_data.transport import ZerodhaOptionSubscriptionTransportProtocol, to_kite_mode
from brokers.zerodha.options import ZerodhaOptionUniverse


class ZerodhaOptionMarketDataSubscriptionManager:
    def __init__(
        self,
        *,
        transport: ZerodhaOptionSubscriptionTransportProtocol,
        planner: ZerodhaOptionSubscriptionPlanner | None = None,
        registry: ZerodhaOptionSubscriptionRegistry | None = None,
        clock=None,
    ):
        for name in ("subscribe", "unsubscribe", "set_mode"):
            if not hasattr(transport, name):
                raise TypeError("transport must implement subscription methods")
        self._transport = transport
        self._planner = planner or ZerodhaOptionSubscriptionPlanner()
        if not isinstance(self._planner, ZerodhaOptionSubscriptionPlanner):
            raise TypeError("planner must be ZerodhaOptionSubscriptionPlanner")
        self._registry = registry or ZerodhaOptionSubscriptionRegistry()
        if not isinstance(self._registry, ZerodhaOptionSubscriptionRegistry):
            raise TypeError("registry must be ZerodhaOptionSubscriptionRegistry")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()
        self._status = ZerodhaOptionSubscriptionStatus.CREATED
        self._active = False
        self._operation_count = 0
        self._successful_operation_count = 0
        self._failed_operation_count = 0
        self._activation_count = 0
        self._replacement_count = 0
        self._deactivation_count = 0
        self._last_operation: ZerodhaOptionSubscriptionOperation | None = None
        self._last_result: ZerodhaOptionSubscriptionBatchResult | None = None
        self._last_started_at: datetime | None = None
        self._last_completed_at: datetime | None = None
        self._last_error: str | None = None

    def prepare(self, universe: ZerodhaOptionUniverse) -> ZerodhaOptionSubscriptionSnapshot:
        entries = entries_from_universe(universe)
        with self._lock:
            if self._active:
                current = self._registry.all()
                if current == entries:
                    return self._snapshot_unlocked()
                raise RuntimeError("use replace while active")
            try:
                self._begin(ZerodhaOptionSubscriptionOperation.PREPARE)
                self._registry.replace(entries)
                completed_at = self._now()
                self._status = ZerodhaOptionSubscriptionStatus.PREPARED
                self._successful_operation_count += 1
                self._last_completed_at = completed_at
                self._last_result = ZerodhaOptionSubscriptionBatchResult(
                    ZerodhaOptionSubscriptionOperation.PREPARE,
                    (),
                    (),
                    (),
                    (),
                    completed_at,
                )
                return self._snapshot_unlocked()
            except Exception as exc:
                self._record_failure(exc)
                raise

    def activate(self) -> ZerodhaOptionSubscriptionSnapshot:
        with self._lock:
            entries = self._registry.all()
            if self._active and entries:
                return self._snapshot_unlocked()
            if not entries:
                raise RuntimeError("no prepared option subscriptions")
            subscribed_tokens: tuple[int, ...] = ()
            try:
                self._begin(ZerodhaOptionSubscriptionOperation.ACTIVATE)
                self._status = ZerodhaOptionSubscriptionStatus.ACTIVATING
                subscribed_tokens = self._tokens(entries)
                self._transport.subscribe(list(subscribed_tokens))
                mode_tokens = self._apply_modes(entries)
                completed_at = self._now()
                self._active = True
                self._status = ZerodhaOptionSubscriptionStatus.ACTIVE
                self._successful_operation_count += 1
                self._activation_count += 1
                self._last_completed_at = completed_at
                self._last_result = ZerodhaOptionSubscriptionBatchResult(
                    ZerodhaOptionSubscriptionOperation.ACTIVATE,
                    subscribed_tokens,
                    (),
                    mode_tokens,
                    subscribed_tokens,
                    completed_at,
                )
                return self._snapshot_unlocked()
            except Exception as exc:
                rollback_error = None
                if subscribed_tokens:
                    try:
                        self._transport.unsubscribe(list(subscribed_tokens))
                    except Exception as rollback_exc:
                        rollback_error = rollback_exc
                self._active = False
                self._record_failure(exc, rollback_error=rollback_error)
                raise

    def replace(self, universe: ZerodhaOptionUniverse) -> ZerodhaOptionSubscriptionSnapshot:
        proposed = entries_from_universe(universe)
        with self._lock:
            if not self._active:
                raise RuntimeError("replace requires active subscriptions")
            current = self._registry.all()
            plan = self._planner.plan(current, proposed)
            if not plan.subscribe_entries and not plan.unsubscribe_entries and not plan.mode_change_entries:
                return self._snapshot_unlocked()
            subscribed = ()
            unsubscribed = ()
            changed = ()
            rollback_error = None
            try:
                self._begin(ZerodhaOptionSubscriptionOperation.REPLACE)
                self._status = ZerodhaOptionSubscriptionStatus.REPLACING
                subscribed = self._tokens(plan.subscribe_entries)
                if subscribed:
                    self._transport.subscribe(list(subscribed))
                changed_entries = plan.subscribe_entries + plan.mode_change_entries
                changed = self._apply_modes(changed_entries) if changed_entries else ()
                unsubscribed = self._tokens(plan.unsubscribe_entries)
                if unsubscribed:
                    self._transport.unsubscribe(list(unsubscribed))
                completed_at = self._now()
                self._registry.replace(proposed)
                self._status = ZerodhaOptionSubscriptionStatus.ACTIVE
                self._successful_operation_count += 1
                self._replacement_count += 1
                self._last_completed_at = completed_at
                self._last_result = ZerodhaOptionSubscriptionBatchResult(
                    ZerodhaOptionSubscriptionOperation.REPLACE,
                    subscribed,
                    unsubscribed,
                    changed,
                    self._tokens(proposed),
                    completed_at,
                )
                return self._snapshot_unlocked()
            except Exception as exc:
                rollback_error = self._rollback_replace(plan, subscribed, unsubscribed, changed) or rollback_error
                self._registry.replace(current)
                self._active = True
                self._record_failure(exc, rollback_error=rollback_error)
                raise

    def deactivate(self) -> ZerodhaOptionSubscriptionSnapshot:
        with self._lock:
            if not self._active:
                return self._snapshot_unlocked()
            entries = self._registry.all()
            tokens = self._tokens(entries)
            try:
                self._begin(ZerodhaOptionSubscriptionOperation.DEACTIVATE)
                self._status = ZerodhaOptionSubscriptionStatus.DEACTIVATING
                self._transport.unsubscribe(list(tokens))
                completed_at = self._now()
                self._active = False
                self._status = ZerodhaOptionSubscriptionStatus.INACTIVE
                self._successful_operation_count += 1
                self._deactivation_count += 1
                self._last_completed_at = completed_at
                self._last_result = ZerodhaOptionSubscriptionBatchResult(
                    ZerodhaOptionSubscriptionOperation.DEACTIVATE,
                    (),
                    tokens,
                    (),
                    (),
                    completed_at,
                )
                return self._snapshot_unlocked()
            except Exception as exc:
                self._active = True
                self._record_failure(exc)
                raise

    def snapshot(self) -> ZerodhaOptionSubscriptionSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def clear(self) -> ZerodhaOptionSubscriptionSnapshot:
        with self._lock:
            if self._active:
                raise RuntimeError("cannot clear active option subscriptions")
            self._registry.clear()
            self._status = ZerodhaOptionSubscriptionStatus.CLEARED
            self._active = False
            self._operation_count = 0
            self._successful_operation_count = 0
            self._failed_operation_count = 0
            self._activation_count = 0
            self._replacement_count = 0
            self._deactivation_count = 0
            self._last_operation = None
            self._last_result = None
            self._last_started_at = None
            self._last_completed_at = None
            self._last_error = None
            return self._snapshot_unlocked()

    def _begin(self, operation: ZerodhaOptionSubscriptionOperation) -> None:
        self._operation_count += 1
        self._last_operation = operation
        self._last_result = None
        self._last_error = None
        self._last_completed_at = None
        self._last_started_at = self._now()

    def _record_failure(self, exc: Exception, *, rollback_error: Exception | None = None) -> None:
        self._status = ZerodhaOptionSubscriptionStatus.ERROR
        self._failed_operation_count += 1
        error = _safe_error(exc)
        if rollback_error is not None:
            error = f"{error}; rollback: {_safe_error(rollback_error)}"
        self._last_error = error
        try:
            self._last_completed_at = self._now()
        except Exception:
            self._last_completed_at = None

    def _snapshot_unlocked(self) -> ZerodhaOptionSubscriptionSnapshot:
        entries = self._registry.all()
        underlying = entries[0].contract.underlying if entries else None
        expiry = entries[0].contract.expiry if entries else None
        return ZerodhaOptionSubscriptionSnapshot(
            status=self._status,
            underlying=underlying,
            expiry=expiry,
            entries=entries,
            active=self._active,
            prepared=bool(entries),
            operation_count=self._operation_count,
            successful_operation_count=self._successful_operation_count,
            failed_operation_count=self._failed_operation_count,
            activation_count=self._activation_count,
            replacement_count=self._replacement_count,
            deactivation_count=self._deactivation_count,
            subscribed_token_count=len(entries),
            last_operation=self._last_operation,
            last_result=self._last_result,
            last_started_at=self._last_started_at,
            last_completed_at=self._last_completed_at,
            last_error=self._last_error,
        )

    def _apply_modes(self, entries: tuple[ZerodhaOptionSubscriptionEntry, ...]) -> tuple[int, ...]:
        mode_order: list[ZerodhaSubscriptionMode] = []
        grouped: dict[ZerodhaSubscriptionMode, list[int]] = {}
        for entry in entries:
            mode = entry.subscription.mode
            if mode not in grouped:
                grouped[mode] = []
                mode_order.append(mode)
            grouped[mode].append(entry.subscription.instrument_token)
        updated: list[int] = []
        for mode in mode_order:
            tokens = grouped[mode]
            self._transport.set_mode(to_kite_mode(mode), tokens)
            updated.extend(tokens)
        return tuple(updated)

    def _rollback_replace(self, plan, subscribed, unsubscribed, changed) -> Exception | None:
        try:
            if unsubscribed:
                self._transport.subscribe(list(unsubscribed))
                self._apply_modes(plan.unsubscribe_entries)
            retained_changed = tuple(
                entry
                for entry in plan.current_entries
                if entry.subscription.instrument_token in {item.subscription.instrument_token for item in plan.mode_change_entries}
            )
            if retained_changed:
                self._apply_modes(retained_changed)
            if subscribed:
                self._transport.unsubscribe(list(subscribed))
            return None
        except Exception as exc:
            return exc

    def _tokens(self, entries: tuple[ZerodhaOptionSubscriptionEntry, ...]) -> tuple[int, ...]:
        return tuple(entry.subscription.instrument_token for entry in entries)

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock result must be datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock result must be timezone-aware")
        return value


def _safe_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message
