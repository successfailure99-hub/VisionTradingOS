from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from application.enums import RuntimeStatus
from application.live_option_chain import LiveOptionChainStatus
from application.live_option_chain_integration import (
    LiveOptionChainDeliveryKind,
    LiveOptionChainDeliveryResult,
    LiveOptionChainIntegrationSnapshot,
    LiveOptionChainIntegrationStatus,
)
from brokers.zerodha.option_market_data import ZerodhaOptionSubscriptionStatus
from core.enums.instrument import Instrument
from tests.test_live_option_chain_models import quote


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def option_snapshot():
    from application.live_option_chain import LiveOptionChainSnapshot

    return LiveOptionChainSnapshot(
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
        latest_quotes=(quote(),),
        latest_option_chain_snapshot=None,
        latest_option_chain_analysis=None,
        last_batch_result=None,
        last_received_at=NOW,
        last_assembled_at=None,
        last_error=None,
    )


def test_delivery_result_and_snapshot_validation_and_immutability():
    delivery = LiveOptionChainDeliveryResult(
        LiveOptionChainDeliveryKind.UNDERLYING_PRICE,
        True,
        1,
        0,
        LiveOptionChainStatus.READY,
        NOW,
    )
    with pytest.raises(FrozenInstanceError):
        delivery.accepted = False
    with pytest.raises(ValueError):
        LiveOptionChainDeliveryResult(LiveOptionChainDeliveryKind.UNDERLYING_PRICE, True, 0, 0, LiveOptionChainStatus.READY, NOW)
    with pytest.raises(ValueError):
        LiveOptionChainDeliveryResult(LiveOptionChainDeliveryKind.UNDERLYING_PRICE, True, 1, 0, LiveOptionChainStatus.READY, datetime(2026, 7, 14))

    snapshot = LiveOptionChainIntegrationSnapshot(
        status=LiveOptionChainIntegrationStatus.RUNNING,
        application_status=RuntimeStatus.RUNNING,
        live_market_data_status=None,
        option_subscription_status=ZerodhaOptionSubscriptionStatus.ACTIVE,
        option_subscriptions_active=True,
        live_option_chain_status=LiveOptionChainStatus.READY,
        running=True,
        ready=True,
        underlying=Instrument.NIFTY,
        expiry=date(2026, 7, 30),
        configured_option_token_count=2,
        quoted_option_token_count=1,
        complete_pair_count=0,
        expected_pair_count=1,
        underlying_price=25000,
        start_count=1,
        stop_count=0,
        validation_count=1,
        underlying_price_delivery_count=1,
        option_batch_delivery_count=0,
        delivered_option_tick_count=0,
        rejected_option_tick_count=0,
        last_started_at=NOW,
        last_stopped_at=None,
        last_delivery_at=NOW,
        last_delivery=delivery,
        option_chain=option_snapshot(),
        last_error=None,
    )
    with pytest.raises(FrozenInstanceError):
        snapshot.running = False
    assert not hasattr(snapshot, "raw_ticks")
    assert not hasattr(snapshot, "client")
    assert not hasattr(snapshot, "runtime")
