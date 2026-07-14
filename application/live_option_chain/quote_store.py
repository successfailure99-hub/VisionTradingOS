"""
Thread-safe in-memory live option quote state.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from math import isfinite
from numbers import Real
from threading import RLock

from application.live_option_chain.enums import LiveOptionQuoteUpdateResult
from application.live_option_chain.models import ZerodhaLiveOptionQuote
from brokers.zerodha.option_market_data import ZerodhaOptionSubscriptionEntry


class LiveOptionQuoteStore:
    def __init__(
        self,
        entries: tuple[ZerodhaOptionSubscriptionEntry, ...],
        clock=None,
    ):
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()
        self._underlying_price: float | None = None
        self._underlying_timestamp: datetime | None = None
        self._set_entries(entries)
        self._quotes: dict[int, ZerodhaLiveOptionQuote] = {}
        self._baselines: dict[int, int] = {}

    @property
    def underlying_price(self) -> float | None:
        with self._lock:
            return self._underlying_price

    @property
    def underlying_timestamp(self) -> datetime | None:
        with self._lock:
            return self._underlying_timestamp

    def set_underlying_price(
        self,
        price: float,
        *,
        timestamp: datetime,
    ) -> None:
        value = _positive_float(price, "underlying price")
        timestamp = _aware(timestamp, "timestamp")
        with self._lock:
            if self._underlying_timestamp is not None and timestamp < self._underlying_timestamp:
                raise ValueError("stale underlying price timestamp")
            self._underlying_price = value
            self._underlying_timestamp = timestamp

    def seed_open_interest_baselines(
        self,
        baselines: Mapping[int, int],
    ) -> None:
        if not isinstance(baselines, Mapping):
            raise TypeError("baselines must be mapping")
        with self._lock:
            for token, baseline in baselines.items():
                token = self._known_token(token)
                if isinstance(baseline, bool) or not isinstance(baseline, int) or baseline < 0:
                    raise ValueError("open interest baseline must be non-negative integer")
                self._baselines[token] = baseline

    def baseline_for(
        self,
        instrument_token: int,
        *,
        current_open_interest: int,
    ) -> int:
        if isinstance(current_open_interest, bool) or not isinstance(current_open_interest, int) or current_open_interest < 0:
            raise ValueError("current_open_interest must be non-negative integer")
        with self._lock:
            token = self._known_token(instrument_token)
            if token not in self._baselines:
                self._baselines[token] = current_open_interest
            return self._baselines[token]

    def update(
        self,
        quote: ZerodhaLiveOptionQuote,
    ) -> LiveOptionQuoteUpdateResult:
        if not isinstance(quote, ZerodhaLiveOptionQuote):
            raise TypeError("quote must be ZerodhaLiveOptionQuote")
        with self._lock:
            token = self._known_token(quote.instrument_token)
            previous = self._quotes.get(token)
            if previous == quote:
                return LiveOptionQuoteUpdateResult.DUPLICATE
            if previous is not None and quote.exchange_timestamp < previous.exchange_timestamp:
                return LiveOptionQuoteUpdateResult.STALE
            self._quotes[token] = quote
            return LiveOptionQuoteUpdateResult.ACCEPTED

    def latest_by_token(
        self,
        instrument_token: int,
    ) -> ZerodhaLiveOptionQuote | None:
        with self._lock:
            return self._quotes.get(self._known_token(instrument_token))

    def all_latest(self) -> tuple[ZerodhaLiveOptionQuote, ...]:
        with self._lock:
            return tuple(
                self._quotes[token]
                for token in self._tokens
                if token in self._quotes
            )

    def baselines(self) -> tuple[tuple[int, int], ...]:
        with self._lock:
            return tuple((token, self._baselines[token]) for token in self._tokens if token in self._baselines)

    def clear_quotes(self) -> None:
        with self._lock:
            self._quotes.clear()
            self._baselines.clear()

    def reset(
        self,
        entries: tuple[ZerodhaOptionSubscriptionEntry, ...],
    ) -> None:
        with self._lock:
            self._set_entries(entries)
            self._quotes.clear()
            self._baselines.clear()
            self._underlying_price = None
            self._underlying_timestamp = None

    def _set_entries(self, entries: tuple[ZerodhaOptionSubscriptionEntry, ...]) -> None:
        values = tuple(entries)
        if not values:
            raise ValueError("entries cannot be empty")
        tokens = []
        for entry in values:
            if not isinstance(entry, ZerodhaOptionSubscriptionEntry):
                raise TypeError("entries must contain ZerodhaOptionSubscriptionEntry values")
            token = entry.subscription.instrument_token
            if token in tokens:
                raise ValueError("duplicate option token")
            tokens.append(token)
        self._entries = values
        self._tokens = tuple(tokens)

    def _known_token(self, token: int) -> int:
        if isinstance(token, bool) or not isinstance(token, int) or token <= 0:
            raise ValueError("instrument token must be positive integer")
        if token not in self._tokens:
            raise ValueError("unknown option instrument token")
        return token


def _positive_float(value: Real, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be positive finite number")
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{field_name} must be positive finite number")
    return number


def _aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value
