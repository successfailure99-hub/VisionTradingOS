from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from application.cross_feed_timestamp_telemetry import (
    CrossFeedTimestampObservation,
    CrossFeedTimestampTelemetry,
)
from application.enums import RuntimeStatus
from application.live_market_data.enums import LiveFeedWatchdogState, LiveMarketDataRuntimeStatus
from application.models import RuntimeSnapshot
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.tick import Tick
from dashboard.presenters import build_runtime_view
from engines.option_paper_execution.enums import OptionPaperExecutionStyle
from engines.option_paper_execution.models import DirectionalOptionSellingConfiguration
from tests.test_dashboard_presenters import lifecycle
from tests.test_live_option_chain_runtime_gate_c import _analytics, _snapshot


NOW = datetime(2026, 8, 17, 4, 26, 51, tzinfo=UTC)
OBSERVED = datetime(2026, 8, 17, 4, 26, 58, tzinfo=UTC)
EXPIRY = date(2026, 8, 27)


def _observation(option_time, *, status="ACCEPTED", reason="-"):
    return CrossFeedTimestampObservation(
        observed_at=OBSERVED,
        instrument="NIFTY",
        canonical_nifty_timestamp=NOW,
        last_delivered_nifty_timestamp=NOW,
        option_snapshot_timestamp=option_time,
        option_snapshot_observed_at=option_time,
        option_receipt_timestamp=option_time - timedelta(milliseconds=25),
        option_minus_canonical_seconds=(option_time - NOW).total_seconds(),
        option_minus_last_delivered_seconds=(option_time - NOW).total_seconds(),
        nifty_feed_age_seconds=(OBSERVED - NOW).total_seconds(),
        watchdog_state="healthy",
        market_data_health="running",
        websocket_state="connected",
        runtime_contract_status=status,
        runtime_contract_reason=reason,
        option_expiry=EXPIRY,
        option_source="LiveOptionChainRuntime",
        session_date=date(2026, 8, 17),
    )


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


def _runtime(tmp_path: Path):
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,), option_expiry_date=EXPIRY),
        RuntimeInstrument.NIFTY,
    )
    item._cross_feed_timestamp_telemetry = CrossFeedTimestampTelemetry(
        tmp_path / "cross_feed.jsonl",
        max_events=8,
        max_samples=8,
        clock=lambda: OBSERVED,
    )
    item.start()
    item.process_tick(_tick())
    return item


def _runtime_with_directional_option_paper(tmp_path: Path):
    item = SymbolRuntime(
        EventBus(),
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.NIFTY,),
            option_expiry_date=EXPIRY,
            directional_option_selling_configuration=DirectionalOptionSellingConfiguration(
                execution_style=OptionPaperExecutionStyle.DIRECTIONAL_OPTION_SELLING_PAPER,
            ),
        ),
        RuntimeInstrument.NIFTY,
    )
    item._cross_feed_timestamp_telemetry = CrossFeedTimestampTelemetry(
        tmp_path / "cross_feed.jsonl",
        max_events=8,
        max_samples=8,
        clock=lambda: OBSERVED,
    )
    item.start()
    item.process_tick(_tick())
    return item


def _live_feed_snapshot():
    return SimpleNamespace(
        watchdog_state=LiveFeedWatchdogState.HEALTHY,
        status=LiveMarketDataRuntimeStatus.RUNNING,
        last_delivered_market_timestamp=NOW,
        websocket=SimpleNamespace(status="connected"),
    )


def test_cross_feed_observation_preserves_timestamps_and_positive_skew(tmp_path):
    telemetry = CrossFeedTimestampTelemetry(tmp_path / "trace.jsonl", max_events=4, max_samples=4, clock=lambda: OBSERVED)
    option_time = NOW + timedelta(seconds=6, milliseconds=342)

    assert telemetry.record(_observation(option_time)) is True

    summary = telemetry.summary()
    assert summary.sample_count == 1
    assert summary.latest_skew_seconds == pytest.approx(6.342)
    assert summary.latest_nifty_feed_age_seconds == pytest.approx(7.0)
    assert summary.latest_watchdog_state == "healthy"
    assert "access_token" not in (tmp_path / "trace.jsonl").read_text(encoding="utf-8")


