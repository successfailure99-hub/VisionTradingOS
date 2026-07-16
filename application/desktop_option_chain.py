"""
Desktop live option-chain integration helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
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
    refresh_seconds: int
    strikes_each_side: int


@dataclass(frozen=True, slots=True)
class _OptionChainStack:
    underlying: Instrument
    token_count: int
    live_integration: object
    analytics_integration: object


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
        self._clock = clock or _default_clock
        self._spot_by_token = {subscription.instrument_token: subscription.instrument for subscription in spot_subscriptions}
        self._discovery = ZerodhaOptionContractDiscoveryService(client=instrument_client, clock=self._clock)
        self._resolver = None
        self._stacks: dict[Instrument, _OptionChainStack] = {}
        self._token_owner: dict[int, Instrument] = {}
        self._started = False
        self._stopped = False
        self._last_error: str | None = None

    @property
    def started(self) -> bool:
        return self._started

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def option_tokens(self) -> set[int]:
        return set(self._token_owner)

    def start(self) -> None:
        if self._started:
            return
        try:
            discovery = self._discovery.load(SUPPORTED_OPTION_CHAIN_INSTRUMENTS)
            missing = tuple(
                underlying
                for underlying in SUPPORTED_OPTION_CHAIN_INSTRUMENTS
                if underlying not in discovery.available_underlyings
            )
            if missing:
                raise RuntimeError("option contracts are unavailable for supported instruments")
            self._resolver = self._discovery.create_resolver()
        except Exception as exc:
            self._last_error = _safe_error(exc)
            raise DesktopOptionChainConfigurationError(f"Live option-chain startup failed: {self._last_error}") from exc
        self._started = True
        self._stopped = False
        self._last_error = None

    def stop(self) -> None:
        if self._stopped:
            return
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
            self._last_error = _safe_error(first_error)
            raise first_error

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
            try:
                stack = self._stack_for(underlying, price)
                stack.live_integration.deliver_underlying_price(price, timestamp=timestamp)
            except Exception as exc:
                self._last_error = _safe_error(exc)

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
            try:
                stack.live_integration.deliver_option_ticks(tuple(rows))
                stack.analytics_integration.process_current()
                snapshot = stack.live_integration.snapshot().option_chain.latest_option_chain_snapshot
                if snapshot is not None:
                    self._lifecycle.orchestrator.process_option_chain(RuntimeInstrument(underlying.value), snapshot)
            except Exception as exc:
                self._last_error = _safe_error(exc)

    def _stack_for(self, underlying: Instrument, underlying_price: float) -> _OptionChainStack:
        existing = self._stacks.get(underlying)
        if existing is not None:
            return existing
        if self._resolver is None:
            raise RuntimeError("option contract resolver is not ready")
        now = _aware(self._clock(), "clock result")
        universe = self._resolver.resolve_universe(
            underlying,
            as_of=now.date(),
            underlying_price=underlying_price,
            strikes_each_side=self._settings.strikes_each_side,
        )
        subscription_manager = ZerodhaOptionMarketDataSubscriptionManagerFactory().create(
            client=self._ticker_client,
            clock=self._clock,
        )
        subscription_manager.prepare(universe)
        subscription_manager.activate()
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
        for subscription in universe.subscriptions:
            self._token_owner[subscription.instrument_token] = underlying
        return stack


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


def _safe_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message


def _default_clock() -> datetime:
    return datetime.now(UTC)
