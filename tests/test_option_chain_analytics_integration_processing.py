from datetime import UTC, date, datetime

from application.bootstrap import ApplicationBootstrap
from application.live_option_chain import LiveOptionChainRuntime
from application.live_option_chain_integration import LiveOptionChainIntegrationCoordinator
from application.option_chain_analytics_integration import (
    OptionChainAnalyticsIntegrationCoordinator,
    OptionChainAnalyticsProcessingResult,
)
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.option_market_data import ZerodhaOptionMarketDataSubscriptionManager
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaExpiry, ZerodhaExpiryKind, ZerodhaOptionContract, ZerodhaOptionPair, ZerodhaOptionRight, ZerodhaOptionUniverse
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.option_chain_analytics import OptionBuildUpType, OptionChainAnalyticsEngine


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)
EXPIRY = date(2026, 7, 30)


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
    return ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", EXPIRY, strike, right, 75, 0.05)


def universe():
    exp = ZerodhaExpiry(Instrument.NIFTY, EXPIRY, ZerodhaExpiryKind.MONTHLY, 4, 2, 25000, 25100)
    pairs = (
        ZerodhaOptionPair(Instrument.NIFTY, exp, 25000, contract(1, 25000, ZerodhaOptionRight.CALL), contract(2, 25000, ZerodhaOptionRight.PUT)),
        ZerodhaOptionPair(Instrument.NIFTY, exp, 25100, contract(3, 25100, ZerodhaOptionRight.CALL), contract(4, 25100, ZerodhaOptionRight.PUT)),
    )
    subs = tuple(ZerodhaInstrumentSubscription(token, Instrument.NIFTY, Exchange.NSE) for token in (1, 2, 3, 4))
    return ZerodhaOptionUniverse(Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, exp, 25050, 25000, 100, pairs, subs, NOW)


def raw_batch(oi_values, timestamp, *, price_offset=0):
    return tuple(
        {"instrument_token": index, "last_price": 10 + index + price_offset, "volume": index, "oi": oi, "exchange_timestamp": timestamp}
        for index, oi in zip((1, 2, 3, 4), oi_values)
    )


def build_running_stack(*, start_analytics=True):
    current_time = [NOW]
    clock = lambda: current_time[0]
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    item = universe()
    transport = Transport()
    subscriptions = ZerodhaOptionMarketDataSubscriptionManager(transport=transport, clock=clock)
    subscriptions.prepare(item)
    subscriptions.activate()
    source_engine = OptionChainEngine(EventBus(), "NIFTY", "NSE", EXPIRY)
    live_runtime = LiveOptionChainRuntime(universe=item, subscription_manager=subscriptions, option_chain_engine=source_engine, clock=clock)
    live_coordinator = LiveOptionChainIntegrationCoordinator(lifecycle=lifecycle, subscription_manager=subscriptions, live_option_chain_runtime=live_runtime, clock=clock)
    live_coordinator.start()
    analytics_engine = OptionChainAnalyticsEngine(underlying=Instrument.NIFTY, expiry=EXPIRY)
    analytics_coordinator = OptionChainAnalyticsIntegrationCoordinator(lifecycle=lifecycle, live_option_chain_integration=live_coordinator, analytics_engine=analytics_engine, clock=clock)
    if start_analytics:
        analytics_coordinator.start()
    return {
        "lifecycle": lifecycle,
        "live_coordinator": live_coordinator,
        "analytics_engine": analytics_engine,
        "analytics_coordinator": analytics_coordinator,
        "raw_batch": raw_batch,
        "transport": transport,
        "set_clock": lambda value: current_time.__setitem__(0, value),
    }


def test_processing_not_ready_processed_duplicate_and_newer():
    stack = build_running_stack()
    coordinator = stack["analytics_coordinator"]
    not_ready = coordinator.process_current()
    assert not_ready.result is OptionChainAnalyticsProcessingResult.NOT_READY
    stack["live_coordinator"].deliver_underlying_price(25050, timestamp=NOW)
    stack["live_coordinator"].deliver_option_ticks(raw_batch((100, 200, 300, 400), NOW))
    first = coordinator.process_current()
    assert first.result is OptionChainAnalyticsProcessingResult.PROCESSED
    duplicate = coordinator.process_current()
    assert duplicate.result is OptionChainAnalyticsProcessingResult.DUPLICATE
    later = datetime(2026, 7, 14, 9, 16, tzinfo=UTC)
    stack["set_clock"](later)
    stack["live_coordinator"].deliver_option_ticks(raw_batch((120, 230, 320, 430), later, price_offset=1))
    second = coordinator.process_current()
    assert second.result is OptionChainAnalyticsProcessingResult.PROCESSED
    assert second.analytics_snapshot.strikes[0].call.build_up in {
        OptionBuildUpType.LONG_BUILDUP,
        OptionBuildUpType.SHORT_BUILDUP,
    }
    snapshot = coordinator.snapshot()
    assert snapshot.processing_count == 3
    assert snapshot.duplicate_count == 1
    assert snapshot.not_ready_count == 1
