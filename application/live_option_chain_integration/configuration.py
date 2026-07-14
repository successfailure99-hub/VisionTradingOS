"""
Configuration for live option-chain runtime integration.
"""

from dataclasses import dataclass


def _require_bool(value: bool, field_name: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")
    return value


@dataclass(frozen=True, slots=True)
class LiveOptionChainIntegrationConfiguration:
    require_application_running: bool = True
    require_live_market_data_running_for_spot: bool = False
    stop_live_option_runtime_on_shutdown: bool = True
    deactivate_option_subscriptions_on_shutdown: bool = False

    def __post_init__(self) -> None:
        _require_bool(self.require_application_running, "require_application_running")
        _require_bool(
            self.require_live_market_data_running_for_spot,
            "require_live_market_data_running_for_spot",
        )
        _require_bool(
            self.stop_live_option_runtime_on_shutdown,
            "stop_live_option_runtime_on_shutdown",
        )
        _require_bool(
            self.deactivate_option_subscriptions_on_shutdown,
            "deactivate_option_subscriptions_on_shutdown",
        )
