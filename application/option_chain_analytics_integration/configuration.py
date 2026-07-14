"""
Configuration for option-chain analytics runtime integration.
"""

from dataclasses import dataclass


def _require_bool(value: bool, field_name: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")
    return value


@dataclass(frozen=True, slots=True)
class OptionChainAnalyticsIntegrationConfiguration:
    require_application_running: bool = True
    require_live_option_integration_running: bool = True
    process_only_ready_live_snapshots: bool = True
    reset_analytics_on_clear: bool = True

    def __post_init__(self) -> None:
        _require_bool(self.require_application_running, "require_application_running")
        _require_bool(
            self.require_live_option_integration_running,
            "require_live_option_integration_running",
        )
        _require_bool(
            self.process_only_ready_live_snapshots,
            "process_only_ready_live_snapshots",
        )
        _require_bool(self.reset_analytics_on_clear, "reset_analytics_on_clear")
