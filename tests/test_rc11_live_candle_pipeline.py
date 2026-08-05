from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.event_bus import EventBus
from core.events import CANDLE_CLOSED
from core.models.candle import Candle
from core.models.tick import Tick
from engines.vision_method.opening_range import VisionOpeningRangeRequest, assemble_vision_opening_range_context


IST = ZoneInfo("Asia/Kolkata")
OPEN = datetime(2026, 8, 5, 9, 15, tzinfo=IST)


def tick(timestamp: datetime, *, price: float = 100.0, volume: int = 10) -> Tick:
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=volume,
        bid_price=price - 0.5,
        ask_price=price + 0.5,
        open_interest=0,
    )


def candle(offset: int, *, price: float = 100.0) -> Candle:
    start = OPEN + timedelta(minutes=offset)
    return Candle("NIFTY", "1m", start, start + timedelta(minutes=1), price, price, price, price, 10)


def runtime() -> ApplicationOrchestrator:
    item = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(timeframe="1m"))
    item.start()
    return item


def opening_range_from_history(history: tuple[Candle, ...], timestamp: datetime):
    return assemble_vision_opening_range_context(
        VisionOpeningRangeRequest(
            instrument=RuntimeInstrument.NIFTY,
            timeframe=TimeFrame.ONE_MINUTE,
            trading_date=OPEN.date(),
            timestamp=timestamp,
            candles=history,
        )
    )


def test_rc11_normal_live_stream_produces_15_opening_range_candles():
    bus = EventBus()
    closed = []
    bus.subscribe(CANDLE_CLOSED, closed.append)
    item = ApplicationOrchestrator(bus, RuntimeConfiguration(timeframe="1m"))
    item.start()
    for minute in range(16):
        item.process_tick(tick(OPEN + timedelta(minutes=minute), price=100.0 + minute))

    history = item.get_candle_history("NIFTY")
    snapshot = item.snapshot().runtime_snapshots[0]
    opening = opening_range_from_history(history, OPEN + timedelta(minutes=15))

    assert len(history) == 15
    assert len(closed) == 15
    assert tuple(closed) == history
    assert snapshot.latest_candle.start_time == OPEN + timedelta(minutes=15)
    assert tuple(c.start_time for c in history) == tuple(OPEN + timedelta(minutes=i) for i in range(15))
    assert opening.actual_candle_count == 15
    assert opening.missing_candle_timestamps == ()


def test_rc11_sparse_live_ticks_with_latency_still_close_elapsed_opening_minutes():
    item = runtime()
    item.process_tick(tick(OPEN + timedelta(seconds=4), price=100.0))
    item.process_tick(tick(OPEN + timedelta(minutes=15, milliseconds=350), price=103.0))

    history = item.get_candle_history("NIFTY")
    opening = opening_range_from_history(history, OPEN + timedelta(minutes=15))

    assert len(history) == 15
    assert tuple(c.start_time for c in history) == tuple(OPEN + timedelta(minutes=i) for i in range(15))
    assert tuple(c.volume for c in history[1:]) == (0,) * 14
    assert opening.actual_candle_count == 15
    assert opening.missing_candle_timestamps == ()


def test_rc11_out_of_order_ticks_are_rejected_without_candle_loss():
    item = runtime()
    item.process_tick(tick(OPEN, price=100.0))
    item.process_tick(tick(OPEN + timedelta(minutes=1), price=101.0))

    with pytest.raises(ValueError, match="Stale tick received"):
        item.process_tick(tick(OPEN + timedelta(seconds=30), price=99.0))

    history = item.get_candle_history("NIFTY")
    assert len(history) == 1
    assert history[0].start_time == OPEN


def test_rc11_duplicate_ticks_do_not_create_duplicate_closed_candles():
    item = runtime()
    first = tick(OPEN, price=100.0)
    item.process_tick(first)
    item.process_tick(first)
    item.process_tick(tick(OPEN + timedelta(minutes=1), price=101.0))

    history = item.get_candle_history("NIFTY")
    assert len(history) == 1
    assert history[0].start_time == OPEN


def test_rc11_restart_historical_bootstrap_and_live_continuation_preserve_opening_history():
    item = runtime()
    historical = tuple(candle(index, price=100.0 + index) for index in range(15))
    accepted, _snapshot = item.warm_up_candles("NIFTY", historical)

    item.process_tick(tick(OPEN + timedelta(minutes=15), price=116.0))
    history = item.get_candle_history("NIFTY")
    opening = opening_range_from_history(history, OPEN + timedelta(minutes=15))

    assert accepted == historical
    assert history[:15] == historical
    assert len(history) == 15
    assert opening.actual_candle_count == 15
    assert opening.missing_candle_timestamps == ()


def test_rc11_continuous_live_market_keeps_every_closed_minute_until_close():
    item = runtime()
    for minute in range(376):
        item.process_tick(tick(OPEN + timedelta(minutes=minute), price=100.0 + (minute * 0.01)))

    history = item.get_candle_history("NIFTY")

    assert len(history) == 375
    assert history[0].start_time == OPEN
    assert history[-1].start_time == OPEN + timedelta(minutes=374)
    assert tuple(c.start_time for c in history[:15]) == tuple(OPEN + timedelta(minutes=i) for i in range(15))
