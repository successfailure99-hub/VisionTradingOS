"""
Zerodha raw tick normalizer.
"""

from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import datetime
from math import isfinite

from core.models.tick import Tick

from brokers.zerodha.market_data.subscription_registry import ZerodhaSubscriptionRegistry
from brokers.zerodha.market_data.timestamps import default_zerodha_clock, normalize_zerodha_tick_timestamp


def _default_clock() -> datetime:
    return default_zerodha_clock()


class ZerodhaTickNormalizer:
    def __init__(
        self,
        registry: ZerodhaSubscriptionRegistry,
        *,
        clock=None,
    ):
        if not isinstance(registry, ZerodhaSubscriptionRegistry):
            raise TypeError("registry must be ZerodhaSubscriptionRegistry")
        self._registry = registry
        self._clock = clock or _default_clock

    def normalize(
        self,
        raw_tick: Mapping[str, object],
    ) -> Tick:
        if not isinstance(raw_tick, Mapping):
            raise TypeError("raw_tick must be a mapping")
        original = deepcopy(raw_tick)
        token = self._token(raw_tick.get("instrument_token"))
        subscription = self._registry.get_by_token(token)
        if subscription is None:
            raise ValueError("Unknown instrument token")
        last_price = self._positive_float(raw_tick.get("last_price"), "last_price")
        timestamp = self._timestamp(raw_tick)
        volume_value = raw_tick.get("volume_traded")
        if volume_value is None:
            volume_value = raw_tick.get("volume", 0)
        volume = self._non_negative_int(volume_value, "volume")
        open_interest = self._non_negative_int(raw_tick.get("oi", 0), "oi")
        bid_price, ask_price = self._depth(raw_tick.get("depth"))
        if bid_price > 0 and ask_price > 0 and bid_price > ask_price:
            raise ValueError("bid_price cannot exceed ask_price")
        if raw_tick != original:
            raise ValueError("raw_tick must not be mutated")
        return Tick(
            symbol=subscription.instrument,
            exchange=subscription.exchange,
            timestamp=timestamp,
            last_price=last_price,
            volume=volume,
            bid_price=bid_price,
            ask_price=ask_price,
            open_interest=open_interest,
        )

    def normalize_batch(
        self,
        raw_ticks: Iterable[Mapping[str, object]],
    ) -> tuple[Tick, ...]:
        return tuple(self.normalize(raw_tick) for raw_tick in raw_ticks)

    def _token(self, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("instrument_token must be a positive integer")
        if value <= 0:
            raise ValueError("instrument_token must be positive")
        return value

    def _positive_float(self, value: object, field_name: str) -> float:
        number = self._float(value, field_name)
        if number <= 0:
            raise ValueError(f"{field_name} must be greater than zero")
        return number

    def _non_negative_float(self, value: object, field_name: str) -> float:
        number = self._float(value, field_name)
        if number < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return number

    def _float(self, value: object, field_name: str) -> float:
        if isinstance(value, bool):
            raise TypeError(f"{field_name} must be numeric")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be numeric") from exc
        if not isfinite(number):
            raise ValueError(f"{field_name} must be finite")
        return number

    def _non_negative_int(self, value: object, field_name: str) -> int:
        if isinstance(value, bool):
            raise TypeError(f"{field_name} must be an integer")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an integer") from exc
        if number < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return number

    def _timestamp(self, raw_tick: Mapping[str, object]) -> datetime:
        return normalize_zerodha_tick_timestamp(raw_tick, clock=self._clock).timestamp

    def _depth(self, value: object) -> tuple[float, float]:
        if not isinstance(value, Mapping):
            return 0.0, 0.0
        bid = self._side_price(value.get("buy"), "bid_price")
        ask = self._side_price(value.get("sell"), "ask_price")
        return bid, ask

    def _side_price(self, rows: object, field_name: str) -> float:
        if not rows:
            return 0.0
        if not isinstance(rows, list | tuple):
            return 0.0
        first = rows[0] if rows else None
        if not isinstance(first, Mapping) or "price" not in first:
            return 0.0
        return self._non_negative_float(first["price"], field_name)
