from datetime import UTC, date, datetime, timedelta

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.tick import Tick
from desktop.vision_method.live_integration import _runtime_timestamp
from tests.test_live_option_chain_runtime_gate_c import _analytics, _snapshot


NOW = datetime(2026, 7, 14, 9, 16, tzinfo=UTC)
EXPIRY = date(2026, 7, 30)


def _tick(timestamp=NOW, *, volume=100):
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=25050.0,
        volume=volume,
        bid_price=25049.0,
        ask_price=25051.0,
        open_interest=0,
    )


def _runtime():
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,), option_expiry_date=EXPIRY),
        RuntimeInstrument.NIFTY,
    )
    item.start()
    item.process_tick(_tick())
    return item


def test_option_chain_newer_feed_timestamp_advances_canonical_runtime_timestamp():
    runtime = _runtime()
    option_time = NOW + timedelta(seconds=2)
    option_snapshot = _snapshot(option_time)
    analytics = _analytics(option_snapshot)

    runtime_snapshot = runtime.process_option_chain_runtime(option_snapshot, analytics)

    assert runtime_snapshot.option_chain_snapshot == option_snapshot
    assert runtime_snapshot.option_chain_analytics == analytics
    assert runtime_snapshot.snapshot_created_at == option_time
    assert runtime_snapshot.updated_at == option_time
    assert runtime_snapshot.runtime_session.market_timestamp == option_time
    assert runtime_snapshot.option_chain_runtime.age_seconds == 0.0


def test_stale_option_chain_timestamp_remains_strict_after_canonical_timestamp_advances():
    runtime = _runtime()
    runtime.process_tick(_tick(NOW + timedelta(minutes=5)))

    try:
        runtime.process_option_chain(_snapshot(NOW))
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale option-chain snapshots must remain rejected")


def test_futures_vwap_timestamp_advances_canonical_runtime_timestamp():
    runtime = _runtime()
    vwap_time = NOW + timedelta(seconds=3)

    runtime_snapshot = runtime.process_vwap_tick(
        _tick(vwap_time, volume=25),
        source_type="Futures Proxy",
        source_exchange="NFO",
        trading_symbol="NIFTY26JULFUT",
        instrument_token=12345,
        expiry=EXPIRY,
        live_tick_count=1,
        last_live_volume=25,
        last_delta_volume=25,
        last_live_tick=vwap_time,
        current_accumulated_volume=25,
    )

    assert runtime_snapshot.vwap.timestamp == vwap_time
    assert runtime_snapshot.vwap_source.updated_at == vwap_time
    assert runtime_snapshot.snapshot_created_at == vwap_time
    assert runtime_snapshot.updated_at == vwap_time
    assert runtime_snapshot.runtime_session.market_timestamp == vwap_time


def test_runtime_session_uses_exchange_local_date_for_aware_market_timestamp():
    runtime = _runtime()
    utc_market_time_on_previous_calendar_day = datetime(2026, 8, 6, 20, 0, tzinfo=UTC)

    runtime_snapshot = runtime.process_tick(_tick(utc_market_time_on_previous_calendar_day))

    assert runtime_snapshot.runtime_session.market_timestamp == utc_market_time_on_previous_calendar_day
    assert runtime_snapshot.runtime_session.trading_date == date(2026, 8, 7)


def test_vision_live_bridge_uses_canonical_runtime_timestamp_before_latest_tick():
    runtime = _runtime()
    vwap_time = NOW + timedelta(seconds=4)
    runtime_snapshot = runtime.process_vwap_tick(
        _tick(vwap_time, volume=25),
        source_type="Futures Proxy",
        source_exchange="NFO",
        trading_symbol="NIFTY26JULFUT",
        instrument_token=12345,
        expiry=EXPIRY,
        live_tick_count=1,
        last_live_volume=25,
        last_delta_volume=25,
        last_live_tick=vwap_time,
        current_accumulated_volume=25,
    )

    assert runtime_snapshot.latest_tick_at == NOW
    assert _runtime_timestamp(runtime_snapshot) == vwap_time
