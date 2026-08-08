"""
Canonical exchange trading-calendar and session authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from core.enums.exchange import Exchange


IST = ZoneInfo("Asia/Kolkata")
DEFAULT_SESSION_OPEN = time(9, 15)
DEFAULT_SESSION_CLOSE = time(15, 30)
DEFAULT_PRE_OPEN = time(9, 0)


class ExchangeSessionPhase(str, Enum):
    PRE_MARKET = "PRE_MARKET"
    OPEN = "OPEN"
    POST_MARKET = "POST_MARKET"
    CLOSED = "CLOSED"
    NON_TRADING_DAY = "NON_TRADING_DAY"


@dataclass(frozen=True, slots=True)
class ExchangeHoliday:
    exchange: Exchange
    trading_date: date
    name: str = "Holiday"

    def __post_init__(self) -> None:
        if not isinstance(self.exchange, Exchange):
            raise TypeError("exchange must be Exchange")
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date")
        if not isinstance(self.name, str):
            raise TypeError("name must be text")
        object.__setattr__(self, "name", self.name.strip() or "Holiday")


@dataclass(frozen=True, slots=True)
class ExchangeSession:
    exchange: Exchange
    timestamp: datetime
    local_timestamp: datetime
    phase: ExchangeSessionPhase
    trading_date: date | None
    previous_completed_trading_date: date | None
    next_trading_date: date | None
    session_open: datetime | None
    session_close: datetime | None
    timezone: ZoneInfo = IST
    calendar_status: str = "READY"
    reason: str = "-"

    def __post_init__(self) -> None:
        if not isinstance(self.exchange, Exchange):
            raise TypeError("exchange must be Exchange")
        for field_name in ("timestamp", "local_timestamp"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be datetime")
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if not isinstance(self.phase, ExchangeSessionPhase):
            raise TypeError("phase must be ExchangeSessionPhase")
        for field_name in ("trading_date", "previous_completed_trading_date", "next_trading_date"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, date) or isinstance(value, datetime)):
                raise TypeError(f"{field_name} must be date or None")
        for field_name in ("session_open", "session_close"):
            value = getattr(self, field_name)
            if value is not None:
                if not isinstance(value, datetime):
                    raise TypeError(f"{field_name} must be datetime or None")
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError(f"{field_name} must be timezone-aware")
        for field_name in ("calendar_status", "reason"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")

    @property
    def is_trading_day(self) -> bool:
        return self.trading_date == self.local_timestamp.date() and self.phase is not ExchangeSessionPhase.NON_TRADING_DAY

    @property
    def is_open(self) -> bool:
        return self.phase is ExchangeSessionPhase.OPEN


class ExchangeTradingCalendar:
    """
    Cheap deterministic exchange-session authority for runtime decisions.

    Holiday data is supplied locally/configurably. Runtime lookups do not use
    network calls, broker APIs, dashboard state, or wall-clock dates directly.
    """

    def __init__(self, holidays: tuple[ExchangeHoliday, ...] = ()):
        normalized: dict[Exchange, set[date]] = {exchange: set() for exchange in Exchange}
        for holiday in holidays:
            if not isinstance(holiday, ExchangeHoliday):
                raise TypeError("holidays must contain ExchangeHoliday values")
            normalized.setdefault(holiday.exchange, set()).add(holiday.trading_date)
        self._holidays = {exchange: frozenset(days) for exchange, days in normalized.items()}

    def is_trading_day(self, value: date, exchange: Exchange | str) -> bool:
        exchange = _exchange(exchange)
        if not isinstance(value, date) or isinstance(value, datetime):
            raise TypeError("value must be date")
        return value.weekday() < 5 and value not in self._holidays.get(exchange, frozenset())

    def previous_trading_day(self, value: date, exchange: Exchange | str) -> date:
        exchange = _exchange(exchange)
        if not isinstance(value, date) or isinstance(value, datetime):
            raise TypeError("value must be date")
        candidate = value - timedelta(days=1)
        while not self.is_trading_day(candidate, exchange):
            candidate -= timedelta(days=1)
        return candidate

    def next_trading_day(self, value: date, exchange: Exchange | str) -> date:
        exchange = _exchange(exchange)
        if not isinstance(value, date) or isinstance(value, datetime):
            raise TypeError("value must be date")
        candidate = value + timedelta(days=1)
        while not self.is_trading_day(candidate, exchange):
            candidate += timedelta(days=1)
        return candidate

    def resolve_active_session(self, timestamp: datetime, exchange: Exchange | str) -> ExchangeSession:
        exchange = _exchange(exchange)
        local = _local_timestamp(timestamp)
        local_date = local.date()
        if not self.is_trading_day(local_date, exchange):
            previous = self.previous_trading_day(local_date, exchange)
            next_day = self.next_trading_day(local_date, exchange)
            reason = self.non_trading_reason(local_date, exchange)
            return ExchangeSession(
                exchange=exchange,
                timestamp=timestamp,
                local_timestamp=local,
                phase=ExchangeSessionPhase.NON_TRADING_DAY,
                trading_date=None,
                previous_completed_trading_date=previous,
                next_trading_date=next_day,
                session_open=None,
                session_close=None,
                reason=reason,
            )
        session_open = datetime.combine(local_date, DEFAULT_SESSION_OPEN, tzinfo=IST)
        session_close = datetime.combine(local_date, DEFAULT_SESSION_CLOSE, tzinfo=IST)
        if local.time() < DEFAULT_PRE_OPEN:
            phase = ExchangeSessionPhase.CLOSED
            previous = self.previous_trading_day(local_date, exchange)
            reason = "Exchange has not reached pre-market."
        elif local.time() < DEFAULT_SESSION_OPEN:
            phase = ExchangeSessionPhase.PRE_MARKET
            previous = self.previous_trading_day(local_date, exchange)
            reason = "Exchange is in pre-market."
        elif local.time() <= DEFAULT_SESSION_CLOSE:
            phase = ExchangeSessionPhase.OPEN
            previous = self.previous_trading_day(local_date, exchange)
            reason = "-"
        else:
            phase = ExchangeSessionPhase.POST_MARKET
            previous = local_date
            reason = "Exchange session is closed for the day."
        next_day = self.next_trading_day(local_date, exchange)
        return ExchangeSession(
            exchange=exchange,
            timestamp=timestamp,
            local_timestamp=local,
            phase=phase,
            trading_date=local_date,
            previous_completed_trading_date=previous,
            next_trading_date=next_day,
            session_open=session_open,
            session_close=session_close,
            reason=reason,
        )

    def resolve_previous_completed_session(self, timestamp: datetime, exchange: Exchange | str) -> date:
        return self.resolve_active_session(timestamp, exchange).previous_completed_trading_date

    def classify_market_phase(self, timestamp: datetime, exchange: Exchange | str) -> ExchangeSessionPhase:
        return self.resolve_active_session(timestamp, exchange).phase

    def non_trading_reason(self, value: date, exchange: Exchange | str) -> str:
        exchange = _exchange(exchange)
        if not isinstance(value, date) or isinstance(value, datetime):
            raise TypeError("value must be date")
        if value.weekday() >= 5:
            return "Exchange is closed for the weekend."
        if value in self._holidays.get(exchange, frozenset()):
            return "Exchange is closed for a configured holiday."
        return "Exchange is closed for a non-trading day."


DEFAULT_EXCHANGE_CALENDAR = ExchangeTradingCalendar()


def _exchange(value: Exchange | str) -> Exchange:
    if isinstance(value, Exchange):
        return value
    if isinstance(value, str):
        return Exchange.from_value(value)
    raise TypeError("exchange must be Exchange or str")


def _local_timestamp(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(IST)
