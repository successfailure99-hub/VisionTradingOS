"""
Raw Zerodha option tick normalizer.
"""

from collections.abc import Mapping
from datetime import datetime
from math import isfinite
from numbers import Real

from application.live_option_chain.models import ZerodhaLiveOptionQuote
from brokers.zerodha.market_data.timestamps import default_zerodha_clock, normalize_zerodha_tick_timestamp
from brokers.zerodha.option_market_data import ZerodhaOptionSubscriptionEntry


class ZerodhaLiveOptionQuoteNormalizer:
    def __init__(
        self,
        *,
        entries: tuple[ZerodhaOptionSubscriptionEntry, ...],
        clock=None,
        reject_crossed_market: bool = True,
    ):
        self._entries = _entry_map(entries)
        self._clock = clock or default_zerodha_clock
        if type(reject_crossed_market) is not bool:
            raise TypeError("reject_crossed_market must be bool")
        self._reject_crossed_market = reject_crossed_market

    def normalize(
        self,
        raw_tick: Mapping[str, object],
        *,
        baseline_open_interest: int,
    ) -> ZerodhaLiveOptionQuote:
        if not isinstance(raw_tick, Mapping):
            raise TypeError("raw option tick must be a mapping")
        if isinstance(baseline_open_interest, bool) or not isinstance(baseline_open_interest, int):
            raise TypeError("baseline_open_interest must be int")
        token = _positive_int(raw_tick.get("instrument_token"), "instrument_token")
        entry = self._entries.get(token)
        if entry is None:
            raise ValueError("unknown option instrument token")
        last_price = _non_negative_float(raw_tick.get("last_price"), "last_price")
        volume = _session_volume(raw_tick)
        open_interest = _non_negative_int(raw_tick.get("oi", 0), "oi")
        exchange_timestamp = _timestamp(raw_tick, self._clock)
        received_at = self._now()
        bid, ask = _depth_prices(raw_tick.get("depth"))
        if self._reject_crossed_market and bid is not None and ask is not None and bid > ask:
            raise ValueError("crossed option market")
        contract = entry.contract
        return ZerodhaLiveOptionQuote(
            instrument_token=contract.instrument_token,
            underlying=contract.underlying,
            expiry=contract.expiry,
            strike=contract.strike,
            right=contract.right,
            last_price=last_price,
            volume=volume,
            open_interest=open_interest,
            runtime_change_open_interest=open_interest - baseline_open_interest,
            bid_price=bid,
            ask_price=ask,
            exchange_timestamp=exchange_timestamp,
            received_at=received_at,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock result must be datetime")
        return _aware(value)


def _entry_map(entries: tuple[ZerodhaOptionSubscriptionEntry, ...]) -> dict[int, ZerodhaOptionSubscriptionEntry]:
    values = tuple(entries)
    if not values:
        raise ValueError("entries cannot be empty")
    result = {}
    for entry in values:
        if not isinstance(entry, ZerodhaOptionSubscriptionEntry):
            raise TypeError("entries must contain ZerodhaOptionSubscriptionEntry values")
        token = entry.subscription.instrument_token
        if token in result:
            raise ValueError("duplicate option entry token")
        result[token] = entry
    return result


def _positive_int(value, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be positive integer")
    return value


def _non_negative_int(value, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be non-negative integer")
    return value


def _session_volume(raw_tick: Mapping[str, object]) -> int:
    for field_name in ("volume_traded", "volume", "traded_quantity"):
        value = raw_tick.get(field_name)
        if value is not None:
            return _non_negative_int(value, field_name)
    return 0


def _non_negative_float(value, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be finite non-negative number")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{field_name} must be finite non-negative number")
    return number


def _timestamp(raw_tick: Mapping[str, object], clock) -> datetime:
    return normalize_zerodha_tick_timestamp(
        raw_tick,
        clock=clock,
        field_names=("exchange_timestamp", "timestamp"),
    ).timestamp


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=IST)
    return value


def _depth_prices(depth) -> tuple[float | None, float | None]:
    if depth is None:
        return None, None
    if not isinstance(depth, Mapping):
        raise ValueError("depth must be mapping")
    return _first_price(depth.get("buy")), _first_price(depth.get("sell"))


def _first_price(levels) -> float | None:
    if not levels:
        return None
    if not isinstance(levels, (list, tuple)):
        raise ValueError("depth levels must be a sequence")
    first = levels[0]
    if not isinstance(first, Mapping):
        raise ValueError("depth level must be mapping")
    price = first.get("price")
    if price is None:
        return None
    return _non_negative_float(price, "depth price")
