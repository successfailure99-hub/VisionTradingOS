from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from application.models import RuntimeTradingSession
from application.runtime_contract import (
    RuntimeContractContext,
    RuntimeContractSubject,
    RuntimeContractValidator,
    RuntimeTemporalClass,
    temporal_class_for,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.building_candle import BuildingCandle
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from core.event_bus import EventBus
from core.models.tick import Tick
from dashboard.presenters import build_runtime_view
from tests.test_dashboard_presenters import lifecycle


NOW = datetime(2026, 7, 29, 9, 31, tzinfo=UTC)


def _session(trading_date=date(2026, 7, 29), status="ACTIVE"):
    return RuntimeTradingSession(
        instrument=RuntimeInstrument.NIFTY,
        exchange="NSE",
        market_timestamp=NOW,
        trading_date=trading_date,
        previous_completed_trading_date=date(2026, 7, 28),
        cpr_trading_date=trading_date,
        camarilla_trading_date=trading_date,
        adr_trading_date=trading_date,
        vwap_trading_date=trading_date,
        status=status,
    )


def _context(timestamp=NOW):
    return RuntimeContractContext(
        instrument=RuntimeInstrument.NIFTY,
        timeframe="1m",
        runtime_timestamp=timestamp,
        trading_date=timestamp.date(),
        session=_session(timestamp.date()),
        previous_runtime_timestamp=timestamp - timedelta(seconds=1),
    )


def _report_for(snapshot, *, object_name="Snapshot", context=None):
    return RuntimeContractValidator().validate_many(
        ((object_name, snapshot, "SymbolRuntime", "TestProducer", "TestConsumer"),),
        context or _context(),
    )


def test_runtime_contract_accepts_valid_runtime_subject():
    subject = RuntimeContractSubject(
        instrument=RuntimeInstrument.NIFTY,
        timeframe="1m",
        timestamp=NOW,
        trading_date=NOW.date(),
        session=_session(),
    )

    report = _report_for(subject, object_name="RuntimeSnapshot")

    assert report.valid is True
    assert report.violations == ()


def test_runtime_contract_reports_timezone_mismatch():
    subject = SimpleNamespace(symbol="NIFTY", timeframe="1m", timestamp=datetime(2026, 7, 29, 9, 31), trading_date=NOW.date())

    report = _report_for(subject)

    assert report.valid is False
    assert report.violations[0].reason == "Timezone mismatch"


def test_runtime_contract_reports_trading_date_mismatch():
    subject = SimpleNamespace(symbol="NIFTY", timeframe="1m", timestamp=NOW - timedelta(days=1))

    report = _report_for(subject)

    assert report.valid is False
    assert report.violations[0].reason == "Trading date mismatch"


def test_runtime_contract_accepts_previous_session_daily_ohlc_reference_for_active_runtime_date():
    runtime_timestamp = datetime(2026, 8, 7, 9, 31, tzinfo=UTC)
    previous_daily = DailyOHLC(date(2026, 8, 6), 100.0, 110.0, 90.0, 105.0)

    report = _report_for(previous_daily, object_name="DailyOHLC", context=_context(runtime_timestamp))

    assert report.valid is True
    assert report.violations == ()


def test_runtime_contract_declares_temporal_classes_for_runtime_objects():
    assert temporal_class_for("Candle") is RuntimeTemporalClass.INTERVAL
    assert temporal_class_for("DailyOHLC") is RuntimeTemporalClass.HISTORICAL_REFERENCE
    assert temporal_class_for("CPR") is RuntimeTemporalClass.ACTIVE_SESSION
    assert temporal_class_for("Camarilla") is RuntimeTemporalClass.ACTIVE_SESSION
    assert temporal_class_for("ADR") is RuntimeTemporalClass.ACTIVE_SESSION
    assert temporal_class_for("VWAP") is RuntimeTemporalClass.ACTIVE_SESSION
    assert temporal_class_for("OptionChainSnapshot") is RuntimeTemporalClass.EVENT_TIMESTAMPED
    assert temporal_class_for("VisionMethodSnapshot") is RuntimeTemporalClass.ACTIVE_SESSION


def test_runtime_contract_rejects_active_session_cpr_from_wall_clock_weekend_date():
    friday_runtime = datetime(2026, 8, 7, 9, 31, tzinfo=UTC)
    cpr_from_calendar_saturday = SimpleNamespace(
        symbol="NIFTY",
        timeframe="1m",
        timestamp=friday_runtime,
        trading_date=date(2026, 8, 8),
    )

    report = _report_for(cpr_from_calendar_saturday, object_name="CPR", context=_context(friday_runtime))

    assert report.valid is False
    assert report.violations[0].reason == "Trading date mismatch"
    assert report.violations[0].expected == "2026-08-07"
    assert report.violations[0].actual == "2026-08-08"


def test_runtime_contract_rejects_future_daily_ohlc_reference():
    runtime_timestamp = datetime(2026, 8, 7, 9, 31, tzinfo=UTC)
    future_daily = DailyOHLC(date(2026, 8, 8), 100.0, 110.0, 90.0, 105.0)

    report = _report_for(future_daily, object_name="DailyOHLC", context=_context(runtime_timestamp))

    assert report.valid is False
    assert report.violations[0].reason == "Future historical date"


def test_runtime_contract_accepts_weekend_previous_session_reference():
    monday_runtime = datetime(2026, 8, 10, 9, 31, tzinfo=UTC)
    friday_daily = DailyOHLC(date(2026, 8, 7), 100.0, 110.0, 90.0, 105.0)

    report = _report_for(friday_daily, object_name="DailyOHLC", context=_context(monday_runtime))

    assert report.valid is True
    assert report.violations == ()


def test_runtime_contract_reports_session_mismatch():
    subject = SimpleNamespace(symbol="NIFTY", timeframe="1m", timestamp=NOW, trading_date=NOW.date(), session=_session(status="CLOSED"))

    report = _report_for(subject)

    assert report.valid is False
    assert report.violations[0].reason == "Session mismatch"


def test_runtime_contract_reports_timestamp_ordering_and_future_timestamp():
    future = SimpleNamespace(symbol="NIFTY", timeframe="1m", timestamp=NOW + timedelta(seconds=1), trading_date=NOW.date())
    backwards = RuntimeContractSubject(
        instrument=RuntimeInstrument.NIFTY,
        timeframe="1m",
        timestamp=NOW - timedelta(seconds=2),
        trading_date=NOW.date(),
    )

    future_report = _report_for(future)
    backwards_report = _report_for(backwards, object_name="RuntimeSnapshot")

    assert future_report.violations[0].reason == "Future timestamp"
    assert backwards_report.violations[0].reason == "Runtime ordering mismatch"


def test_runtime_contract_accepts_live_building_candle_interval_boundary():
    runtime_timestamp = datetime(2026, 8, 7, 14, 21, 59, 509494, tzinfo=UTC)
    active_candle = BuildingCandle(
        symbol=Instrument.NIFTY,
        timeframe=TimeFrame.ONE_MINUTE,
        start_time=datetime(2026, 8, 7, 14, 21, tzinfo=UTC),
        end_time=datetime(2026, 8, 7, 14, 22, tzinfo=UTC),
        open=25000.0,
        high=25010.0,
        low=24995.0,
        close=25005.0,
        volume=100,
    )

    report = _report_for(active_candle, object_name="Candle", context=_context(runtime_timestamp))

    assert report.valid is True
    assert report.violations == ()


def test_runtime_contract_rejects_candle_interval_starting_after_runtime_timestamp():
    runtime_timestamp = datetime(2026, 8, 7, 14, 21, 59, 509494, tzinfo=UTC)
    future_candle = Candle(
        symbol="NIFTY",
        timeframe="1m",
        start_time=datetime(2026, 8, 7, 14, 22, tzinfo=UTC),
        end_time=datetime(2026, 8, 7, 14, 23, tzinfo=UTC),
        open=25000.0,
        high=25010.0,
        low=24995.0,
        close=25005.0,
        volume=100,
    )

    report = _report_for(future_candle, object_name="Candle", context=_context(runtime_timestamp))

    assert report.valid is False
    assert report.violations[0].reason == "Future timestamp"
    assert "start_time <=" in report.violations[0].expected


def test_runtime_contract_reports_ownership_instrument_and_timeframe_failures():
    subject = SimpleNamespace(symbol="BANKNIFTY", timeframe="5m", timestamp=NOW, trading_date=NOW.date())

    report = _report_for(subject)
    reasons = {item.reason for item in report.violations}

    assert "Instrument mismatch" in reasons
    assert "Timeframe mismatch" in reasons
    assert report.violations[0].owner == "SymbolRuntime"
    assert report.violations[0].producer == "TestProducer"
    assert report.violations[0].consumer == "TestConsumer"


def test_symbol_runtime_snapshot_includes_canonical_contract_report_and_dashboard_row():
    runtime = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    runtime.start()
    runtime.process_tick(
        Tick(
            symbol=Instrument.NIFTY,
            exchange=Exchange.NSE,
            timestamp=NOW,
            last_price=100.0,
            volume=100,
            bid_price=99.5,
            ask_price=100.5,
            open_interest=0,
        )
    )

    snapshot = runtime.snapshot()
    view = build_runtime_view(lifecycle(snapshot))
    rows = {row.name: row for row in view.component_health}

    assert snapshot.runtime_contract_report is not None
    assert rows["Runtime Contract"].status in {"READY", "FAILED"}
    assert rows["Runtime Contract"].owner != "-"


def test_dashboard_displays_structured_runtime_contract_failure():
    runtime = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    runtime.start()
    runtime.process_tick(
        Tick(
            symbol=Instrument.NIFTY,
            exchange=Exchange.NSE,
            timestamp=NOW,
            last_price=100.0,
            volume=100,
            bid_price=99.5,
            ask_price=100.5,
            open_interest=0,
        )
    )
    bad_subject = SimpleNamespace(symbol="NIFTY", timeframe="1m", timestamp=datetime(2026, 7, 29, 9, 31), trading_date=NOW.date())
    report = _report_for(bad_subject, object_name="ADR")
    snapshot = replace(runtime.snapshot(), runtime_contract_report=report)

    view = build_runtime_view(lifecycle(snapshot))
    rows = {row.name: row for row in view.component_health}

    assert rows["Runtime Contract"].status == "FAILED"
    assert "Runtime Contract Failed" in rows["Runtime Contract"].detail
    assert "Reason=Timezone mismatch" in rows["Runtime Contract"].detail
    assert "Object=ADR" in rows["Runtime Contract"].detail


def test_symbol_runtime_accepts_previous_daily_ohlc_for_current_cpr_camarilla_and_runtime_contract():
    runtime_timestamp = datetime(2026, 8, 7, 9, 31, tzinfo=UTC)
    previous_day = date(2026, 8, 6)
    runtime = SymbolRuntime(EventBus(), RuntimeConfiguration(adr_period=5), RuntimeInstrument.NIFTY)
    runtime.start()
    runtime.process_daily_ohlc(
        DailyOHLC(previous_day, 100.0, 110.0, 90.0, 105.0),
        levels_trading_date=runtime_timestamp.date(),
    )
    runtime.process_tick(
        Tick(
            symbol=Instrument.NIFTY,
            exchange=Exchange.NSE,
            timestamp=runtime_timestamp,
            last_price=106.0,
            volume=100,
            bid_price=105.5,
            ask_price=106.5,
            open_interest=0,
        )
    )

    snapshot = runtime.snapshot()
    rows = {row.name: row for row in build_runtime_view(lifecycle(snapshot)).component_health}

    assert snapshot.cpr.trading_date == runtime_timestamp.date()
    assert snapshot.camarilla.trading_date == runtime_timestamp.date()
    assert runtime._daily_ohlc_history[-1].trading_date == previous_day
    assert snapshot.runtime_contract_report.valid is True
    assert rows["Runtime Contract"].status == "READY"


def test_symbol_runtime_accepts_multi_day_adr_history_before_runtime_date():
    runtime_timestamp = datetime(2026, 8, 7, 9, 31, tzinfo=UTC)
    runtime = SymbolRuntime(EventBus(), RuntimeConfiguration(adr_period=5), RuntimeInstrument.NIFTY)
    runtime.start()
    for offset in reversed(range(5)):
        day = runtime_timestamp.date() - timedelta(days=offset + 1)
        runtime.process_daily_ohlc(DailyOHLC(day, 100.0 + offset, 110.0 + offset, 90.0 + offset, 105.0 + offset))
    runtime.process_tick(
        Tick(
            symbol=Instrument.NIFTY,
            exchange=Exchange.NSE,
            timestamp=runtime_timestamp,
            last_price=106.0,
            volume=100,
            bid_price=105.5,
            ask_price=106.5,
            open_interest=0,
        )
    )

    snapshot = runtime.snapshot()

    assert snapshot.adr is not None
    assert snapshot.adr_runtime.state == "READY"
    assert snapshot.runtime_contract_report.valid is True


def test_symbol_runtime_daily_ohlc_duplicate_history_is_reported_as_runtime_failure():
    runtime_timestamp = datetime(2026, 8, 7, 9, 31, tzinfo=UTC)
    previous_daily = DailyOHLC(date(2026, 8, 6), 100.0, 110.0, 90.0, 105.0)
    runtime = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    runtime.start()
    runtime.process_daily_ohlc(previous_daily, levels_trading_date=runtime_timestamp.date())
    runtime.process_tick(
        Tick(
            symbol=Instrument.NIFTY,
            exchange=Exchange.NSE,
            timestamp=runtime_timestamp,
            last_price=106.0,
            volume=100,
            bid_price=105.5,
            ask_price=106.5,
            open_interest=0,
        )
    )
    runtime._daily_ohlc_history = (previous_daily, previous_daily)

    report = runtime.snapshot().runtime_contract_report

    assert report.valid is False
    assert report.integrity_violations[0].object_name == "DailyOHLC"
    assert report.integrity_violations[0].invariant == "Daily OHLC history has no duplicate trading dates"


def test_symbol_runtime_future_daily_ohlc_still_surfaces_dashboard_runtime_failure():
    runtime_timestamp = datetime(2026, 8, 7, 9, 31, tzinfo=UTC)
    future_daily = DailyOHLC(date(2026, 8, 8), 100.0, 110.0, 90.0, 105.0)
    runtime = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    runtime.start()
    runtime.process_tick(
        Tick(
            symbol=Instrument.NIFTY,
            exchange=Exchange.NSE,
            timestamp=runtime_timestamp,
            last_price=106.0,
            volume=100,
            bid_price=105.5,
            ask_price=106.5,
            open_interest=0,
        )
    )
    runtime._daily_ohlc_history = (future_daily,)

    snapshot = runtime.snapshot()
    rows = {row.name: row for row in build_runtime_view(lifecycle(snapshot)).component_health}

    assert snapshot.runtime_contract_report.valid is False
    assert snapshot.runtime_contract_report.violations[0].reason == "Future historical date"
    assert rows["Runtime Contract"].status == "FAILED"
    assert "Object=DailyOHLC" in rows["Runtime Contract"].detail
