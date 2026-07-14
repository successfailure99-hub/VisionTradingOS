"""
Adapter from live option quotes to the existing Option Chain Engine input.
"""

from datetime import datetime
from math import isfinite
from numbers import Real

from application.live_option_chain.configuration import LiveOptionChainConfiguration
from application.live_option_chain.models import ZerodhaLiveOptionQuote
from brokers.zerodha.options import ZerodhaOptionRight, ZerodhaOptionUniverse
from engines.option_chain.enums import OptionType
from engines.option_chain.models import OptionChainSnapshot, OptionLeg, OptionStrike


class IncompleteLiveOptionChainError(ValueError):
    pass


class StaleLiveOptionQuoteError(ValueError):
    pass


class LiveOptionChainAssembler:
    def __init__(
        self,
        *,
        universe: ZerodhaOptionUniverse,
        configuration: LiveOptionChainConfiguration,
    ):
        if not isinstance(universe, ZerodhaOptionUniverse):
            raise TypeError("universe must be ZerodhaOptionUniverse")
        if not isinstance(configuration, LiveOptionChainConfiguration):
            raise TypeError("configuration must be LiveOptionChainConfiguration")
        self._universe = universe
        self._configuration = configuration

    def assemble(
        self,
        *,
        quotes: tuple[ZerodhaLiveOptionQuote, ...],
        underlying_price: float,
        timestamp: datetime,
    ) -> OptionChainSnapshot:
        timestamp = _aware(timestamp, "timestamp")
        price = _positive_float(underlying_price, "underlying_price")
        quote_by_token = {quote.instrument_token: quote for quote in tuple(quotes)}
        strikes = []
        max_age = self._configuration.maximum_quote_age_seconds
        for pair in self._universe.pairs:
            call = quote_by_token.get(pair.call.instrument_token)
            put = quote_by_token.get(pair.put.instrument_token)
            if call is None or put is None:
                if self._configuration.require_all_pairs:
                    raise IncompleteLiveOptionChainError("complete CE/PE quotes are required")
                continue
            _validate_quote(call, pair.call.instrument_token, ZerodhaOptionRight.CALL, self._universe, timestamp, max_age)
            _validate_quote(put, pair.put.instrument_token, ZerodhaOptionRight.PUT, self._universe, timestamp, max_age)
            strikes.append(
                OptionStrike(
                    strike_price=pair.strike,
                    call=_leg(call, OptionType.CALL),
                    put=_leg(put, OptionType.PUT),
                )
            )
        if not strikes:
            raise IncompleteLiveOptionChainError("at least one complete option pair is required")
        exchange = "BSE" if self._universe.venue.value == "BFO" else "NSE"
        return OptionChainSnapshot(
            symbol=self._universe.underlying.value,
            exchange=exchange,
            expiry_date=self._universe.expiry.expiry,
            timestamp=timestamp,
            underlying_price=price,
            strikes=tuple(strikes),
        )


def _leg(quote: ZerodhaLiveOptionQuote, option_type: OptionType) -> OptionLeg:
    return OptionLeg(
        option_type=option_type,
        last_price=quote.last_price,
        open_interest=quote.open_interest,
        change_in_open_interest=quote.runtime_change_open_interest,
        volume=quote.volume,
        bid_price=quote.bid_price,
        ask_price=quote.ask_price,
    )


def _validate_quote(
    quote: ZerodhaLiveOptionQuote,
    token: int,
    right: ZerodhaOptionRight,
    universe: ZerodhaOptionUniverse,
    timestamp: datetime,
    maximum_age_seconds: int,
) -> None:
    if not isinstance(quote, ZerodhaLiveOptionQuote):
        raise TypeError("quotes must contain ZerodhaLiveOptionQuote values")
    if quote.instrument_token != token:
        raise ValueError("quote token does not match option pair")
    if quote.underlying is not universe.underlying:
        raise ValueError("quote underlying does not match universe")
    if quote.expiry != universe.expiry.expiry:
        raise ValueError("quote expiry does not match universe")
    if quote.right is not right:
        raise ValueError("quote right does not match option pair")
    age = (timestamp - quote.exchange_timestamp).total_seconds()
    if age > maximum_age_seconds:
        raise StaleLiveOptionQuoteError("option quote is stale")


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
