"""
Paper Trading & Position Lifecycle V1 configuration.
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real

from engines.paper_trading.enums import PaperIntrabarPolicy


@dataclass(frozen=True, slots=True)
class PaperTradingConfiguration:
    enabled: bool = True
    auto_create_order: bool = True
    slippage_points: float = 0.0
    fixed_fee_per_trade: float = 0.0
    fee_percentage: float = 0.0
    intrabar_policy: PaperIntrabarPolicy = PaperIntrabarPolicy.STOP_FIRST
    exit_on_strategy_invalidation: bool = False
    close_at_session_end: bool = True
    cancel_pending_at_session_end: bool = True
    max_active_positions_per_instrument: int = 1
    stale_data_seconds: int = 300

    def __post_init__(self) -> None:
        for name in ("enabled", "auto_create_order", "exit_on_strategy_invalidation", "close_at_session_end", "cancel_pending_at_session_end"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        object.__setattr__(self, "slippage_points", _non_negative_real(self.slippage_points, "slippage_points"))
        object.__setattr__(self, "fixed_fee_per_trade", _non_negative_real(self.fixed_fee_per_trade, "fixed_fee_per_trade"))
        object.__setattr__(self, "fee_percentage", _non_negative_real(self.fee_percentage, "fee_percentage"))
        if not isinstance(self.intrabar_policy, PaperIntrabarPolicy):
            raise TypeError("intrabar_policy must be PaperIntrabarPolicy")
        if isinstance(self.max_active_positions_per_instrument, bool) or not isinstance(self.max_active_positions_per_instrument, int) or self.max_active_positions_per_instrument < 1:
            raise ValueError("max_active_positions_per_instrument must be positive integer")
        if isinstance(self.stale_data_seconds, bool) or not isinstance(self.stale_data_seconds, int) or self.stale_data_seconds < 1:
            raise ValueError("stale_data_seconds must be positive integer")


def _non_negative_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite non-negative number")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite non-negative number")
    return number

