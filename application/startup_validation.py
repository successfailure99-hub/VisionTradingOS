"""
Deterministic production startup validation.
"""

from dataclasses import dataclass

from application.models import RuntimeConfiguration
from application.release import (
    REQUIRED_BROKER_MODE,
    SUPPORTED_RUNTIME_INSTRUMENTS,
    SUPPORTED_SAFETY_MODES,
    VERSION,
)
from brokers.zerodha.enums import BrokerExecutionMode
from core.event_bus import EventBus


@dataclass(frozen=True, slots=True)
class StartupValidationResult:
    version: str
    instruments: tuple[str, ...]
    safety_mode: str
    broker_mode: str
    dependencies: tuple[str, ...]


def validate_startup(
    configuration: RuntimeConfiguration,
    *,
    broker_mode: BrokerExecutionMode = REQUIRED_BROKER_MODE,
    event_bus: EventBus | None = None,
) -> StartupValidationResult:
    if not isinstance(configuration, RuntimeConfiguration):
        raise TypeError("startup configuration must be a RuntimeConfiguration.")
    if not isinstance(broker_mode, BrokerExecutionMode):
        raise TypeError("startup broker_mode must be a BrokerExecutionMode.")
    if broker_mode is not REQUIRED_BROKER_MODE:
        raise ValueError("startup execution mode must be DRY_RUN.")
    if event_bus is not None and not isinstance(event_bus, EventBus):
        raise TypeError("startup event_bus must be an EventBus.")

    _validate_instruments(configuration)
    _validate_safety_mode(configuration)
    return StartupValidationResult(
        version=VERSION,
        instruments=tuple(instrument.value for instrument in configuration.instruments),
        safety_mode=configuration.safety_mode.value,
        broker_mode=broker_mode.value,
        dependencies=("EventBus", "ApplicationOrchestrator", "ApplicationLifecycleManager"),
    )


def _validate_instruments(configuration: RuntimeConfiguration) -> None:
    if not configuration.instruments:
        raise ValueError("startup instruments must be configured.")
    unsupported = tuple(
        instrument
        for instrument in configuration.instruments
        if instrument not in SUPPORTED_RUNTIME_INSTRUMENTS
    )
    if unsupported:
        names = ", ".join(getattr(instrument, "value", str(instrument)) for instrument in unsupported)
        raise ValueError(f"startup instruments are unsupported: {names}.")


def _validate_safety_mode(configuration: RuntimeConfiguration) -> None:
    if configuration.safety_mode not in SUPPORTED_SAFETY_MODES:
        raise ValueError("startup safety mode must be ANALYSIS_ONLY or DRY_RUN.")
