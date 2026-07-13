from datetime import UTC, date, datetime

from application import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.option_market_data import ZerodhaOptionMarketDataSubscriptionManagerFactory
from brokers.zerodha.options import ZerodhaDerivativeVenue, ZerodhaExpiry, ZerodhaExpiryKind, ZerodhaOptionContract, ZerodhaOptionPair, ZerodhaOptionRight, ZerodhaOptionUniverse
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 10, tzinfo=UTC)


class Client:
    def __init__(self):
        self.calls = []
        self.connected = False
        self.disconnected = False
        self.raw_ticks = []
        self.orders = []

    def subscribe(self, tokens):
        self.calls.append(("subscribe", list(tokens)))

    def unsubscribe(self, tokens):
        self.calls.append(("unsubscribe", list(tokens)))

    def set_mode(self, mode, tokens):
        self.calls.append(("mode", mode, list(tokens)))


def universe(expiry=date(2026, 7, 30), tokens=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), strikes=(24800, 24900, 25000, 25100, 25200)):
    exp = ZerodhaExpiry(Instrument.NIFTY, expiry, ZerodhaExpiryKind.MONTHLY, len(tokens), len(strikes), strikes[0], strikes[-1])
    pairs = []
    for index, strike in enumerate(strikes):
        call = _contract(tokens[index * 2], expiry, strike, ZerodhaOptionRight.CALL)
        put = _contract(tokens[index * 2 + 1], expiry, strike, ZerodhaOptionRight.PUT)
        pairs.append(ZerodhaOptionPair(Instrument.NIFTY, exp, strike, call, put))
    subs = tuple(ZerodhaInstrumentSubscription(token, Instrument.NIFTY, Exchange.NSE) for token in tokens)
    return ZerodhaOptionUniverse(Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, exp, 25000, 25000, 100, tuple(pairs), subs, NOW)


def _contract(token, expiry, strike, right):
    return ZerodhaOptionContract(token, token, Instrument.NIFTY, ZerodhaDerivativeVenue.NFO, "NFO-OPT", f"N{token}", "NIFTY", expiry, strike, right, 75, 0.05)


def test_no_network_option_subscription_flow_prepare_activate_replace_rollover_deactivate():
    client = Client()
    manager = ZerodhaOptionMarketDataSubscriptionManagerFactory().create(client=client, clock=lambda: NOW)
    manager.prepare(universe())
    assert client.calls == []
    manager.activate()
    assert client.calls[:2] == [("subscribe", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), ("mode", "full", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])]
    client.calls.clear()
    manager.replace(universe(tokens=(5, 6, 7, 8, 9, 10, 11, 12, 13, 14), strikes=(25000, 25100, 25200, 25300, 25400)))
    assert client.calls[0] == ("subscribe", [11, 12, 13, 14])
    assert client.calls[-1] == ("unsubscribe", [1, 2, 3, 4])
    client.calls.clear()
    manager.replace(universe(expiry=date(2026, 8, 30), tokens=(21, 22, 23, 24, 25, 26, 27, 28, 29, 30)))
    assert manager.snapshot().expiry == date(2026, 8, 30)
    manager.deactivate()
    assert client.calls[-1][0] == "unsubscribe"
    assert not client.connected
    assert not client.disconnected
    assert client.raw_ticks == []
    assert client.orders == []
    lifecycle = ApplicationBootstrap().create_application()
    snapshot = lifecycle.snapshot().orchestrator_snapshot
    assert snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
