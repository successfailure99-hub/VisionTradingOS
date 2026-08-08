from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from application import ApplicationOrchestrator, RuntimeConfiguration, RuntimeInstrument
from application.exchange_calendar import (
    ExchangeHoliday,
    ExchangeSessionPhase,
    ExchangeTradingCalendar,
)
from application.reference_data_bootstrap import (
    _active_reference_trading_date,
    resolve_reference_bootstrap_bounds,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick


IST = ZoneInfo("Asia/Kolkata")


def test_calendar_resolves_weekend_previous_and_next_sessions():
    calendar = ExchangeTradingCalendar()
    saturday = datetime(2026, 8, 8, 10, 0, tzinfo=IST)

    session = calendar.resolve_active_session(saturday, Exchange.NSE)

    assert session.phase is ExchangeSessionPhase.NON_TRADING_DAY
    assert session.trading_date is None
    assert session.previous_completed_trading_date == date(2026, 8, 7)
    assert session.next_trading_date == date(2026, 8, 10)


def test_calendar_resolves_configured_weekday_holiday_without_calendar_day_assumption():
    holiday = ExchangeHoliday(Exchange.NSE, date(2026, 8, 12), "Fixture Holiday")
    calendar = ExchangeTradingCalendar((holiday,))
    holiday_time = datetime(2026, 8, 12, 10, 0, tzinfo=IST)

    session = calendar.resolve_active_session(holiday_time, Exchange.NSE)

    assert calendar.is_trading_day(date(2026, 8, 12), Exchange.NSE) is False
    assert session.phase is ExchangeSessionPhase.NON_TRADING_DAY
    assert session.trading_date is None
    assert session.previous_completed_trading_date == date(2026, 8, 11)
    assert session.next_trading_date == date(2026, 8, 13)


def test_reference_bootstrap_uses_calendar_previous_session_across_holiday():
    holiday = ExchangeHoliday(Exchange.NSE, date(2026, 8, 12), "Fixture Holiday")
    calendar = ExchangeTradingCalendar((holiday,))
    thursday_pre_market = datetime(2026, 8, 13, 8, 30, tzinfo=IST)

    bounds = resolve_reference_bootstrap_bounds(thursday_pre_market, exchange="NSE", calendar=calendar)
    active = _active_reference_trading_date(
        thursday_pre_market,
        bounds,
        exchange="NSE",
        calendar=calendar,
    )

    assert bounds.previous_start.date() == date(2026, 8, 11)
    assert bounds.previous_end.date() == date(2026, 8, 11)
    assert bounds.current_start is None
    assert active == date(2026, 8, 13)


def test_symbol_runtime_marks_configured_holiday_as_market_closed_not_failed():
    holiday = ExchangeHoliday(Exchange.NSE, date(2026, 8, 12), "Fixture Holiday")
    runtime = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(
            instruments=(RuntimeInstrument.NIFTY,),
            exchange_holidays=(holiday,),
            adr_period=5,
        ),
    )
    runtime.start()
    symbol_runtime = runtime.get_runtime(RuntimeInstrument.NIFTY)
    symbol_runtime.process_daily_ohlc(
        DailyOHLC(date(2026, 8, 11), 100.0, 110.0, 90.0, 105.0),
        levels_trading_date=date(2026, 8, 11),
    )
    runtime.process_tick(
        Tick(
            symbol=Instrument.NIFTY,
            exchange=Exchange.NSE,
            timestamp=datetime(2026, 8, 12, 10, 0, tzinfo=IST),
            last_price=106.0,
            volume=100,
            bid_price=105.5,
            ask_price=106.5,
            open_interest=0,
        )
    )

    snapshot = symbol_runtime.snapshot()

    assert snapshot.runtime_session.status == "MARKET_CLOSED"
    assert snapshot.runtime_session.trading_date is None
    assert snapshot.runtime_session.previous_completed_trading_date == date(2026, 8, 11)
    assert snapshot.runtime_contract_report.valid is True


def test_option_chain_same_session_accepts_utc_representation_of_ist_market_instant():
    runtime = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY,), option_expiry_date=date(2026, 8, 27)),
    )
    runtime.start()
    symbol_runtime = runtime.get_runtime(RuntimeInstrument.NIFTY)
    tick_time = datetime(2026, 8, 6, 20, 0, tzinfo=UTC)

    runtime.process_tick(
        Tick(
            symbol=Instrument.NIFTY,
            exchange=Exchange.NSE,
            timestamp=tick_time,
            last_price=25000.0,
            volume=100,
            bid_price=24999.5,
            ask_price=25000.5,
            open_interest=0,
        )
    )

    assert symbol_runtime.snapshot().runtime_session.trading_date == date(2026, 8, 7)


def test_runtime_critical_modules_do_not_reintroduce_weekday_session_authority():
    root = Path(__file__).resolve().parents[1]
    critical = (
        "application/symbol_runtime.py",
        "application/reference_data_bootstrap.py",
        "application/runtime_contract.py",
        "dashboard/presenters.py",
    )

    for relative in critical:
        text = (root / relative).read_text()
        assert ".weekday(" not in text
        assert ".isoweekday(" not in text
