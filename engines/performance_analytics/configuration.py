"""
Performance analytics configuration.
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PerformanceAnalyticsConfiguration:
    enabled: bool = True
    persistence_enabled: bool = True
    journal_path: Path | str = Path("logs") / "performance_journal.jsonl"
    starting_equity: float = 100000.0
    recent_trade_limit: int = 50
    export_directory: Path | str = Path("logs") / "exports"

    def __post_init__(self) -> None:
        for name in ("enabled", "persistence_enabled"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        object.__setattr__(self, "starting_equity", _positive_real(self.starting_equity, "starting_equity"))
        if isinstance(self.recent_trade_limit, bool) or not isinstance(self.recent_trade_limit, int):
            raise TypeError("recent_trade_limit must be positive integer")
        if not 1 <= self.recent_trade_limit <= 1000:
            raise ValueError("recent_trade_limit must be between 1 and 1000")
        object.__setattr__(self, "journal_path", Path(self.journal_path))
        object.__setattr__(self, "export_directory", Path(self.export_directory))


def _positive_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be positive finite number")
    number = float(value)
    if not isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be positive finite number")
    return number

