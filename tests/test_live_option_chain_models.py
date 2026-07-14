from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from application.live_option_chain import (
    LiveOptionChainSnapshot,
    LiveOptionChainStatus,
    LiveOptionQuoteBatchResult,
    ZerodhaLiveOptionQuote,
)
from brokers.zerodha.options import ZerodhaOptionRight
from core.enums.instrument import Instrument


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def quote(**overrides):
    values = {
        "instrument_token": 1,
        "underlying": Instrument.NIFTY,
        "expiry": date(2026, 7, 30),
        "strike": 25000,
        "right": ZerodhaOptionRight.CALL,
        "last_price": 100.0,
        "volume": 10,
        "open_interest": 1000,
        "runtime_change_open_interest": 0,
        "bid_price": 99.5,
        "ask_price": 100.5,
        "exchange_timestamp": NOW,
        "received_at": NOW,
    }
    values.update(overrides)
    return ZerodhaLiveOptionQuote(**values)


def test_valid_quote_zero_price_and_signed_runtime_change():
    item = quote(last_price=0, runtime_change_open_interest=-10)
    assert item.last_price == 0.0
    assert item.runtime_change_open_interest == -10


def test_quote_validation_and_crossed_market():
    with pytest.raises(ValueError):
        quote(instrument_token=True)
    with pytest.raises(ValueError):
        quote(volume=-1)
    with pytest.raises(ValueError):
        quote(open_interest=-1)
    with pytest.raises(ValueError):
        quote(bid_price=101, ask_price=100)
    with pytest.raises(ValueError):
        quote(exchange_timestamp=datetime(2026, 7, 14, 9, 15))


def test_batch_counts_and_snapshot_immutability():
    item = quote()
    batch = LiveOptionQuoteBatchResult(1, (item,), 0, 0, 0, True, True)
    with pytest.raises(ValueError):
        LiveOptionQuoteBatchResult(2, (item,), 0, 0, 0, False, False)
    snapshot = LiveOptionChainSnapshot(
        status=LiveOptionChainStatus.READY,
        underlying=Instrument.NIFTY,
        expiry=date(2026, 7, 30),
        configured_token_count=2,
        quoted_token_count=1,
        fresh_token_count=1,
        complete_pair_count=0,
        expected_pair_count=1,
        received_tick_count=1,
        accepted_tick_count=1,
        duplicate_tick_count=0,
        stale_tick_count=0,
        rejected_tick_count=0,
        assembly_count=0,
        engine_update_count=0,
        underlying_price=25000,
        latest_quotes=(item,),
        latest_option_chain_snapshot=None,
        latest_option_chain_analysis=None,
        last_batch_result=batch,
        last_received_at=NOW,
        last_assembled_at=None,
        last_error=None,
    )
    with pytest.raises(FrozenInstanceError):
        snapshot.status = LiveOptionChainStatus.ERROR
    assert not hasattr(snapshot, "raw_tick")
    assert not hasattr(snapshot, "client")
