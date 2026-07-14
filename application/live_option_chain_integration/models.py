"""
Immutable models for live option-chain integration snapshots.
"""

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import RuntimeStatus
from application.live_market_data.enums import LiveMarketDataRuntimeStatus
from application.live_option_chain import (
    LiveOptionChainSnapshot,
    LiveOptionChainStatus,
    LiveOptionQuoteBatchResult,
)
from application.live_option_chain_integration.enums import (
    LiveOptionChainDeliveryKind,
    LiveOptionChainIntegrationStatus,
)
from brokers.zerodha.option_market_data import ZerodhaOptionSubscriptionStatus
from core.enums.instrument import Instrument


def _non_negative(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be non-negative integer")
    return value


def _aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class LiveOptionChainDeliveryResult:
    kind: LiveOptionChainDeliveryKind
    accepted: bool
    delivered_count: int
    rejected_count: int
    runtime_status: LiveOptionChainStatus
    completed_at: datetime
    option_batch_result: LiveOptionQuoteBatchResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LiveOptionChainDeliveryKind):
            raise TypeError("kind must be LiveOptionChainDeliveryKind")
        if type(self.accepted) is not bool:
            raise TypeError("accepted must be bool")
        _non_negative(self.delivered_count, "delivered_count")
        _non_negative(self.rejected_count, "rejected_count")
        if self.accepted and self.delivered_count < 1:
            raise ValueError("accepted delivery requires delivered_count")
        if not isinstance(self.runtime_status, LiveOptionChainStatus):
            raise TypeError("runtime_status must be LiveOptionChainStatus")
        _aware(self.completed_at, "completed_at")
        if self.kind is LiveOptionChainDeliveryKind.UNDERLYING_PRICE and self.option_batch_result is not None:
            raise ValueError("option batch result is only valid for option tick delivery")
        if self.option_batch_result is not None and not isinstance(self.option_batch_result, LiveOptionQuoteBatchResult):
            raise TypeError("option_batch_result must be LiveOptionQuoteBatchResult or None")


@dataclass(frozen=True, slots=True)
class LiveOptionChainIntegrationSnapshot:
    status: LiveOptionChainIntegrationStatus
    application_status: RuntimeStatus
    live_market_data_status: LiveMarketDataRuntimeStatus | None
    option_subscription_status: ZerodhaOptionSubscriptionStatus
    option_subscriptions_active: bool
    live_option_chain_status: LiveOptionChainStatus
    running: bool
    ready: bool
    underlying: Instrument
    expiry: date
    configured_option_token_count: int
    quoted_option_token_count: int
    complete_pair_count: int
    expected_pair_count: int
    underlying_price: float | None
    start_count: int
    stop_count: int
    validation_count: int
    underlying_price_delivery_count: int
    option_batch_delivery_count: int
    delivered_option_tick_count: int
    rejected_option_tick_count: int
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    last_delivery_at: datetime | None
    last_delivery: LiveOptionChainDeliveryResult | None
    option_chain: LiveOptionChainSnapshot
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LiveOptionChainIntegrationStatus):
            raise TypeError("status must be LiveOptionChainIntegrationStatus")
        if not isinstance(self.application_status, RuntimeStatus):
            raise TypeError("application_status must be RuntimeStatus")
        if self.live_market_data_status is not None and not isinstance(
            self.live_market_data_status,
            LiveMarketDataRuntimeStatus,
        ):
            raise TypeError("live_market_data_status must be LiveMarketDataRuntimeStatus or None")
        if not isinstance(self.option_subscription_status, ZerodhaOptionSubscriptionStatus):
            raise TypeError("option_subscription_status must be ZerodhaOptionSubscriptionStatus")
        if type(self.option_subscriptions_active) is not bool:
            raise TypeError("option_subscriptions_active must be bool")
        if not isinstance(self.live_option_chain_status, LiveOptionChainStatus):
            raise TypeError("live_option_chain_status must be LiveOptionChainStatus")
        if type(self.running) is not bool or type(self.ready) is not bool:
            raise TypeError("running and ready must be bool")
        if self.running and self.status is not LiveOptionChainIntegrationStatus.RUNNING:
            raise ValueError("running snapshot requires RUNNING status")
        if not isinstance(self.underlying, Instrument):
            raise TypeError("underlying must be Instrument")
        if not isinstance(self.expiry, date) or isinstance(self.expiry, datetime):
            raise TypeError("expiry must be date")
        for name in (
            "configured_option_token_count",
            "quoted_option_token_count",
            "complete_pair_count",
            "expected_pair_count",
            "start_count",
            "stop_count",
            "validation_count",
            "underlying_price_delivery_count",
            "option_batch_delivery_count",
            "delivered_option_tick_count",
            "rejected_option_tick_count",
        ):
            _non_negative(getattr(self, name), name)
        _aware(self.last_started_at, "last_started_at")
        _aware(self.last_stopped_at, "last_stopped_at")
        _aware(self.last_delivery_at, "last_delivery_at")
        if self.last_delivery is not None and not isinstance(self.last_delivery, LiveOptionChainDeliveryResult):
            raise TypeError("last_delivery must be LiveOptionChainDeliveryResult or None")
        if not isinstance(self.option_chain, LiveOptionChainSnapshot):
            raise TypeError("option_chain must be LiveOptionChainSnapshot")
        if self.last_error is not None and not isinstance(self.last_error, str):
            raise TypeError("last_error must be str or None")
