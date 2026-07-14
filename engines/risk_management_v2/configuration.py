"""
Configuration for Risk Management Engine V2.
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real

from engines.risk_management_v2.enums import PositionSizingMode


@dataclass(frozen=True, slots=True)
class RiskManagementV2Configuration:
    risk_per_trade_fraction: float = 0.005
    maximum_risk_per_trade_fraction: float = 0.01

    maximum_daily_loss_fraction: float = 0.02
    maximum_account_drawdown_fraction: float = 0.10
    maximum_total_exposure_fraction: float = 0.25
    maximum_instrument_exposure_fraction: float = 0.10

    minimum_reward_risk_ratio: float = 1.5

    maximum_position_quantity: int = 1
    maximum_trades_per_day: int = 3
    maximum_consecutive_losses: int = 2

    reduced_size_fraction: float = 0.50
    minimum_position_quantity: int = 1

    sizing_mode: PositionSizingMode = PositionSizingMode.MINIMUM_OF_LIMITS

    require_invalidation_reference: bool = True
    require_structural_objective: bool = True
    reject_low_quality_setups: bool = False
    reduce_moderate_quality_setups: bool = False
    block_after_consecutive_losses: bool = True

    history_limit: int = 120

    def __post_init__(self) -> None:
        fraction_fields = (
            "risk_per_trade_fraction",
            "maximum_risk_per_trade_fraction",
            "maximum_daily_loss_fraction",
            "maximum_account_drawdown_fraction",
            "maximum_total_exposure_fraction",
            "maximum_instrument_exposure_fraction",
        )
        for name in fraction_fields:
            value = _finite_real(getattr(self, name), name)
            if value <= 0.0 or value > 1.0:
                raise ValueError(f"{name} must be greater than 0.0 and at most 1.0")
            object.__setattr__(self, name, value)
        if self.risk_per_trade_fraction > self.maximum_risk_per_trade_fraction:
            raise ValueError("normal risk must not exceed maximum risk")
        if self.maximum_daily_loss_fraction > self.maximum_account_drawdown_fraction:
            raise ValueError("daily loss must not exceed drawdown limit")
        if self.maximum_instrument_exposure_fraction > self.maximum_total_exposure_fraction:
            raise ValueError("instrument exposure must not exceed total exposure")
        object.__setattr__(
            self,
            "minimum_reward_risk_ratio",
            _positive_real(self.minimum_reward_risk_ratio, "minimum_reward_risk_ratio"),
        )
        object.__setattr__(
            self,
            "reduced_size_fraction",
            _finite_real(self.reduced_size_fraction, "reduced_size_fraction"),
        )
        if not 0.0 < self.reduced_size_fraction < 1.0:
            raise ValueError("reduced_size_fraction must be greater than 0.0 and less than 1.0")
        for name in (
            "maximum_position_quantity",
            "maximum_trades_per_day",
            "maximum_consecutive_losses",
            "minimum_position_quantity",
            "history_limit",
        ):
            _positive_int(getattr(self, name), name)
        if self.minimum_position_quantity > self.maximum_position_quantity:
            raise ValueError("minimum quantity cannot exceed maximum quantity")
        if not isinstance(self.sizing_mode, PositionSizingMode):
            raise TypeError("sizing_mode must be PositionSizingMode")
        for name in (
            "require_invalidation_reference",
            "require_structural_objective",
            "reject_low_quality_setups",
            "reduce_moderate_quality_setups",
            "block_after_consecutive_losses",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")


def _finite_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _positive_real(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number <= 0.0:
        raise ValueError(f"{name} must be positive")
    return number


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be positive integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
