"""
Tests for Application Bootstrap V1.
"""

import pytest

from application import ApplicationBootstrap, ApplicationLifecycleManager, ExecutionSafetyMode, RuntimeConfiguration, RuntimeStatus
from application.bootstrap import create_application
from application.orchestrator import ApplicationOrchestrator
from brokers.zerodha.enums import BrokerExecutionMode
from core.event_bus import EventBus


def test_default_bootstrap_creates_valid_configuration():
    bootstrap = ApplicationBootstrap()
    assert isinstance(bootstrap.configuration, RuntimeConfiguration)
    assert bootstrap.configuration.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY


def test_create_application_composes_one_event_bus_and_orchestrator():
    captured = []

    def factory(event_bus, configuration):
        captured.append((event_bus, configuration))
        return ApplicationOrchestrator(event_bus, configuration)

    bootstrap = ApplicationBootstrap(orchestrator_factory=factory)
    manager = bootstrap.create_application()
    assert isinstance(manager, ApplicationLifecycleManager)
    assert len(captured) == 1
    assert isinstance(captured[0][0], EventBus)
    assert captured[0][1] is bootstrap.configuration
    assert manager.orchestrator.status is RuntimeStatus.CREATED


def test_create_application_does_not_start_application():
    manager = ApplicationBootstrap().create_application()
    assert manager.status is RuntimeStatus.CREATED
    assert manager.orchestrator.status is RuntimeStatus.CREATED


def test_repeated_create_application_returns_same_manager_and_orchestrator():
    bootstrap = ApplicationBootstrap()
    first = bootstrap.create_application()
    second = bootstrap.create_application()
    assert first is second
    assert first.orchestrator is second.orchestrator


def test_bootstrap_starts_existing_manager_without_duplication():
    bootstrap = ApplicationBootstrap()
    manager = bootstrap.create_application()
    orchestrator = manager.orchestrator
    started = bootstrap.bootstrap()
    assert started is manager
    assert started.status is RuntimeStatus.RUNNING
    assert started.orchestrator is orchestrator


def test_repeated_bootstrap_is_idempotent_for_application_instance():
    bootstrap = ApplicationBootstrap()
    first = bootstrap.bootstrap()
    second = bootstrap.bootstrap()
    assert first is second
    assert first.orchestrator is second.orchestrator
    assert first.snapshot().start_count == 1


def test_explicit_configuration_is_preserved():
    config = RuntimeConfiguration(exchange="nse", timeframe="1m")
    manager = ApplicationBootstrap(config).create_application()
    assert manager.orchestrator.configuration is config


def test_default_safety_and_broker_modes_are_preserved():
    manager = ApplicationBootstrap().create_application()
    assert manager.orchestrator.configuration.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert manager.orchestrator.broker_adapter.mode is BrokerExecutionMode.DRY_RUN


def test_module_level_create_application_returns_unstarted_manager():
    manager = create_application()
    assert isinstance(manager, ApplicationLifecycleManager)
    assert manager.status is RuntimeStatus.CREATED


def test_injected_event_bus_is_used_once():
    event_bus = EventBus()
    seen = []

    def factory(bus, configuration):
        seen.append(bus)
        return ApplicationOrchestrator(bus, configuration)

    bootstrap = ApplicationBootstrap(event_bus=event_bus, orchestrator_factory=factory)
    manager = bootstrap.create_application()
    assert seen == [event_bus]
    assert manager is bootstrap.create_application()
    assert len(seen) == 1


def test_invalid_configuration_dependency_is_rejected():
    with pytest.raises(TypeError):
        ApplicationBootstrap(configuration=object())


def test_invalid_event_bus_dependency_is_rejected():
    with pytest.raises(TypeError):
        ApplicationBootstrap(event_bus=object())


def test_invalid_orchestrator_factory_dependency_is_rejected():
    with pytest.raises(TypeError):
        ApplicationBootstrap(orchestrator_factory=object())


def test_invalid_orchestrator_factory_result_is_rejected():
    bootstrap = ApplicationBootstrap(orchestrator_factory=lambda event_bus, configuration: object())
    with pytest.raises(TypeError):
        bootstrap.create_application()