def test_cross_feed_observation_records_zero_and_negative_skew(tmp_path):
    telemetry = CrossFeedTimestampTelemetry(tmp_path / "trace.jsonl", max_events=4, max_samples=4, clock=lambda: OBSERVED)
    telemetry.record(_observation(NOW))
    telemetry.record(_observation(NOW - timedelta(milliseconds=250)))

    summary = telemetry.summary()
    assert summary.sample_count == 2
    assert summary.latest_skew_seconds == pytest.approx(-0.25)
    assert summary.max_skew_seconds == pytest.approx(0.0)


def test_cross_feed_telemetry_is_bounded_in_memory_and_persistence(tmp_path):
    path = tmp_path / "trace.jsonl"
    telemetry = CrossFeedTimestampTelemetry(path, max_events=2, max_samples=2, clock=lambda: OBSERVED)

    for index in range(3):
        telemetry.record(_observation(NOW + timedelta(seconds=index)))

    assert telemetry.summary().sample_count == 2
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_cross_feed_persistence_failure_does_not_raise_or_clear_memory():
    class FailingStore:
        def record(self, row):
            raise RuntimeError("access_token exploded")

    telemetry = CrossFeedTimestampTelemetry("ignored.jsonl", store=FailingStore(), clock=lambda: OBSERVED)

    assert telemetry.record(_observation(NOW + timedelta(seconds=1))) is False
    summary = telemetry.summary()
    assert summary.sample_count == 1
    assert "[REDACTED]" in summary.last_persistence_error


def test_symbol_runtime_records_accepted_option_snapshot_without_advancing_canonical_clock(tmp_path):
    runtime = _runtime(tmp_path)
    option_time = NOW + timedelta(milliseconds=175)
    option_snapshot = _snapshot(option_time, expiry=EXPIRY)
    analytics = _analytics(option_snapshot)

    runtime_snapshot = runtime.process_option_chain_runtime(
        option_snapshot,
        analytics,
        live_market_data_snapshot=_live_feed_snapshot(),
        option_receipt_timestamp=option_time - timedelta(milliseconds=25),
    )

    assert runtime_snapshot.snapshot_created_at == NOW
    assert runtime_snapshot.runtime_session.market_timestamp == NOW
    assert runtime_snapshot.cross_feed_timestamp_summary.sample_count == 1
    assert runtime_snapshot.cross_feed_timestamp_summary.latest_skew_seconds == pytest.approx(0.175)
    assert runtime_snapshot.cross_feed_timestamp_summary.latest_runtime_contract_status == "ACCEPTED"


def test_symbol_runtime_records_rejected_option_snapshot_without_suppressing_validation(tmp_path):
    runtime = _runtime(tmp_path)
    option_snapshot = _snapshot(NOW + timedelta(seconds=2), expiry=EXPIRY)

    with pytest.raises(ValueError, match="future"):
        runtime.process_option_chain(
            option_snapshot,
            live_market_data_snapshot=_live_feed_snapshot(),
            option_receipt_timestamp=NOW + timedelta(seconds=2),
        )

    summary = runtime.snapshot().cross_feed_timestamp_summary
    assert summary.sample_count == 1
    assert summary.latest_skew_seconds == pytest.approx(2.0)
    assert summary.latest_runtime_contract_status == "REJECTED"
    assert "future" in summary.latest_runtime_contract_reason
    assert runtime.snapshot().snapshot_created_at == NOW


def test_dashboard_runtime_view_exposes_cross_feed_summary_read_only():
    summary = CrossFeedTimestampTelemetry(clock=lambda: OBSERVED).summary()
    runtime = RuntimeSnapshot(
        RuntimeInstrument.NIFTY,
        "1m",
        RuntimeStatus.RUNNING,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        NOW,
        cross_feed_timestamp_summary=summary,
    )

    view = build_runtime_view(lifecycle(runtime))

    assert view.cross_feed_sample_count == 0
    assert view.cross_feed_watchdog_state == "-"


def test_configured_directional_option_paper_style_reaches_runtime_and_dashboard(tmp_path):
    runtime = _runtime_with_directional_option_paper(tmp_path)

    runtime_snapshot = runtime.snapshot()
    view = build_runtime_view(lifecycle(runtime_snapshot))

    assert runtime_snapshot.option_paper_execution_style == "directional_option_selling_paper"
    assert view.option_paper_execution_style == "directional_option_selling_paper"
