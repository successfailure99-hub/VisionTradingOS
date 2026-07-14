from datetime import UTC, datetime

import pytest

from application.live_option_chain_integration import LiveOptionChainDeliveryKind
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.models.tick import Tick
from tests.test_live_option_chain_integration_lifecycle import build_stack


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def raw(token, oi=100):
    return {"instrument_token": token, "last_price": 10 + token, "volume": token, "oi": oi, "exchange_timestamp": NOW}


def running_coordinator():
    lifecycle, manager, runtime, engine, transport, now = build_stack(start_application=True)
    from application.live_option_chain_integration import LiveOptionChainIntegrationCoordinator

    coordinator = LiveOptionChainIntegrationCoordinator(
        lifecycle=lifecycle,
        subscription_manager=manager,
        live_option_chain_runtime=runtime,
        clock=lambda: now,
    )
    coordinator.start()
    return coordinator, lifecycle, manager, runtime, engine, transport


def test_underlying_price_tick_and_option_batch_delivery():
    coordinator, _lifecycle, _manager, _runtime, engine, _transport = running_coordinator()
    price = coordinator.deliver_underlying_price(25050, timestamp=NOW)
    assert price.kind is LiveOptionChainDeliveryKind.UNDERLYING_PRICE
    tick = Tick(Instrument.NIFTY, Exchange.NSE, NOW, 25051, 1, 25050, 25052, 0)
    coordinator.deliver_underlying_tick(tick)
    with pytest.raises(ValueError):
        coordinator.deliver_underlying_tick(Tick(Instrument.BANKNIFTY, Exchange.NSE, NOW, 1, 1, 1, 1, 0))
    rows = [raw(1, 100), raw(2, 200), raw(3, 300), raw(4, 400)]
    result = coordinator.deliver_option_ticks(iter(rows))
    assert result.kind is LiveOptionChainDeliveryKind.OPTION_TICK_BATCH
    assert result.delivered_count == 4
    assert engine.state is not None
    snapshot = coordinator.snapshot()
    assert snapshot.option_batch_delivery_count == 1
    assert snapshot.delivered_option_tick_count == 4
    assert rows[0]["oi"] == 100


def test_delivery_rejections_do_not_increment_success_counters():
    coordinator, *_ = running_coordinator()
    before = coordinator.snapshot()
    with pytest.raises(TypeError):
        coordinator.deliver_option_ticks({"instrument_token": 1})
    after = coordinator.snapshot()
    assert after.option_batch_delivery_count == before.option_batch_delivery_count
    with pytest.raises(TypeError):
        coordinator.deliver_option_ticks("bad")
