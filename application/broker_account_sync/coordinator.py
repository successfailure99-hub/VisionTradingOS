"""
Read-only broker account synchronization coordinator.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import RLock

from brokers.zerodha.auth.enums import ZerodhaAuthStatus

from .enums import (
    BrokerConnectionState,
    BrokerMutationMode,
    BrokerReconciliationStatus,
    BrokerRuntimeStatus,
    BrokerSessionState,
)
from .models import (
    BrokerAccountSnapshot,
    BrokerHoldingSnapshot,
    BrokerOrderStatusSnapshot,
    BrokerPositionSnapshot,
    BrokerReconciliationSnapshot,
    BrokerRuntimeVerificationStage,
    mask_account_id,
)


@dataclass(frozen=True, slots=True)
class BrokerAccountSyncPolicy:
    stale_after_seconds: float = 120.0
    minimum_refresh_interval_seconds: float = 5.0
    max_retry_count: int = 3
    retry_backoff_seconds: float = 2.0

    def __post_init__(self) -> None:
        for name in ("stale_after_seconds", "minimum_refresh_interval_seconds", "retry_backoff_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"{name} must be a non-negative number")
            object.__setattr__(self, name, float(value))
        if isinstance(self.max_retry_count, bool) or not isinstance(self.max_retry_count, int) or self.max_retry_count < 0:
            raise ValueError("max_retry_count must be a non-negative integer")


class BrokerAccountSyncCoordinator:
    def __init__(self, *, broker: str = "ZERODHA", policy: BrokerAccountSyncPolicy | None = None):
        self._broker = _text(broker, "broker")
        self._policy = policy or BrokerAccountSyncPolicy()
        self._lock = RLock()
        self._client = None
        self._auth_snapshot = None
        self._last_snapshot: BrokerAccountSnapshot | None = None
        self._last_valid_snapshot: BrokerAccountSnapshot | None = None
        self._last_refresh_attempt: datetime | None = None
        self._retry_count = 0
        self._refreshing = False
        self._last_error: str | None = None

    @property
    def retry_count(self) -> int:
        with self._lock:
            return self._retry_count

    @property
    def mutation_mode(self) -> BrokerMutationMode:
        return BrokerMutationMode.DISABLED

    def configure_client(self, client) -> None:
        with self._lock:
            self._client = client
            self._last_error = None

    def observe_authentication(self, auth_snapshot) -> BrokerAccountSnapshot:
        with self._lock:
            self._auth_snapshot = auth_snapshot
            now = _snapshot_time(auth_snapshot) or _now()
            return self._status_snapshot(now, self._session_state(auth_snapshot), "Authentication state updated.")

    def refresh(self, *, timestamp: datetime | None = None, force: bool = False) -> BrokerAccountSnapshot:
        now = _aware(timestamp or _now(), "timestamp")
        with self._lock:
            if self._refreshing:
                return self._status_snapshot(now, self._current_session_state(), "Refresh already in progress.", status=BrokerRuntimeStatus.WAITING)
            if not force and self._last_refresh_attempt is not None:
                elapsed = (now - self._last_refresh_attempt).total_seconds()
                if elapsed < self._policy.minimum_refresh_interval_seconds:
                    return self._last_snapshot or self._status_snapshot(now, self._current_session_state(), "Refresh suppressed by deterministic interval.")
            self._last_refresh_attempt = now
            self._refreshing = True
        try:
            snapshot = self._refresh_unlocked(now)
            with self._lock:
                self._last_snapshot = snapshot
                self._last_valid_snapshot = snapshot
                self._retry_count = 0
                self._last_error = None
                return snapshot
        except Exception as exc:
            with self._lock:
                self._retry_count = min(self._retry_count + 1, self._policy.max_retry_count)
                self._last_error = _safe_error(exc)
                return self._failure_snapshot(now, self._last_error)
        finally:
            with self._lock:
                self._refreshing = False

    def mark_stale(self, *, timestamp: datetime | None = None, reason: str = "Broker account data is stale.") -> BrokerAccountSnapshot:
        now = _aware(timestamp or _now(), "timestamp")
        with self._lock:
            if self._last_valid_snapshot is None:
                return self._status_snapshot(now, self._current_session_state(), reason, status=BrokerRuntimeStatus.STALE)
            stale = replace(
                self._last_valid_snapshot,
                timestamp=now,
                data_age=_age(self._last_valid_snapshot.latest_refresh_timestamp, now),
                is_stale=True,
                blocking_reason=_text(reason, "reason"),
                reconciliation=self._last_valid_snapshot.reconciliation,
            )
            self._last_snapshot = stale
            return stale

    def snapshot(self, *, timestamp: datetime | None = None) -> BrokerAccountSnapshot:
        now = _aware(timestamp or _now(), "timestamp")
        with self._lock:
            if self._last_snapshot is None:
                return self._status_snapshot(now, self._current_session_state(), "Broker account sync has not refreshed yet.")
            if self._last_snapshot.latest_refresh_timestamp is None:
                return self._last_snapshot
            if _age(self._last_snapshot.latest_refresh_timestamp, now) > self._policy.stale_after_seconds:
                return self.mark_stale(timestamp=now)
            return self._last_snapshot

    def verification_report(self, *, timestamp: datetime | None = None) -> tuple[BrokerRuntimeVerificationStage, ...]:
        snapshot = self.snapshot(timestamp=timestamp)
        auth_status = _auth_status(snapshot)
        connection_status = _connection_status(snapshot)
        data_status = BrokerRuntimeStatus.STALE if snapshot.is_stale else (BrokerRuntimeStatus.READY if snapshot.latest_refresh_timestamp else BrokerRuntimeStatus.WAITING)
        mutation_status = BrokerRuntimeStatus.DISABLED
        rows = (
            ("BROKER_AUTH", "ApplicationOrchestrator", "ZerodhaSessionManager", "BrokerAccountSync", auth_status, _auth_reason(snapshot)),
            ("BROKER_CONNECTION", "ApplicationOrchestrator", "ZerodhaReadOnlyAdapter", "BrokerAccountSync", connection_status, snapshot.blocking_reason),
            ("BROKER_MARGINS", "BrokerAccountSyncCoordinator", "ReadOnlyBrokerClient.margins", "RuntimeSnapshot", data_status, snapshot.blocking_reason),
            ("BROKER_POSITIONS", "BrokerAccountSyncCoordinator", "ReadOnlyBrokerClient.positions", "RuntimeSnapshot", data_status, snapshot.blocking_reason),
            ("BROKER_HOLDINGS", "BrokerAccountSyncCoordinator", "ReadOnlyBrokerClient.holdings", "RuntimeSnapshot", data_status, snapshot.blocking_reason),
            ("BROKER_ORDERS", "BrokerAccountSyncCoordinator", "ReadOnlyBrokerClient.orders", "RuntimeSnapshot", data_status, snapshot.blocking_reason),
            ("BROKER_ACCOUNT_SYNC", "ApplicationOrchestrator", "BrokerAccountSyncCoordinator", "Dashboard", data_status, snapshot.blocking_reason),
            ("BROKER_MUTATION_MODE", "ApplicationOrchestrator", "ProductionSafety", "Dashboard", mutation_status, "Broker Mutation Mode: DISABLED"),
        )
        return tuple(
            BrokerRuntimeVerificationStage(
                stage=stage,
                owner=owner,
                producer=producer,
                consumer=consumer,
                timestamp=snapshot.timestamp,
                status=status,
                data_age=snapshot.data_age,
                recovery_state="LAST_VALID_PRESERVED" if snapshot.is_stale and self._last_valid_snapshot is not None else "NONE",
                blocking_reason=reason,
            )
            for stage, owner, producer, consumer, status, reason in rows
        )

    def reconcile_paper_position(self, paper_position) -> BrokerReconciliationSnapshot:
        with self._lock:
            snapshot = self._last_snapshot
        reconciliation = reconcile_paper_and_broker(paper_position, snapshot)
        with self._lock:
            if self._last_snapshot is not None:
                self._last_snapshot = replace(self._last_snapshot, reconciliation=reconciliation)
        return reconciliation

    def reset(self) -> None:
        with self._lock:
            self._last_snapshot = None
            self._last_valid_snapshot = None
            self._last_refresh_attempt = None
            self._retry_count = 0
            self._refreshing = False
            self._last_error = None

    def _refresh_unlocked(self, now: datetime) -> BrokerAccountSnapshot:
        with self._lock:
            client = self._client
            auth_snapshot = self._auth_snapshot
        session_state = self._session_state(auth_snapshot, reference_time=now)
        if session_state is not BrokerSessionState.AUTHENTICATED:
            return self._status_snapshot(now, session_state, _auth_blocking_reason(session_state), status=BrokerRuntimeStatus.BLOCKED)
        if client is None:
            return self._status_snapshot(now, session_state, "Read-only broker client is unavailable.", status=BrokerRuntimeStatus.WAITING)
        _assert_read_only_client(client)
        margins_raw = client.margins()
        positions_raw = client.positions()
        holdings_raw = client.holdings()
        orders_raw = client.orders()
        account_id = _client_account_id(client, auth_snapshot)
        positions = tuple(_position(item) for item in _sequence(positions_raw, "positions"))
        holdings = tuple(_holding(item) for item in _sequence(holdings_raw, "holdings"))
        orders = tuple(_order(item) for item in _sequence(orders_raw, "orders"))
        equity_available, equity_used, commodity_available, commodity_used = _margins(margins_raw)
        total = equity_available + commodity_available
        return BrokerAccountSnapshot(
            broker=self._broker,
            account_id_masked=mask_account_id(account_id),
            timestamp=now,
            session_state=session_state,
            connection_state=BrokerConnectionState.READY,
            authentication_state=session_state,
            equity_available=equity_available,
            equity_used=equity_used,
            commodity_available=commodity_available,
            commodity_used=commodity_used,
            total_available_margin=total,
            positions=positions,
            holdings=holdings,
            orders=orders,
            latest_refresh_timestamp=now,
            data_age=0.0,
            is_stale=False,
            blocking_reason="-",
            mutation_mode=BrokerMutationMode.DISABLED,
            reconciliation=reconcile_paper_and_broker(None, None),
        )

    def _current_session_state(self) -> BrokerSessionState:
        return self._session_state(self._auth_snapshot)

    def _session_state(self, auth_snapshot, *, reference_time: datetime | None = None) -> BrokerSessionState:
        status = getattr(auth_snapshot, "status", None)
        if status is ZerodhaAuthStatus.AUTHENTICATED:
            expires_at = getattr(auth_snapshot, "expires_at", None)
            if expires_at is not None and expires_at <= (reference_time or _now()):
                return BrokerSessionState.TOKEN_EXPIRED
            return BrokerSessionState.AUTHENTICATED
        if status is ZerodhaAuthStatus.AUTHENTICATING:
            return BrokerSessionState.AUTHENTICATING
        if status is ZerodhaAuthStatus.EXPIRED:
            return BrokerSessionState.TOKEN_EXPIRED
        if status is ZerodhaAuthStatus.ERROR:
            return BrokerSessionState.SESSION_INVALID
        return BrokerSessionState.UNAUTHENTICATED

    def _status_snapshot(self, now: datetime, session_state: BrokerSessionState, reason: str, *, status: BrokerRuntimeStatus | None = None) -> BrokerAccountSnapshot:
        connection = BrokerConnectionState.WAITING
        if session_state in {BrokerSessionState.SESSION_INVALID, BrokerSessionState.FAILED}:
            connection = BrokerConnectionState.FAILED
        elif session_state is BrokerSessionState.RECONNECTING:
            connection = BrokerConnectionState.RECONNECTING
        elif session_state is BrokerSessionState.AUTHENTICATED:
            connection = BrokerConnectionState.WAITING
        return BrokerAccountSnapshot(
            broker=self._broker,
            account_id_masked="-",
            timestamp=now,
            session_state=session_state,
            connection_state=connection,
            authentication_state=session_state,
            equity_available=0.0,
            equity_used=0.0,
            commodity_available=0.0,
            commodity_used=0.0,
            total_available_margin=0.0,
            positions=(),
            holdings=(),
            orders=(),
            latest_refresh_timestamp=None,
            data_age=None,
            is_stale=status is BrokerRuntimeStatus.STALE,
            blocking_reason=reason,
            mutation_mode=BrokerMutationMode.DISABLED,
            reconciliation=reconcile_paper_and_broker(None, None),
        )

    def _failure_snapshot(self, now: datetime, reason: str) -> BrokerAccountSnapshot:
        if self._last_valid_snapshot is not None:
            stale = replace(
                self._last_valid_snapshot,
                timestamp=now,
                data_age=_age(self._last_valid_snapshot.latest_refresh_timestamp, now),
                is_stale=True,
                blocking_reason=reason,
            )
            self._last_snapshot = stale
            return stale
        return self._status_snapshot(now, BrokerSessionState.FAILED, reason, status=BrokerRuntimeStatus.FAILED)


def reconcile_paper_and_broker(paper_position, account_snapshot: BrokerAccountSnapshot | None) -> BrokerReconciliationSnapshot:
    if paper_position is None and account_snapshot is None:
        return BrokerReconciliationSnapshot(False, False, False, False, False, BrokerReconciliationStatus.NOT_APPLICABLE)
    if account_snapshot is None or account_snapshot.is_stale:
        return BrokerReconciliationSnapshot(paper_position is not None, False, False, False, False, BrokerReconciliationStatus.BROKER_UNAVAILABLE, "Broker account snapshot unavailable.")
    paper_present = paper_position is not None and str(getattr(paper_position, "status", "")).lower() in {"open", "partially_closed", "objective_reached"}
    broker_positions = tuple(position for position in account_snapshot.positions if position.quantity != 0)
    broker_present = bool(broker_positions)
    if paper_present and not broker_present:
        return BrokerReconciliationSnapshot(True, False, False, False, False, BrokerReconciliationStatus.PAPER_ONLY)
    if broker_present and not paper_present:
        return BrokerReconciliationSnapshot(False, True, False, False, False, BrokerReconciliationStatus.BROKER_ONLY)
    if not paper_present and not broker_present:
        return BrokerReconciliationSnapshot(False, False, False, False, False, BrokerReconciliationStatus.NOT_APPLICABLE)
    paper_instrument = str(getattr(getattr(paper_position, "instrument", None), "value", getattr(paper_position, "instrument", ""))).upper()
    paper_quantity = abs(int(getattr(paper_position, "quantity", 0)))
    paper_direction = str(getattr(paper_position, "direction", "")).lower()
    broker = broker_positions[0]
    instrument_match = broker.instrument.upper() == paper_instrument
    quantity_match = abs(broker.quantity) == paper_quantity
    direction_match = (broker.quantity > 0 and "long" in paper_direction) or (broker.quantity < 0 and "short" in paper_direction)
    status = BrokerReconciliationStatus.MATCHED if instrument_match and quantity_match and direction_match else BrokerReconciliationStatus.MISMATCHED
    return BrokerReconciliationSnapshot(True, True, instrument_match, quantity_match, direction_match, status)


def _assert_read_only_client(client) -> None:
    for name in ("place_order", "modify_order", "cancel_order", "exit_position"):
        method = getattr(client, name, None)
        if method is not None and not getattr(method, "read_only_disabled", False):
            raise ValueError(f"Read-only broker account client exposes mutation method: {name}")


def _margins(raw) -> tuple[float, float, float, float]:
    mapping = _mapping(raw, "margins")
    equity = _mapping(mapping.get("equity", {}), "equity margins")
    commodity = _mapping(mapping.get("commodity", {}), "commodity margins")
    return (
        _float_from(equity, "available"),
        _float_from(equity, "used"),
        _float_from(commodity, "available"),
        _float_from(commodity, "used"),
    )


def _position(raw) -> BrokerPositionSnapshot:
    item = _mapping(raw, "position")
    return BrokerPositionSnapshot(
        instrument=_string_from(item, "instrument", "tradingsymbol"),
        exchange=_string_from(item, "exchange", default="-"),
        product=_string_from(item, "product", default="-"),
        quantity=_int_from(item, "quantity"),
        overnight_quantity=_int_from(item, "overnight_quantity", "overnight_quantity"),
        average_price=_float_from(item, "average_price"),
        last_price=_float_from(item, "last_price"),
        unrealized_pnl=_float_from(item, "unrealized_pnl", "pnl"),
        realized_pnl=_float_from(item, "realized_pnl"),
        buy_quantity=_int_from(item, "buy_quantity"),
        sell_quantity=_int_from(item, "sell_quantity"),
    )


def _holding(raw) -> BrokerHoldingSnapshot:
    item = _mapping(raw, "holding")
    return BrokerHoldingSnapshot(
        instrument=_string_from(item, "instrument", "tradingsymbol"),
        exchange=_string_from(item, "exchange", default="-"),
        quantity=_int_from(item, "quantity"),
        t1_quantity=_int_from(item, "t1_quantity"),
        average_price=_float_from(item, "average_price"),
        last_price=_float_from(item, "last_price"),
        pnl=_float_from(item, "pnl"),
        collateral_quantity=_int_from(item, "collateral_quantity"),
    )


def _order(raw) -> BrokerOrderStatusSnapshot:
    item = _mapping(raw, "order")
    return BrokerOrderStatusSnapshot(
        order_id=_string_from(item, "order_id"),
        instrument=_string_from(item, "instrument", "tradingsymbol"),
        exchange=_string_from(item, "exchange", default="-"),
        transaction_type=_string_from(item, "transaction_type", default="-"),
        order_type=_string_from(item, "order_type", default="-"),
        product=_string_from(item, "product", default="-"),
        quantity=_int_from(item, "quantity"),
        filled_quantity=_int_from(item, "filled_quantity"),
        pending_quantity=_int_from(item, "pending_quantity"),
        average_price=_float_from(item, "average_price"),
        status=_string_from(item, "status", default="-"),
        status_message=_optional_string_from(item, "status_message"),
        created_at=_datetime_from(item, "created_at"),
        updated_at=_datetime_from(item, "updated_at"),
    )


def _mapping(raw, name: str) -> Mapping:
    if not isinstance(raw, Mapping):
        raise TypeError(f"{name} payload must be a mapping")
    return raw


def _sequence(raw, name: str) -> Sequence:
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise TypeError(f"{name} payload must be a sequence")
    return raw


def _string_from(mapping: Mapping, *keys: str, default: str | None = None) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return _text(str(value), key)
    if default is not None:
        return default
    raise ValueError(f"missing broker field: {keys[0]}")


def _optional_string_from(mapping: Mapping, key: str) -> str | None:
    value = mapping.get(key)
    if value is None or not str(value).strip():
        return None
    return _text(str(value), key)


def _float_from(mapping: Mapping, *keys: str) -> float:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{key} must be numeric")
            return float(value)
    return 0.0


def _int_from(mapping: Mapping, *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{key} must be int")
            return value
    return 0


def _datetime_from(mapping: Mapping, key: str) -> datetime | None:
    value = mapping.get(key)
    if value is None:
        return None
    return _aware(value, key)


def _client_account_id(client, auth_snapshot) -> str | None:
    for attr in ("account_id", "user_id"):
        value = getattr(client, attr, None)
        if value:
            return str(value)
    value = getattr(auth_snapshot, "user_id", None)
    return str(value) if value else None


def _snapshot_time(auth_snapshot) -> datetime | None:
    return getattr(auth_snapshot, "authenticated_at", None)


def _auth_blocking_reason(state: BrokerSessionState) -> str:
    if state is BrokerSessionState.TOKEN_EXPIRED:
        return "Broker token expired; user authentication is required."
    if state is BrokerSessionState.SESSION_INVALID:
        return "Broker session is invalid; user authentication is required."
    if state is BrokerSessionState.AUTHENTICATING:
        return "Broker authentication is in progress."
    return "Broker account sync requires authentication."


def _auth_status(snapshot: BrokerAccountSnapshot) -> BrokerRuntimeStatus:
    if snapshot.authentication_state is BrokerSessionState.AUTHENTICATED:
        return BrokerRuntimeStatus.READY
    if snapshot.authentication_state is BrokerSessionState.AUTHENTICATING:
        return BrokerRuntimeStatus.WAITING
    if snapshot.authentication_state in {BrokerSessionState.TOKEN_EXPIRED, BrokerSessionState.SESSION_INVALID}:
        return BrokerRuntimeStatus.BLOCKED
    if snapshot.authentication_state is BrokerSessionState.FAILED:
        return BrokerRuntimeStatus.FAILED
    return BrokerRuntimeStatus.WAITING


def _connection_status(snapshot: BrokerAccountSnapshot) -> BrokerRuntimeStatus:
    if snapshot.connection_state is BrokerConnectionState.READY:
        return BrokerRuntimeStatus.READY
    if snapshot.connection_state is BrokerConnectionState.RECONNECTING:
        return BrokerRuntimeStatus.RECONNECTING
    if snapshot.connection_state is BrokerConnectionState.FAILED:
        return BrokerRuntimeStatus.FAILED
    return BrokerRuntimeStatus.WAITING


def _auth_reason(snapshot: BrokerAccountSnapshot) -> str:
    return "-" if snapshot.authentication_state is BrokerSessionState.AUTHENTICATED else snapshot.blocking_reason


def _age(refresh_timestamp: datetime | None, now: datetime) -> float | None:
    if refresh_timestamp is None:
        return None
    return max(0.0, (now - refresh_timestamp).total_seconds())


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty text")
    return normalized


def _safe_error(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    for sensitive in ("access_token", "request_token", "api_secret", "password", "pin", "totp", "totp_seed"):
        message = message.replace(sensitive, "[REDACTED]")
    return message


