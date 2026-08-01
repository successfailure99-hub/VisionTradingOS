"""
Trade Journal & Performance Analytics V1 configuration.
"""

from dataclasses import dataclass
from pathlib import Path
from math import isfinite
from numbers import Real


@dataclass(frozen=True, slots=True)
class TradeJournalV1Configuration:
    minimum_trades_for_statistics: int = 5
    minimum_trades_for_trend: int = 10
    flat_pnl_tolerance: float = 0.0
    history_limit: int = 10000
    equity_curve_limit: int = 10000
    reject_duplicate_trade_ids: bool = True
    require_closed_position: bool = True
    require_dry_run: bool = True
    require_analysis_only: bool = True
    calculate_setup_statistics: bool = True
    calculate_instrument_statistics: bool = True
    calculate_confidence_statistics: bool = True
    persistence_enabled: bool = True
    journal_path: Path | None = None
    checkpoint_path: Path | None = None

    def __post_init__(self) -> None:
        for name in (
            "minimum_trades_for_statistics",
            "minimum_trades_for_trend",
            "history_limit",
            "equity_curve_limit",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be positive integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if isinstance(self.flat_pnl_tolerance, bool) or not isinstance(self.flat_pnl_tolerance, Real):
            raise TypeError("flat_pnl_tolerance must be finite non-negative number")
        tolerance = float(self.flat_pnl_tolerance)
        if not isfinite(tolerance) or tolerance < 0.0:
            raise ValueError("flat_pnl_tolerance must be finite and non-negative")
        object.__setattr__(self, "flat_pnl_tolerance", tolerance)
        for name in (
            "reject_duplicate_trade_ids",
            "require_closed_position",
            "require_dry_run",
            "require_analysis_only",
            "calculate_setup_statistics",
            "calculate_instrument_statistics",
            "calculate_confidence_statistics",
            "persistence_enabled",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if self.journal_path is not None:
            object.__setattr__(self, "journal_path", Path(self.journal_path))
        if self.checkpoint_path is not None:
            object.__setattr__(self, "checkpoint_path", Path(self.checkpoint_path))
