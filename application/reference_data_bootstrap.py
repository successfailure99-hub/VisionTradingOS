"""
Desktop reference-data bootstrap helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from application.historical_warmup import HistoricalWarmupConfiguration, HistoricalWarmupCoordinator, derive_daily_ohlc
from application.lifecycle_manager import ApplicationLifecycleManager
from brokers.zerodha.historical import ZerodhaHistoricalDataManager
from brokers.zerodha.instruments import ZerodhaInstrumentRecord, ZerodhaInstrumentResolution, ZerodhaInstrumentType
from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from core.enums.timeframe import TimeFrame


IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)


@dataclass(frozen=True, slots=True)
class ReferenceBootstrapBounds:
    previous_start: datetime
    previous_end: datetime
    current_start: datetime | None
    current_end: datetime | None


def resolve_reference_bootstrap_bounds(now: datetime) -> ReferenceBootstrapBounds:
    if not isinstance(now, datetime):
        raise TypeError("clock result must be datetime")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock result must be timezone-aware")
    local = now.astimezone(IST)
    previous_date = local.date() - timedelta(days=1)
    while previous_date.weekday() >= 5:
        previous_date -= timedelta(days=1)
    previous_start = datetime.combine(previous_date, SESSION_OPEN, tzinfo=IST)
    previous_end = datetime.combine(previous_date, SESSION_CLOSE, tzinfo=IST)

    current_start = None
    current_end = None
    if local.weekday() < 5 and local.time() >= SESSION_OPEN:
        today_start = local.replace(hour=SESSION_OPEN.hour, minute=SESSION_OPEN.minute, second=0, microsecond=0)
        if local.time() >= SESSION_CLOSE:
            completed = local.replace(hour=SESSION_CLOSE.hour, minute=SESSION_CLOSE.minute, second=0, microsecond=0)
        else:
            completed = local.replace(second=0, microsecond=0)
            if completed == local:
                completed -= timedelta(minutes=1)
        if completed > today_start:
            current_start = today_start
            current_end = completed

    return ReferenceBootstrapBounds(
        previous_start=previous_start,
        previous_end=previous_end,
        current_start=current_start,
        current_end=current_end,
    )


def run_reference_data_bootstrap(
    *,
    lifecycle: ApplicationLifecycleManager,
    historical_client,
    subscriptions: tuple[ZerodhaInstrumentSubscription, ...],
    clock,
):
    now = clock()
    bounds = resolve_reference_bootstrap_bounds(now)
    manager = ZerodhaHistoricalDataManager(client=historical_client, clock=clock)
    resolutions = tuple(_resolution_for(subscription) for subscription in subscriptions)
    coordinator = HistoricalWarmupCoordinator(
        lifecycle=lifecycle,
        historical_manager=manager,
        resolutions=resolutions,
        configuration=HistoricalWarmupConfiguration(),
        clock=clock,
    )
    if bounds.current_start is None or bounds.current_end is None:
        return _bootstrap_previous_session_only(
            lifecycle=lifecycle,
            historical_manager=manager,
            resolutions=resolutions,
            start_at=bounds.previous_start,
            end_at=bounds.previous_end,
        )
    return coordinator.warm_up(
        start_at=bounds.current_start,
        end_at=bounds.current_end,
        previous_day_start_at=bounds.previous_start,
        previous_day_end_at=bounds.previous_end,
    )


def _bootstrap_previous_session_only(
    *,
    lifecycle: ApplicationLifecycleManager,
    historical_manager: ZerodhaHistoricalDataManager,
    resolutions: tuple[ZerodhaInstrumentResolution, ...],
    start_at: datetime,
    end_at: datetime,
) -> tuple[object, ...]:
    results = []
    for resolution in resolutions:
        try:
            result = historical_manager.fetch_resolution(
                resolution,
                timeframe=TimeFrame.ONE_MINUTE,
                start_at=start_at,
                end_at=end_at,
            )
            if result.candles:
                daily = derive_daily_ohlc(result.candles, instrument=resolution.instrument)
                lifecycle.orchestrator.process_daily_ohlc(resolution.instrument.value, daily)
            results.append(result)
        except Exception as exc:
            results.append(exc)
    return tuple(results)


def _resolution_for(subscription: ZerodhaInstrumentSubscription) -> ZerodhaInstrumentResolution:
    record = ZerodhaInstrumentRecord(
        instrument_token=subscription.instrument_token,
        exchange_token=subscription.instrument_token,
        tradingsymbol=subscription.instrument.value,
        name=subscription.instrument.value,
        exchange=subscription.exchange,
        segment="INDICES",
        instrument_type=ZerodhaInstrumentType.INDEX,
        expiry=None,
        strike=0.0,
        lot_size=1,
        tick_size=0.05,
    )
    return ZerodhaInstrumentResolution(subscription.instrument, record, subscription)
