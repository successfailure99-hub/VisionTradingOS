from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from application.enums import RuntimeStatus
from application.live_option_chain import LiveOptionChainStatus
from application.live_option_chain_integration import LiveOptionChainIntegrationStatus
from application.option_chain_analytics_integration import (
    OptionChainAnalyticsIntegrationSnapshot,
    OptionChainAnalyticsIntegrationStatus,
    OptionChainAnalyticsProcessingOutcome,
    OptionChainAnalyticsProcessingResult,
)
from core.enums.instrument import Instrument
from tests.test_live_option_chain_integration_models import option_snapshot


NOW = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)


def live_snapshot():
    from application.live_option_chain_integration.models import LiveOptionChainIntegrationSnapshot
    from brokers.zerodha.option_market_data import ZerodhaOptionSubscriptionStatus

    return LiveOptionChainIntegrationSnapshot(
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
        underlying_price_delivery_count=0,
        option_batch_delivery_count=0,
        delivered_option_tick_count=0,
        rejected_option_tick_count=0,
        last_started_at=NOW,
        last_stopped_at=None,
        last_delivery_at=None,
        last_delivery=None,
        option_chain=option_snapshot(),
        last_error=None,
    )


def test_outcome_and_snapshot_immutability():
    outcome = OptionChainAnalyticsProcessingOutcome(
        OptionChainAnalyticsProcessingResult.NOT_READY,
        False,
        False,
        None,
        None,
        NOW,
    )
    with pytest.raises(FrozenInstanceError):
        outcome.processed = True
    with pytest.raises(ValueError):
        OptionChainAnalyticsProcessingOutcome(OptionChainAnalyticsProcessingResult.PROCESSED, True, False, None, None, NOW)
    snapshot = OptionChainAnalyticsIntegrationSnapshot(
        status=OptionChainAnalyticsIntegrationStatus.CREATED,
        application_status=RuntimeStatus.RUNNING,
        live_option_integration_status=LiveOptionChainIntegrationStatus.RUNNING,
        live_option_chain_status=LiveOptionChainStatus.READY,
        analytics_ready=False,
        running=False,
        ready=False,
        underlying=Instrument.NIFTY,
        expiry=date(2026, 7, 30),
        source_option_chain_timestamp=None,
        latest_analytics=None,
        analytics_history_size=0,
        validation_count=0,
        start_count=0,
        stop_count=0,
        processing_count=0,
        analytics_update_count=0,
        duplicate_count=0,
        not_ready_count=0,
        last_started_at=None,
        last_stopped_at=None,
        last_processed_at=None,
        last_outcome=outcome,
        live_option_chain_integration=live_snapshot(),
        last_error=None,
    )
    assert not hasattr(snapshot, "raw_ticks")
    assert not hasattr(snapshot, "runtime")
