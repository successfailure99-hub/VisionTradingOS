from datetime import UTC, date, datetime, timedelta

import pytest

from application.enums import RuntimeInstrument, RuntimeStatus
from application.models import RuntimeConfiguration, RuntimeSnapshot
from application.symbol_runtime import SymbolRuntime
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.tick import Tick
from dashboard.presenters import build_option_chain_view
from desktop.vision_method.live_integration import VisionMethodLiveInspectorBridge
from engines.option_chain.enums import OptionType
from engines.option_chain.models import OptionChainSnapshot, OptionLeg, OptionStrike
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.option_chain_analytics import OptionChainAnalyticsEngine


NOW = datetime(2026, 7, 14, 9, 16, tzinfo=UTC)
EXPIRY = date(2026, 7, 30)


def _tick(timestamp=NOW):
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=25050.0,
        volume=100,
        bid_price=25049.0,
        ask_price=25051.0,
        open_interest=0,
    )


def _snapshot(timestamp=NOW, *, expiry=EXPIRY):
    return OptionChainSnapshot(
        "NIFTY",
        "NSE",
        expiry,
        timestamp,
        25050.0,
        (
            OptionStrike(
                25000.0,
                OptionLeg(OptionType.CALL, 75.0, 1000, 120, 250, 74.5, 75.5),
                OptionLeg(OptionType.PUT, 35.0, 800, -40, 140, 34.5, 35.5),
            ),
            OptionStrike(
                25100.0,
                OptionLeg(OptionType.CALL, 30.0, 900, 80, 180, 29.5, 30.5),
                OptionLeg(OptionType.PUT, 70.0, 1200, 150, 280, 69.5, 70.5),
            ),
        ),
    )


def _analytics(snapshot):
    engine = OptionChainEngine(EventBus(), "NIFTY", "NSE", snapshot.expiry_date)
    state = engine.process(snapshot)
    return OptionChainAnalyticsEngine(underlying=Instrument.NIFTY, expiry=snapshot.expiry_date).process(engine.snapshot, state)


def _runtime():
    runtime = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,), option_expiry_date=EXPIRY),
        RuntimeInstrument.NIFTY,
    )
    runtime.start()
    runtime.process_tick(_tick())
    return runtime


def test_canonical_option_chain_snapshot_and_analytics_are_exposed_on_runtime_snapshot():
    runtime = _runtime()
    snapshot = _snapshot()
    analytics = _analytics(snapshot)

    runtime_snapshot = runtime.process_option_chain_runtime(snapshot, analytics)

    assert runtime_snapshot.option_chain_snapshot == snapshot
    assert runtime_snapshot.option_chain_analytics == analytics
    assert runtime_snapshot.option_chain_runtime.snapshot_status == "READY"
    assert runtime_snapshot.option_chain_runtime.analytics_status == "READY"
    stages = {stage.stage: stage for stage in runtime_snapshot.runtime_verification_report}
    assert stages["Option Snapshot"].status == "READY"
    assert stages["Option Analytics"].status == "READY"


def test_option_chain_newer_feed_timestamp_advances_runtime_and_stale_timestamps_are_rejected():
    runtime = _runtime()
    newer = runtime.process_option_chain_runtime(
        _snapshot(NOW + timedelta(seconds=1)),
        _analytics(_snapshot(NOW + timedelta(seconds=1))),
    )
    assert newer.snapshot_created_at == NOW + timedelta(seconds=1)

    runtime.process_tick(_tick(NOW + timedelta(minutes=5)))
    with pytest.raises(ValueError, match="stale"):
        runtime.process_option_chain(_snapshot(NOW))


def test_option_chain_subsecond_async_arrival_is_synchronized_not_blocked():
    runtime = _runtime()
    option_time = NOW + timedelta(milliseconds=175)
    snapshot = _snapshot(option_time)
    analytics = _analytics(snapshot)

    runtime_snapshot = runtime.process_option_chain_runtime(snapshot, analytics)
    view = build_option_chain_view(runtime_snapshot)

    assert runtime_snapshot.latest_tick_at == NOW
    assert runtime_snapshot.snapshot_created_at == option_time
    assert runtime_snapshot.option_chain_snapshot.timestamp == option_time
    assert runtime_snapshot.option_chain_analytics.timestamp == option_time
    assert runtime_snapshot.option_chain_runtime.latency_ms == pytest.approx(175.0)
    assert runtime_snapshot.option_chain_runtime.synchronization_status == "Option Chain synchronized; Latency = 175 ms; Accepted"
    assert runtime_snapshot.option_chain_runtime.blocking_reason == "-"
    assert view.runtime_latency_ms == pytest.approx(175.0)
    assert view.runtime_synchronization_status == "Option Chain synchronized; Latency = 175 ms; Accepted"
    assert view.runtime_blocking_reason == "-"


def test_option_chain_expiry_mismatch_is_rejected():
    runtime = _runtime()
    with pytest.raises(ValueError, match="expiry"):
        runtime.process_option_chain(_snapshot(expiry=date(2026, 8, 27)))


def test_option_chain_dashboard_reads_canonical_runtime_health():
    runtime = _runtime()
    runtime_snapshot = runtime.process_option_chain_runtime(_snapshot(), _analytics(_snapshot()))

    view = build_option_chain_view(runtime_snapshot)

    assert view.runtime_snapshot_status == "READY"
    assert view.runtime_analytics_status == "READY"
    assert view.snapshot_age_seconds == 0.0
    assert view.runtime_blocking_reason == "-"


def test_vision_bridge_prefers_canonical_runtime_option_inputs_over_provider():
    snapshot = _snapshot()
    analytics = _analytics(snapshot)
    runtime_snapshot = RuntimeSnapshot(
        RuntimeInstrument.NIFTY,
        "1m",
        RuntimeStatus.RUNNING,
        None,
        None,
        None,
        None,
        None,
        None,
        analytics.source_analysis,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        NOW,
        option_chain_snapshot=snapshot,
        option_chain_analytics=analytics,
    )
    bridge = object.__new__(VisionMethodLiveInspectorBridge)
    bridge._option_analytics_provider = lambda instrument: (_snapshot(NOW - timedelta(minutes=1)), None)

    option_chain, option_analytics = VisionMethodLiveInspectorBridge._option_inputs(bridge, runtime_snapshot)

    assert option_chain == snapshot
    assert option_analytics == analytics
