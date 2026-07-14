from datetime import UTC, date, datetime

import pytest

from application.bootstrap import ApplicationBootstrap
from application.live_option_chain import LiveOptionChainRuntime
from application.live_option_chain_integration import (
    LiveOptionChainIntegrationConfiguration,
    LiveOptionChainIntegrationCoordinator,
    LiveOptionChainIntegrationStatus,
)
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.option_market_data import ZerodhaOptionMarketDataSubscriptionManager
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaExpiry, ZerodhaExpiryKind, ZerodhaOptionContract, ZerodhaOptionPair, ZerodhaOptionRight, ZerodhaOptionUniverse
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from engines.option_chain.option_chain_engine import OptionChainEngine


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


class Transport:
    def __init__(self):
        self.calls = []

    def subscribe(self, tokens):
        self.calls.append(("subscribe", list(tokens)))

    def unsubscribe(self, tokens):
        self.calls.append(("unsubscribe", list(tokens)))

    def set_mode(self, mode, tokens):
        self.calls.append(("mode", mode, list(tokens)))


def contract(token, strike, right):
    return ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", date(2026, 7, 30), strike, right, 75, 0.05)


def universe():
    exp = ZerodhaExpiry(Instrument.NIFTY, date(2026, 7, 30), ZerodhaExpiryKind.MONTHLY, 4, 2, 25000, 25100)
    pairs = (
        ZerodhaOptionPair(Instrument.NIFTY, exp, 25000, contract(1, 25000, ZerodhaOptionRight.CALL), contract(2, 25000, ZerodhaOptionRight.PUT)),
        ZerodhaOptionPair(Instrument.NIFTY, exp, 25100, contract(3, 25100, ZerodhaOptionRight.CALL), contract(4, 25100, ZerodhaOptionRight.PUT)),
    )
    subs = tuple(ZerodhaInstrumentSubscription(token, Instrument.NIFTY, Exchange.NSE) for token in (1, 2, 3, 4))
    return ZerodhaOptionUniverse(Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, exp, 25050, 25000, 100, pairs, subs, NOW)


def build_stack(*, start_application=True, config=None):
    lifecycle = ApplicationBootstrap().create_application()
    if start_application:
        lifecycle.start()
    transport = Transport()
    manager = ZerodhaOptionMarketDataSubscriptionManager(transport=transport, clock=lambda: NOW)
    item = universe()
    manager.prepare(item)
    manager.activate()
    engine = OptionChainEngine(EventBus(), "NIFTY", "NSE", date(2026, 7, 30))
    runtime = LiveOptionChainRuntime(universe=item, subscription_manager=manager, option_chain_engine=engine, clock=lambda: NOW)
    coordinator = LiveOptionChainIntegrationCoordinator(
        lifecycle=lifecycle,
        subscription_manager=manager,
        live_option_chain_runtime=runtime,
        configuration=config,
        clock=lambda: NOW,
    )
    return lifecycle, manager, runtime, engine, transport, NOW


def test_start_stop_restart_and_optional_deactivation():
    lifecycle, manager, runtime, _engine, transport, now = build_stack(start_application=True)
    coordinator = LiveOptionChainIntegrationCoordinator(lifecycle=lifecycle, subscription_manager=manager, live_option_chain_runtime=runtime, clock=lambda: now)
    assert coordinator.start().status is LiveOptionChainIntegrationStatus.RUNNING
    assert coordinator.start().start_count == 1
    assert lifecycle.is_running()
    snapshot = coordinator.stop()
    assert snapshot.status is LiveOptionChainIntegrationStatus.STOPPED
    assert manager.snapshot().active is True
    assert not any(call[0] == "connect" for call in transport.calls)
    assert coordinator.restart().status is LiveOptionChainIntegrationStatus.RUNNING

    lifecycle2, manager2, runtime2, _engine2, _transport2, now2 = build_stack(
        start_application=True,
        config=LiveOptionChainIntegrationConfiguration(deactivate_option_subscriptions_on_shutdown=True),
    )
    coordinator2 = LiveOptionChainIntegrationCoordinator(
        lifecycle=lifecycle2,
        subscription_manager=manager2,
        live_option_chain_runtime=runtime2,
        configuration=LiveOptionChainIntegrationConfiguration(deactivate_option_subscriptions_on_shutdown=True),
        clock=lambda: now2,
    )
    coordinator2.start()
    coordinator2.stop()
    assert manager2.snapshot().active is False


def test_start_requires_running_application():
    lifecycle, manager, runtime, _engine, _transport, now = build_stack(start_application=False)
    coordinator = LiveOptionChainIntegrationCoordinator(lifecycle=lifecycle, subscription_manager=manager, live_option_chain_runtime=runtime, clock=lambda: now)
    with pytest.raises(RuntimeError):
        coordinator.start()
    assert coordinator.snapshot().status is LiveOptionChainIntegrationStatus.ERROR
