from datetime import UTC, datetime

import pytest

from application.live_option_chain import LiveOptionChainStatus
from application.live_option_chain_integration import (
    LiveOptionChainDeliveryKind,
    LiveOptionChainDeliveryResult,
    RawOptionTickBatchDeliveryAdapter,
    UnderlyingPriceDeliveryAdapter,
)


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


class Coordinator:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def deliver_underlying_price(self, price, *, timestamp=None):
        self.calls.append(("price", price, timestamp))
        if self.fail:
            raise RuntimeError("price failed")
        return LiveOptionChainDeliveryResult(LiveOptionChainDeliveryKind.UNDERLYING_PRICE, True, 1, 0, LiveOptionChainStatus.READY, NOW)

    def deliver_option_ticks(self, raw_ticks):
        rows = tuple(raw_ticks)
        self.calls.append(("ticks", rows))
        if self.fail:
            raise RuntimeError("ticks failed")
        return LiveOptionChainDeliveryResult(LiveOptionChainDeliveryKind.OPTION_TICK_BATCH, True, 1, 0, LiveOptionChainStatus.READY, NOW)


def test_adapters_delegate_once_reuse_coordinator_and_reraise():
    coordinator = Coordinator()
    price = UnderlyingPriceDeliveryAdapter(coordinator)
    ticks = RawOptionTickBatchDeliveryAdapter(coordinator)
    rows = [{"instrument_token": 1}]
    assert price.coordinator is coordinator
    assert ticks.coordinator is coordinator
    assert price(1, timestamp=NOW).kind is LiveOptionChainDeliveryKind.UNDERLYING_PRICE
    assert ticks(rows).kind is LiveOptionChainDeliveryKind.OPTION_TICK_BATCH
    assert coordinator.calls == [("price", 1, NOW), ("ticks", tuple(rows))]
    failing = UnderlyingPriceDeliveryAdapter(Coordinator(fail=True))
    with pytest.raises(RuntimeError):
        failing(1)
