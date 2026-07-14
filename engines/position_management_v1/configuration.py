"""
Configuration for Position Management Engine V1.
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real


@dataclass(frozen=True, slots=True)
class PositionManagementV1Configuration:
    allow_partial_exit: bool = True
    partial_exit_fraction: float = 0.50

    auto_exit_on_invalidation: bool = True
    auto_partial_exit_on_objective: bool = False
    auto_full_exit_on_objective: bool = False

    require_filled_execution: bool = True
    reject_position_size_increase: bool = True
    allow_manual_dry_run_exit: bool = True

    minimum_remaining_quantity: int = 1
    history_limit: int = 120

    def __post_init__(self) -> None:
        for name in (
            "allow_partial_exit",
            "auto_exit_on_invalidation",
            "auto_partial_exit_on_objective",
            "auto_full_exit_on_objective",
            "require_filled_execution",
            "reject_position_size_increase",
            "allow_manual_dry_run_exit",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if self.auto_partial_exit_on_objective and self.auto_full_exit_on_objective:
            raise ValueError("automatic partial and full objective exits cannot both be enabled")
        value = self.partial_exit_fraction
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError("partial_exit_fraction must be finite number")
        number = float(value)
        if not isfinite(number) or not 0.0 < number < 1.0:
            raise ValueError("partial_exit_fraction must be between 0.0 and 1.0")
        object.__setattr__(self, "partial_exit_fraction", number)
        for name in ("minimum_remaining_quantity", "history_limit"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be positive integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
