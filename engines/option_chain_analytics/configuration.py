"""
Configuration for Option Chain Analytics Engine V1.
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real


@dataclass(frozen=True, slots=True)
class OptionChainAnalyticsConfiguration:
    minimum_price_change: float = 0.05
    minimum_oi_change: int = 1
    strong_pressure_ratio: float = 1.5
    strong_bias_score: int = 3
    history_limit: int = 120

    def __post_init__(self) -> None:
        price = _real(self.minimum_price_change, "minimum_price_change")
        if price < 0:
            raise ValueError("minimum_price_change must be non-negative")
        object.__setattr__(self, "minimum_price_change", price)
        oi = _int(self.minimum_oi_change, "minimum_oi_change")
        if oi < 0:
            raise ValueError("minimum_oi_change must be non-negative")
        ratio = _real(self.strong_pressure_ratio, "strong_pressure_ratio")
        if ratio <= 1.0:
            raise ValueError("strong_pressure_ratio must be greater than 1.0")
        object.__setattr__(self, "strong_pressure_ratio", ratio)
        score = _int(self.strong_bias_score, "strong_bias_score")
        if score <= 0:
            raise ValueError("strong_bias_score must be positive")
        limit = _int(self.history_limit, "history_limit")
        if limit <= 0:
            raise ValueError("history_limit must be positive")


def _real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be integer")
    return value
