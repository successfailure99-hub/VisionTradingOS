"""
Production Safety & Recovery Engine V1 configuration.
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real

from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.instrument import Instrument
from engines.market_context_v2.models import SUPPORTED_INSTRUMENTS


@dataclass(frozen=True, slots=True)
class ProductionSafetyV1Configuration:
    safety_mode: ExecutionSafetyMode = ExecutionSafetyMode.ANALYSIS_ONLY
    broker_mode: BrokerExecutionMode = BrokerExecutionMode.DRY_RUN
    maximum_daily_loss_fraction: float = 0.02
    maximum_account_drawdown_fraction: float = 0.10
    maximum_trades_per_day: int = 3
    maximum_consecutive_losses: int = 2
    market_data_stale_after_seconds: float = 30.0
    market_data_warning_after_seconds: float = 15.0
    block_on_trade_lifecycle_error: bool = True
    block_on_journal_runtime_error: bool = True
    block_on_application_error: bool = True
    block_new_trades_with_active_execution: bool = True
    block_new_trades_with_active_position: bool = True
    require_manual_release_after_kill_switch: bool = True
    require_manual_release_after_daily_loss: bool = True
    require_manual_release_after_drawdown: bool = True
    enabled_instruments: tuple[Instrument, ...] = (
        Instrument.NIFTY,
        Instrument.BANKNIFTY,
        Instrument.SENSEX,
    )
    incident_history_limit: int = 500
    snapshot_history_limit: int = 120

    def __post_init__(self) -> None:
        if self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            raise ValueError("Production safety V1 supports only ANALYSIS_ONLY")
        if self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("Production safety V1 supports only DRY_RUN")
        daily = _fraction(self.maximum_daily_loss_fraction, "maximum_daily_loss_fraction")
        drawdown = _fraction(self.maximum_account_drawdown_fraction, "maximum_account_drawdown_fraction")
        if daily > drawdown:
            raise ValueError("daily-loss fraction cannot exceed drawdown fraction")
        object.__setattr__(self, "maximum_daily_loss_fraction", daily)
        object.__setattr__(self, "maximum_account_drawdown_fraction", drawdown)
        for name in ("maximum_trades_per_day", "maximum_consecutive_losses", "incident_history_limit", "snapshot_history_limit"):
            _positive_int(getattr(self, name), name)
        warning = _positive_real(self.market_data_warning_after_seconds, "market_data_warning_after_seconds")
        stale = _positive_real(self.market_data_stale_after_seconds, "market_data_stale_after_seconds")
        if warning >= stale:
            raise ValueError("market data warning threshold must be less than stale threshold")
        object.__setattr__(self, "market_data_warning_after_seconds", warning)
        object.__setattr__(self, "market_data_stale_after_seconds", stale)
        for name in (
            "block_on_trade_lifecycle_error",
            "block_on_journal_runtime_error",
            "block_on_application_error",
            "block_new_trades_with_active_execution",
            "block_new_trades_with_active_position",
            "require_manual_release_after_kill_switch",
            "require_manual_release_after_daily_loss",
            "require_manual_release_after_drawdown",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        instruments = tuple(self.enabled_instruments)
        if not instruments:
            raise ValueError("enabled instruments cannot be empty")
        seen = set()
        for instrument in instruments:
            if instrument not in SUPPORTED_INSTRUMENTS:
                raise ValueError("enabled instruments must be NIFTY, BANKNIFTY or SENSEX")
            if instrument in seen:
                raise ValueError("enabled instruments must be unique")
            seen.add(instrument)
        object.__setattr__(self, "enabled_instruments", instruments)


def _fraction(value, name):
    number = _positive_real(value, name)
    if number > 1.0:
        raise ValueError(f"{name} must be at most 1.0")
    return number


def _positive_real(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite positive number")
    number = float(value)
    if not isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be positive integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
