"""
Integration tests for Zerodha WebSocket ticks and MarketDataEngine.
"""

from datetime import UTC, datetime, timedelta

from brokers.zerodha.auth import ZerodhaSession
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaWebSocketManager
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import MARKET_UPDATED, NEW_TICK
from engines.market_data.market_data_engine import MarketDataEngine


NOW = datetime(2026, 7, 12, 9, 15, tzinfo=UTC)


class FakeTickerClient:
    def set_callbacks(self, **callbacks):
        self.callbacks = callbacks

    def connect(self, *, threaded=True):
        pass

    def close(self):
        pass

    def subscribe(self, instrument_tokens):
        pass

    def unsubscribe(self, instrument_tokens):
        pass

    def set_mode(self, mode, instrument_tokens):
        pass


def raw(price=25000.0, timestamp=NOW):
    return {
        "instrument_token": 101,
        "last_price": price,
        "exchange_timestamp": timestamp,
        "volume": 10,
        "depth": {"buy": [{"price": price - 1}], "sell": [{"price": price + 1}]},
    }


def test_raw_zerodha_tick_reaches_market_data_engine_and_events():
    event_bus = EventBus()
    events = []
    event_bus.subscribe(NEW_TICK, lambda tick: events.append((NEW_TICK, tick)))
    event_bus.subscribe(MARKET_UPDATED, lambda tick: events.append((MARKET_UPDATED, tick)))
    engine = MarketDataEngine(event_bus)
    session = ZerodhaSession("AB1234", "access_token", NOW, NOW + timedelta(hours=1))
    manager = ZerodhaWebSocketManager(
        api_key="api_key",
        session=session,
        tick_consumer=engine.on_tick,
        subscriptions=(ZerodhaInstrumentSubscription(101, Instrument.NIFTY, Exchange.NSE),),
        client=FakeTickerClient(),
        clock=lambda: NOW,
    )

    result = manager.process_raw_ticks((raw(), raw(), raw(24999.0, NOW - timedelta(seconds=1)), {"instrument_token": 999, "last_price": 1}, raw(25001.0, NOW + timedelta(seconds=1))))

    assert result.received_count == 5
    assert result.delivered_ticks[0].symbol is Instrument.NIFTY
    assert result.delivered_ticks[0].exchange is Exchange.NSE
    assert engine.get_latest(Instrument.NIFTY).last_price == 25001.0
    assert [name for name, _ in events].count(NEW_TICK) == 2
    assert [name for name, _ in events].count(MARKET_UPDATED) == 2
    assert result.rejected_count == 2
    assert [tick.last_price for tick in result.normalized_ticks] == [25000.0, 25000.0, 24999.0, 25001.0]
