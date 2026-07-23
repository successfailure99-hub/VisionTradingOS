"""
Application Orchestrator V1 package.

The package exports remain stable for callers that use ``from application import
...``. Heavy runtime objects are imported lazily so lower-level engine packages
can safely import ``application.enums`` without triggering full runtime wiring.
"""

from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from application.release import VERSION

__all__ = [
    "ApplicationOrchestrator",
    "SymbolRuntime",
    "RuntimeConfiguration",
    "RuntimeSnapshot",
    "OrchestratorSnapshot",
    "RuntimeInstrument",
    "RuntimeStatus",
    "ExecutionSafetyMode",
    "ApplicationBootstrap",
    "ApplicationLifecycleManager",
    "LifecycleSnapshot",
    "VERSION",
    "StartupValidationResult",
    "validate_startup",
]


def __getattr__(name: str):
    if name == "ApplicationBootstrap":
        from application.bootstrap import ApplicationBootstrap

        return ApplicationBootstrap
    if name == "ApplicationLifecycleManager":
        from application.lifecycle_manager import ApplicationLifecycleManager

        return ApplicationLifecycleManager
    if name == "LifecycleSnapshot":
        from application.lifecycle_manager import LifecycleSnapshot

        return LifecycleSnapshot
    if name == "ApplicationOrchestrator":
        from application.orchestrator import ApplicationOrchestrator

        return ApplicationOrchestrator
    if name == "SymbolRuntime":
        from application.symbol_runtime import SymbolRuntime

        return SymbolRuntime
    if name in {"RuntimeConfiguration", "RuntimeSnapshot", "OrchestratorSnapshot"}:
        from application.models import OrchestratorSnapshot, RuntimeConfiguration, RuntimeSnapshot

        return {
            "RuntimeConfiguration": RuntimeConfiguration,
            "RuntimeSnapshot": RuntimeSnapshot,
            "OrchestratorSnapshot": OrchestratorSnapshot,
        }[name]
    if name in {"StartupValidationResult", "validate_startup"}:
        from application.startup_validation import StartupValidationResult, validate_startup

        return {
            "StartupValidationResult": StartupValidationResult,
            "validate_startup": validate_startup,
        }[name]
    raise AttributeError(f"module 'application' has no attribute {name!r}")
