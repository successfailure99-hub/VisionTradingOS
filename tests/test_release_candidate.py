"""
Production release-candidate validation tests.
"""

import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from application import ApplicationBootstrap, ExecutionSafetyMode, RuntimeConfiguration, RuntimeInstrument, VERSION, validate_startup
from application.enums import RuntimeStatus
from application.orchestrator import ApplicationOrchestrator
from application.release import REQUIRED_BROKER_MODE, SUPPORTED_RUNTIME_INSTRUMENTS, SUPPORTED_SAFETY_MODES
from brokers.zerodha.enums import BrokerExecutionMode
from core.event_bus import EventBus
from dashboard.application import DashboardApplication


def app():
    return QApplication.instance() or QApplication([])


def test_release_version_metadata_is_stable_and_exported():
    assert VERSION == "1.0.0"
    assert REQUIRED_BROKER_MODE is BrokerExecutionMode.DRY_RUN
    assert SUPPORTED_RUNTIME_INSTRUMENTS == (
        RuntimeInstrument.NIFTY,
        RuntimeInstrument.BANKNIFTY,
        RuntimeInstrument.SENSEX,
    )
    assert SUPPORTED_SAFETY_MODES == (
        ExecutionSafetyMode.ANALYSIS_ONLY,
        ExecutionSafetyMode.DRY_RUN,
    )


def test_startup_validation_accepts_supported_release_configuration():
    configuration = RuntimeConfiguration(
        instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX),
        safety_mode=ExecutionSafetyMode.ANALYSIS_ONLY,
    )
    result = validate_startup(configuration, broker_mode=BrokerExecutionMode.DRY_RUN, event_bus=EventBus())
    assert result.version == VERSION
    assert result.instruments == ("NIFTY", "BANKNIFTY", "SENSEX")
    assert result.safety_mode == "analysis_only"
    assert result.broker_mode == "dry_run"
    assert result.dependencies == ("EventBus", "ApplicationOrchestrator", "ApplicationLifecycleManager")
    with pytest.raises(FrozenInstanceError):
        result.version = "2.0.0"


def test_startup_validation_errors_are_deterministic():
    with pytest.raises(TypeError, match="startup configuration must be a RuntimeConfiguration\\."):
        validate_startup(object())
    with pytest.raises(TypeError, match="startup broker_mode must be a BrokerExecutionMode\\."):
        validate_startup(RuntimeConfiguration(), broker_mode=object())
    with pytest.raises(ValueError, match="startup execution mode must be DRY_RUN\\."):
        validate_startup(RuntimeConfiguration(), broker_mode=BrokerExecutionMode.CLIENT)
    with pytest.raises(TypeError, match="startup event_bus must be an EventBus\\."):
        validate_startup(RuntimeConfiguration(), event_bus=object())


def test_invalid_configuration_is_rejected_before_startup_composition():
    with pytest.raises(ValueError, match="RuntimeConfiguration instruments must be a non-empty tuple\\."):
        RuntimeConfiguration(instruments=())
    with pytest.raises(ValueError, match="RuntimeConfiguration supports only RuntimeInstrument values\\."):
        RuntimeConfiguration(instruments=("NIFTY",))
    with pytest.raises(ValueError, match="Application Orchestrator V1 supports only timeframe '1m'\\."):
        RuntimeConfiguration(timeframe="5m")
    with pytest.raises(ValueError, match="RuntimeConfiguration safety_mode must be an ExecutionSafetyMode\\."):
        RuntimeConfiguration(safety_mode="analysis_only")


def test_bootstrap_records_startup_validation_without_starting_or_recreating_runtime():
    bootstrap = ApplicationBootstrap(
        RuntimeConfiguration(instruments=(RuntimeInstrument.SENSEX, RuntimeInstrument.BANKNIFTY))
    )
    assert bootstrap.startup_validation is None
    manager = bootstrap.create_application()
    validation = bootstrap.startup_validation
    assert validation is not None
    assert validation.version == VERSION
    assert validation.instruments == ("SENSEX", "BANKNIFTY")
    assert manager.status is RuntimeStatus.CREATED
    assert manager is bootstrap.create_application()
    assert bootstrap.startup_validation is validation


def test_release_lifecycle_startup_shutdown_and_recovery_are_deterministic():
    manager = ApplicationBootstrap().create_application()
    manager.start()
    assert manager.status is RuntimeStatus.RUNNING
    first_started_at = manager.snapshot().last_started_at
    manager.stop()
    assert manager.status is RuntimeStatus.STOPPED
    stopped_snapshot = manager.snapshot()
    assert stopped_snapshot.stop_count == 1
    assert stopped_snapshot.last_error is None
    manager.restart()
    restarted = manager.snapshot()
    assert restarted.status is RuntimeStatus.RUNNING
    assert restarted.restart_count == 1
    assert restarted.start_count == 2
    assert restarted.last_started_at >= first_started_at
    manager.stop()


def test_release_dashboard_constructs_refreshes_and_shuts_down_without_live_runtime():
    app()
    manager = ApplicationBootstrap().create_application()
    dashboard = DashboardApplication(manager, argv=[])
    view = dashboard.main_window.refresh()
    assert view.runtime.safety_mode == "Analysis Only"
    assert view.runtime.broker_mode == "Dry Run"
    assert tuple(market.symbol for market in view.markets) == ("NIFTY",)
    dashboard.shutdown()
    assert manager.status is RuntimeStatus.CREATED


def test_orchestrator_rejects_non_dry_run_broker_execution_mode():
    class ClientBroker:
        mode = BrokerExecutionMode.CLIENT

    with pytest.raises(ValueError, match="Application Orchestrator V1 requires a DRY_RUN Zerodha adapter by default\\."):
        ApplicationOrchestrator(EventBus(), broker_adapter=ClientBroker())


def test_release_documentation_mentions_supported_modes_and_commands():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "Version: 1.0.0" in text
    assert "ANALYSIS_ONLY" in text
    assert "DRY_RUN" in text
    assert "NIFTY, BANKNIFTY, SENSEX" in text
    assert "python -m pytest -v" in text
