"""
Desktop live option-chain integration helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from math import isfinite
from numbers import Real
from typing import Protocol

from application.enums import RuntimeInstrument
from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data import LiveMarketDataRuntime
from application.live_option_chain import LiveOptionChainRuntimeFactory
from application.live_option_chain_integration import LiveOptionChainIntegrationCoordinatorFactory
from application.option_chain_analytics_integration import OptionChainAnalyticsIntegrationCoordinatorFactory
from brokers.zerodha.instruments import KiteInstrumentClient
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.option_market_data import ZerodhaOptionMarketDataSubscriptionManagerFactory
from brokers.zerodha.options import ZerodhaOptionContractDiscoveryService
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.option_chain_analytics import OptionChainAnalyticsEngine


SUPPORTED_OPTION_CHAIN_INSTRUMENTS = (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)


class DesktopOptionChainConfigurationError(RuntimeError):
    """Raised for sanitized desktop option-chain startup failures."""


class InstrumentClientFactory(Protocol):
    def __call__(self, *, api_key: str, access_token: str):
        ...


@dataclass(frozen=True, slots=True)
class DesktopOptionChainSettings:
    enabled: bool
    auto_start: bool
    strikes_each_side: int


@dataclass(frozen=True, slots=True)
class _OptionChainStack:
    underlying: Instrument
    token_count: int
    live_integration: object
    analytics_integration: object


class DesktopOptionChainRuntimeState(str, Enum):
    DISABLED = "Disabled"
    STARTING = "Starting"
    WAITING_FOR_SPOT = "Waiting For Spot"
    DISCOVERING_CONTRACTS = "Discovering Contracts"
    SUBSCRIBING = "Subscribing"
    RECEIVING = "Receiving"
    ERROR = "Error"


@dataclass(frozen=True, slots=True)
class DesktopOptionChainInstrumentSnapshot:
    underlying: Instrument
    enabled: bool
    configured: bool
    started: bool
    discovery_ready: bool
    waiting_for_spot: bool
    contracts_resolved: bool
    subscriptions_active: bool
    ready: bool
    option_token_count: int
    current_spot: float | None
    last_expiry: object | None
    atm_strike: float | None
    option_ticks_received: int
    analytics_updated: bool
    last_spot_tick_at: datetime | None
    last_option_tick_at: datetime | None
    last_updated_at: datetime | None
    last_error: str | None
    state: DesktopOptionChainRuntimeState
    events: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DesktopOptionChainRuntimeSnapshot:
    enabled: bool
    configured: bool
    started: bool
    discovery_ready: bool
    underlyings_ready: tuple[Instrument, ...]
    option_token_count: int
    last_underlying: Instrument | None
    last_expiry: object | None
    last_updated_at: datetime | None
    last_error: str | None
    instruments: tuple[DesktopOptionChainInstrumentSnapshot, ...]


@dataclass(slots=True)
class _MutableInstrumentState:
    underlying: Instrument
    started: bool = False
    contracts_resolved: bool = False
    subscriptions_active: bool = False
    ready: bool = False
    option_token_count: int = 0
    current_spot: float | None = None
    last_expiry: object | None = None
    atm_strike: float | None = None
    option_ticks_received: int = 0
    analytics_updated: bool = False
    last_spot_tick_at: datetime | None = None
    last_option_tick_at: datetime | None = None
    last_updated_at: datetime | None = None
    last_error: str | None = None
    state: DesktopOptionChainRuntimeState = DesktopOptionChainRuntimeState.DISABLED
    events: list[str] = None

    def __post_init__(self) -> None:
        if self.events is None:
            self.events = []

    def log(self, clock, message: str) -> None:
        timestamp = _safe_now(clock)
        stamp = timestamp.strftime("%H:%M:%S") if timestamp is not None else "--:--:--"
        self.events.append(f"{stamp} {message}")
        self.last_updated_at = timestamp or self.last_updated_at


class DesktopOptionChainRuntimeManager:
    def __init__(
        self,
        *,
        lifecycle: ApplicationLifecycleManager,
        live_market_data_runtime: LiveMarketDataRuntime | None,
        ticker_client,
        instrument_client,
        settings: DesktopOptionChainSettings,
        spot_subscriptions: tuple[ZerodhaInstrumentSubscription, ...],
        redactions: tuple[str | None, ...] = (),
        clock=None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be ApplicationLifecycleManager")
        if live_market_data_runtime is not None and not isinstance(live_market_data_runtime, LiveMarketDataRuntime):
            raise TypeError("live_market_data_runtime must be LiveMarketDataRuntime or None")
        if not isinstance(settings, DesktopOptionChainSettings):
            raise TypeError("settings must be DesktopOptionChainSettings")
        self._lifecycle = lifecycle
        self._live_market_data_runtime = live_market_data_runtime
        self._ticker_client = ticker_client
        self._instrument_client = instrument_client
        self._settings = settings
        self._redactions = tuple(value for value in redactions if value)
        self._clock = clock or _default_clock
        self._spot_by_token = {subscription.instrument_token: subscription.instrument for subscription in spot_subscriptions}
        self._discovery = ZerodhaOptionContractDiscoveryService(client=instrument_client, clock=self._clock)
        self._resolver = None
        self._stacks: dict[Instrument, _OptionChainStack] = {}
        self._token_owner: dict[int, Instrument] = {}
        self._started = False
        self._stopped = False
        self._discovery_ready = False
        self._last_underlying: Instrument | None = None
        self._last_expiry = None
        self._last_updated_at: datetime | None = None
        self._last_error: str | None = None
        self._instrument_state = {
            underlying: _MutableInstrumentState(underlying=underlying)
            for underlying in SUPPORTED_OPTION_CHAIN_INSTRUMENTS
        }

    @property
    def started(self) -> bool:
        return self._started

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def option_tokens(self) -> set[int]:
        return set(self._token_owner)

    def snapshot(self) -> DesktopOptionChainRuntimeSnapshot:
        instrument_snapshots = tuple(self._snapshot_for(underlying) for underlying in SUPPORTED_OPTION_CHAIN_INSTRUMENTS)
        return DesktopOptionChainRuntimeSnapshot(
            enabled=self._settings.enabled,
            configured=self._settings.enabled,
            started=self._started,
            discovery_ready=self._discovery_ready,
            underlyings_ready=tuple(item.underlying for item in instrument_snapshots if item.ready),
            option_token_count=len(self._token_owner),
            last_underlying=self._last_underlying,
            last_expiry=self._last_expiry,
            last_updated_at=self._last_updated_at,
            last_error=self._last_error,
            instruments=instrument_snapshots,
        )

    def start(self) -> DesktopOptionChainRuntimeSnapshot:
        if self._started:
            return self.snapshot()
        for state in self._instrument_state.values():
            state.state = DesktopOptionChainRuntimeState.STARTING
            state.started = True
            state.log(self._clock, "Starting")
        try:
            for state in self._instrument_state.values():
                state.state = DesktopOptionChainRuntimeState.DISCOVERING_CONTRACTS
                state.log(self._clock, "Resolving contracts...")
            discovery = self._discovery.load(SUPPORTED_OPTION_CHAIN_INSTRUMENTS)
            self._discovery_ready = bool(discovery.available_underlyings)
            self._resolver = self._discovery.create_resolver()
        except Exception as exc:
            self._last_error = _safe_error(exc, self._redactions)
            self._last_updated_at = _safe_now(self._clock)
            for state in self._instrument_state.values():
                state.state = DesktopOptionChainRuntimeState.ERROR
                state.last_error = self._last_error
                state.log(self._clock, self._last_error)
            return self.snapshot()
        available = set(discovery.available_underlyings)
        self._started = True
        self._stopped = False
        self._last_error = None if available else (discovery.last_error or "No Contracts Found")
        self._last_updated_at = _safe_now(self._clock)
        for state in self._instrument_state.values():
            if state.underlying in available:
                state.state = DesktopOptionChainRuntimeState.WAITING_FOR_SPOT
                state.last_error = None
                state.log(self._clock, f"Waiting for first {state.underlying.value} spot tick")
            else:
                error = self._discovery.error_for(state.underlying) or f"No valid {state.underlying.value} contracts were discovered."
                state.state = DesktopOptionChainRuntimeState.ERROR
                state.last_error = error
                state.log(self._clock, error)
        return self.snapshot()

    def stop(self) -> DesktopOptionChainRuntimeSnapshot:
        if self._stopped:
            return self.snapshot()
        first_error = None
        for stack in tuple(self._stacks.values()):
            try:
                stack.analytics_integration.stop()
            except Exception as exc:
                first_error = first_error or exc
            try:
                stack.live_integration.stop()
            except Exception as exc:
                first_error = first_error or exc
        self._stopped = True
        if first_error is not None:
            self._last_error = _safe_error(first_error, self._redactions)
            raise first_error
        return self.snapshot()

    def deliver_spot_ticks(self, raw_ticks) -> None:
        if not self._settings.enabled or not self._settings.auto_start or not self._started:
            return
        for raw_tick in tuple(raw_ticks):
            token = _raw_token(raw_tick)
            underlying = self._spot_by_token.get(token)
            if underlying not in SUPPORTED_OPTION_CHAIN_INSTRUMENTS:
                continue
            price = _raw_price(raw_tick)
            timestamp = _raw_timestamp(raw_tick, self._clock)
            state = self._instrument_state[underlying]
            if state.state is DesktopOptionChainRuntimeState.ERROR and state.option_token_count == 0:
                state.current_spot = price
                state.last_spot_tick_at = timestamp
                state.last_updated_at = timestamp
                state.log(self._clock, f"Spot ignored after discovery error: {price:.2f}")
                continue
            state.current_spot = price
            state.last_spot_tick_at = timestamp
            state.last_updated_at = timestamp
            state.log(self._clock, f"Spot received: {price:.2f}")
            self._last_underlying = underlying
            self._last_updated_at = timestamp
            try:
                stack = self._stack_for(underlying, price)
                stack.live_integration.deliver_underlying_price(price, timestamp=timestamp)
            except Exception as exc:
                error = _safe_error(exc, self._redactions)
                self._last_error = error
                state.last_error = error
                state.state = DesktopOptionChainRuntimeState.ERROR
                state.log(self._clock, error)

    def deliver_option_ticks(self, raw_ticks) -> None:
        if not self._settings.enabled or not self._settings.auto_start or not self._started:
            return
        grouped: dict[Instrument, list[object]] = {}
        for raw_tick in tuple(raw_ticks):
            owner = self._token_owner.get(_raw_token(raw_tick))
            if owner is not None:
                grouped.setdefault(owner, []).append(raw_tick)
        for underlying, rows in grouped.items():
            stack = self._stacks.get(underlying)
            if stack is None:
                continue
            state = self._instrument_state[underlying]
            try:
                stack.live_integration.deliver_option_ticks(tuple(rows))
                live_snapshot = stack.live_integration.snapshot()
                state.option_ticks_received = live_snapshot.delivered_option_tick_count
                state.last_option_tick_at = live_snapshot.last_delivery_at
                state.last_updated_at = live_snapshot.last_delivery_at
                if state.option_ticks_received:
                    state.log(self._clock, "First option tick received")
                outcome = stack.analytics_integration.process_current()
                state.analytics_updated = bool(getattr(outcome, "analytics_updated", False) or state.analytics_updated)
                snapshot = stack.live_integration.snapshot().option_chain.latest_option_chain_snapshot
                if snapshot is not None:
                    self._lifecycle.orchestrator.process_option_chain(RuntimeInstrument(underlying.value), snapshot)
                    state.state = DesktopOptionChainRuntimeState.RECEIVING
                    state.ready = True
                    state.log(self._clock, "Analytics updated")
            except Exception as exc:
                error = _safe_error(exc, self._redactions)
                self._last_error = error
                state.last_error = error
                state.state = DesktopOptionChainRuntimeState.ERROR
                state.log(self._clock, error)

    def _stack_for(self, underlying: Instrument, underlying_price: float) -> _OptionChainStack:
        existing = self._stacks.get(underlying)
        if existing is not None:
            return existing
        if self._resolver is None:
            raise RuntimeError("option contract resolver is not ready")
        now = _aware(self._clock(), "clock result")
        state = self._instrument_state[underlying]
        state.state = DesktopOptionChainRuntimeState.DISCOVERING_CONTRACTS
        state.log(self._clock, "Resolving contracts...")
        universe = self._resolver.resolve_universe(
            underlying,
            as_of=now.date(),
            underlying_price=underlying_price,
            strikes_each_side=self._settings.strikes_each_side,
        )
        state.contracts_resolved = True
        state.option_token_count = len(universe.subscriptions)
        state.last_expiry = universe.expiry.expiry
        state.atm_strike = universe.atm_strike
        state.log(self._clock, f"{len(universe.subscriptions)} contracts resolved")
        subscription_manager = ZerodhaOptionMarketDataSubscriptionManagerFactory().create(
            client=self._ticker_client,
            clock=self._clock,
        )
        subscription_manager.prepare(universe)
        owned_tokens = tuple(subscription.instrument_token for subscription in universe.subscriptions)
        if any(token in self._token_owner for token in owned_tokens):
            raise RuntimeError("duplicate option subscription token")
        for token in owned_tokens:
            self._token_owner[token] = underlying
        state.state = DesktopOptionChainRuntimeState.SUBSCRIBING
        state.log(self._clock, "Subscribing...")
        try:
            subscription_manager.activate()
        except Exception:
            for token in owned_tokens:
                self._token_owner.pop(token, None)
            state.subscriptions_active = False
            raise
        state.subscriptions_active = True
        state.log(self._clock, "Subscription successful")
        live_runtime = LiveOptionChainRuntimeFactory().create(
            universe=universe,
            subscription_manager=subscription_manager,
            option_chain_engine=OptionChainEngine(
                EventBus(),
                underlying.value,
                "BSE" if underlying is Instrument.SENSEX else "NSE",
                universe.expiry.expiry,
            ),
            clock=self._clock,
        )
        self._lifecycle.orchestrator.get_runtime(RuntimeInstrument(underlying.value)).option_chain_engine = (
            live_runtime.option_chain_engine
        )
        live_integration = LiveOptionChainIntegrationCoordinatorFactory().create(
            lifecycle=self._lifecycle,
            subscription_manager=subscription_manager,
            live_option_chain_runtime=live_runtime,
            live_market_data_runtime=self._live_market_data_runtime,
            clock=self._clock,
        )
        live_integration.start()
        analytics_integration = OptionChainAnalyticsIntegrationCoordinatorFactory().create(
            lifecycle=self._lifecycle,
            live_option_chain_integration=live_integration,
            analytics_engine=OptionChainAnalyticsEngine(underlying=underlying, expiry=universe.expiry.expiry),
            clock=self._clock,
        )
        analytics_integration.start()
        stack = _OptionChainStack(
            underlying=underlying,
            token_count=len(universe.subscriptions),
            live_integration=live_integration,
            analytics_integration=analytics_integration,
        )
        self._stacks[underlying] = stack
        self._last_underlying = underlying
        self._last_expiry = universe.expiry.expiry
        self._last_updated_at = now
        return stack

    def _snapshot_for(self, underlying: Instrument) -> DesktopOptionChainInstrumentSnapshot:
        state = self._instrument_state[underlying]
        if not self._settings.enabled:
            status = DesktopOptionChainRuntimeState.DISABLED
        else:
            status = state.state
        return DesktopOptionChainInstrumentSnapshot(
            underlying=underlying,
            enabled=self._settings.enabled,
            configured=self._settings.enabled,
            started=state.started or self._started,
            discovery_ready=self._discovery_ready,
            waiting_for_spot=status is DesktopOptionChainRuntimeState.WAITING_FOR_SPOT,
            contracts_resolved=state.contracts_resolved,
            subscriptions_active=state.subscriptions_active,
            ready=state.ready,
            option_token_count=state.option_token_count,
            current_spot=state.current_spot,
            last_expiry=state.last_expiry,
            atm_strike=state.atm_strike,
            option_ticks_received=state.option_ticks_received,
            analytics_updated=state.analytics_updated,
            last_spot_tick_at=state.last_spot_tick_at,
            last_option_tick_at=state.last_option_tick_at,
            last_updated_at=state.last_updated_at,
            last_error=state.last_error,
            state=status,
            events=tuple(state.events[-8:]),
        )


def create_instrument_client(*, api_key: str, access_token: str):
    return KiteInstrumentClient(api_key=api_key, access_token=access_token)


def _raw_token(raw_tick) -> int | None:
    if not hasattr(raw_tick, "get"):
        return None
    token = raw_tick.get("instrument_token")
    return token if isinstance(token, int) and not isinstance(token, bool) else None


def _raw_price(raw_tick) -> float:
    if not hasattr(raw_tick, "get"):
        raise ValueError("raw tick must be a mapping")
    value = raw_tick.get("last_price")
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("last_price must be finite positive number")
    price = float(value)
    if not isfinite(price) or price <= 0:
        raise ValueError("last_price must be finite positive number")
    return price


def _raw_timestamp(raw_tick, clock) -> datetime:
    value = raw_tick.get("exchange_timestamp") if hasattr(raw_tick, "get") else None
    if value is None and hasattr(raw_tick, "get"):
        value = raw_tick.get("timestamp")
    if value is None:
        value = clock()
    return _aware(value, "tick timestamp")


def _aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _safe_error(exc: Exception, redactions: tuple[str, ...] = ()) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    for secret in redactions:
        message = message.replace(secret, "[REDACTED]")
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message


def _safe_now(clock) -> datetime | None:
    try:
        return _aware(clock(), "clock result")
    except Exception:
        return None


def _default_clock() -> datetime:
    return datetime.now(UTC)
