from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from application.models import RuntimeTradingSession
from application.runtime_contract import RuntimeContractContext, RuntimeContractSubject, RuntimeContractValidator
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
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
