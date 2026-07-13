from datetime import UTC, date, datetime

from application import ApplicationBootstrap
from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from brokers.zerodha.options import ZerodhaOptionContractDiscoveryService
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


def rows(name, exchange, base, expiry=date(2026, 7, 30)):
    out = []
    token = base
    segment = f"{exchange}-OPT"
    for strike in (24900, 24950, 25000, 25050, 25100):
        for right in ("CE", "PE"):
            out.append(dict(instrument_token=token, exchange_token=token, tradingsymbol=f"{name}{expiry:%y%m%d}{int(strike)}{right}", name=name, exchange=exchange, segment=segment, instrument_type=right, expiry=expiry, strike=strike, lot_size=75, tick_size=0.05))
            token += 1
    return out


class Client:
    def __init__(self):
        self.calls = []
        self.quote_calls = 0
        self.rows = {
            "NFO": rows("NIFTY", "NFO", 100) + rows("BANKNIFTY", "NFO", 200),
            "BFO": rows("SENSEX", "BFO", 300),
        }

    def instruments(self, exchange=None):
        self.calls.append(exchange)
        return self.rows[exchange]


def test_no_network_contract_discovery_to_subscription_universe_flow():
    client = Client()
    service = ZerodhaOptionContractDiscoveryService(client=client, clock=lambda: datetime(2026, 7, 10, 9, 15, tzinfo=UTC))
    snapshot = service.load((Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX))
    assert snapshot.supported_contract_count == 30
    resolver = service.create_resolver()
    nifty_universe = resolver.resolve_universe(Instrument.NIFTY, as_of=date(2026, 7, 1), underlying_price=25000, strikes_each_side=2)
    banknifty_universe = resolver.resolve_universe(Instrument.BANKNIFTY, as_of=date(2026, 7, 1), underlying_price=25000, strikes_each_side=2)
    sensex_universe = resolver.resolve_universe(Instrument.SENSEX, as_of=date(2026, 7, 1), underlying_price=25000, strikes_each_side=2)

    assert len(nifty_universe.pairs) == 5
    assert len(nifty_universe.subscriptions) == 10
    assert len(banknifty_universe.pairs) == 5
    assert len(banknifty_universe.subscriptions) == 10
    assert len(sensex_universe.pairs) == 5
    assert len(sensex_universe.subscriptions) == 10

    for universe in (nifty_universe, banknifty_universe, sensex_universe):
        assert universe.strike_step == 50
        assert universe.atm_strike == 25000

    assert all(subscription.exchange is Exchange.NSE for subscription in nifty_universe.subscriptions)
    assert all(subscription.exchange is Exchange.NSE for subscription in banknifty_universe.subscriptions)
    assert all(subscription.exchange is Exchange.BSE for subscription in sensex_universe.subscriptions)
    assert client.calls == ["NFO", "BFO"]
    assert client.quote_calls == 0

    lifecycle = ApplicationBootstrap().create_application()
    application_snapshot = lifecycle.snapshot().orchestrator_snapshot

    assert (
        application_snapshot.safety_mode
        is ExecutionSafetyMode.ANALYSIS_ONLY
    )
    assert (
        application_snapshot.broker_mode
        is BrokerExecutionMode.DRY_RUN
    )
