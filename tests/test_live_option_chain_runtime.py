from datetime import UTC, date, datetime, timedelta

import pytest

from application.live_option_chain import LiveOptionChainRuntime, LiveOptionChainStatus
from brokers.zerodha.option_market_data import ZerodhaOptionMarketDataSubscriptionManager
from core.event_bus import EventBus
from engines.option_chain.option_chain_engine import OptionChainEngine
from tests.test_live_option_chain_assembler import NOW, full_quotes, universe


class Transport:
    def __init__(self):
        self.calls = []

    def subscribe(self, tokens):
        self.calls.append(("subscribe", list(tokens)))

    def unsubscribe(self, tokens):
        self.calls.append(("unsubscribe", list(tokens)))

    def set_mode(self, mode, tokens):
        self.calls.append(("mode", mode, list(tokens)))


def raw(token, price=10, oi=100, ts=NOW):
    return {"instrument_token": token, "last_price": price, "volume": token, "oi": oi, "exchange_timestamp": ts}


def active_runtime():
    transport = Transport()
    manager = ZerodhaOptionMarketDataSubscriptionManager(transport=transport, clock=lambda: NOW)
    item = universe()
    manager.prepare(item)
    manager.activate()
    engine = OptionChainEngine(EventBus(), "NIFTY", "NSE", date(2026, 7, 30))
    runtime = LiveOptionChainRuntime(universe=item, subscription_manager=manager, option_chain_engine=engine, clock=lambda: NOW)
    return runtime, manager, engine, transport


def test_runtime_start_underlying_batch_engine_and_duplicates():
    runtime, _, engine, transport = active_runtime()
    assert transport.calls
    assert runtime.start().status is LiveOptionChainStatus.COLLECTING
    runtime.set_underlying_price(25050, timestamp=NOW)
    result = runtime.process_raw_ticks((raw(1), raw(99), raw(2), raw(3), raw(4)))
    assert result.received_count == 5
    assert result.rejected_count == 1
    assert result.engine_updated is True
    assert engine.state is not None
    assert runtime.snapshot().status is LiveOptionChainStatus.READY
    duplicate = runtime.process_raw_ticks((raw(1), raw(2), raw(3), raw(4)))
    assert duplicate.duplicate_count == 4
    assert duplicate.engine_updated is False


def test_runtime_propagates_zerodha_volume_traded_into_option_chain_snapshot():
    runtime, _, engine, _ = active_runtime()
    runtime.start()
    runtime.set_underlying_price(25050, timestamp=NOW)
    result = runtime.process_raw_ticks(
        (
            {"instrument_token": 1, "last_price": 10, "volume_traded": 111, "oi": 101, "exchange_timestamp": NOW},
            {"instrument_token": 2, "last_price": 11, "volume_traded": 222, "oi": 102, "exchange_timestamp": NOW},
            {"instrument_token": 3, "last_price": 12, "volume_traded": 333, "oi": 103, "exchange_timestamp": NOW},
            {"instrument_token": 4, "last_price": 13, "volume_traded": 444, "oi": 104, "exchange_timestamp": NOW},
        )
    )
    assert result.engine_updated is True
    assert engine.state.strikes[0].call.volume == 111
    assert engine.state.strikes[0].put.volume == 222
    assert engine.state.strikes[1].call.volume == 333
    assert engine.state.strikes[1].put.volume == 444


def test_runtime_partial_stale_correction_stop_clear_and_baseline():
    runtime, _, _, _ = active_runtime()
    with pytest.raises(RuntimeError):
        runtime.process_raw_ticks((raw(1),))
    runtime.start()
    runtime.set_underlying_price(25050, timestamp=NOW)
    partial = runtime.process_raw_ticks((raw(1),))
    assert partial.engine_updated is False
    assert runtime.snapshot().status is LiveOptionChainStatus.PARTIAL
    stale = runtime.process_raw_ticks((raw(1, ts=NOW - timedelta(seconds=1)),))
    assert stale.stale_count == 1
    runtime.seed_open_interest_baselines({1: 90})
    corrected = runtime.process_raw_ticks((raw(1, price=11, oi=95),))
    assert corrected.accepted_quotes[0].runtime_change_open_interest == 5
    assert runtime.stop().status is LiveOptionChainStatus.STOPPED
    with pytest.raises(RuntimeError):
        runtime.process_raw_ticks((raw(1),))
    assert runtime.clear().status is LiveOptionChainStatus.CLEARED
