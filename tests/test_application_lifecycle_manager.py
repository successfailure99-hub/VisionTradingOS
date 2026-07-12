"""
Tests for Application Lifecycle Manager V1.
"""

from dataclasses import FrozenInstanceError

import pytest

from application import ApplicationLifecycleManager, LifecycleSnapshot, RuntimeStatus
from application.orchestrator import ApplicationOrchestrator
from core.event_bus import EventBus


def orchestrator():
    return ApplicationOrchestrator(EventBus())


def manager():
    return ApplicationLifecycleManager(orchestrator())


def runtime_ids(lifecycle):
    return tuple(id(runtime) for runtime in lifecycle.orchestrator.runtimes)


def test_constructor_rejects_non_orchestrator():
    with pytest.raises(TypeError):
        ApplicationLifecycleManager(object())


def test_initial_state_is_created():
    lifecycle = manager()
    snapshot = lifecycle.snapshot()
    assert snapshot.status is RuntimeStatus.CREATED
    assert lifecycle.status is RuntimeStatus.CREATED
    assert snapshot.start_count == 0
    assert snapshot.stop_count == 0
    assert snapshot.restart_count == 0


def test_start_transitions_to_running():
    lifecycle = manager()
    snapshot = lifecycle.start()
    assert snapshot.status is RuntimeStatus.RUNNING
    assert lifecycle.orchestrator.status is RuntimeStatus.RUNNING
    assert snapshot.start_count == 1
    assert snapshot.last_started_at.tzinfo is not None


def test_double_start_is_idempotent():
    lifecycle = manager()
    first = lifecycle.start()
    second = lifecycle.start()
    assert second.status is RuntimeStatus.RUNNING
    assert second.start_count == first.start_count == 1
    assert second.last_started_at == first.last_started_at


def test_stop_transitions_to_stopped():
    lifecycle = manager()
    lifecycle.start()
    snapshot = lifecycle.stop()
    assert snapshot.status is RuntimeStatus.STOPPED
    assert lifecycle.orchestrator.status is RuntimeStatus.STOPPED
    assert snapshot.stop_count == 1
    assert snapshot.last_stopped_at.tzinfo is not None


def test_stop_from_created_is_clean_without_stop_counter_increment():
    lifecycle = manager()
    snapshot = lifecycle.stop()
    assert snapshot.status is RuntimeStatus.STOPPED
    assert snapshot.stop_count == 0
    assert snapshot.start_count == 0


def test_double_stop_is_idempotent():
    lifecycle = manager()
    lifecycle.start()
    first = lifecycle.stop()
    second = lifecycle.stop()
    assert second.status is RuntimeStatus.STOPPED
    assert second.stop_count == first.stop_count == 1
    assert second.last_stopped_at == first.last_stopped_at


def test_start_after_stop_reuses_same_orchestrator():
    lifecycle = manager()
    original = lifecycle.orchestrator
    lifecycle.start()
    lifecycle.stop()
    lifecycle.start()
    assert lifecycle.orchestrator is original
    assert lifecycle.status is RuntimeStatus.RUNNING
    assert lifecycle.snapshot().start_count == 2


def test_restart_from_running_ends_running_and_reuses_orchestrator():
    lifecycle = manager()
    lifecycle.start()
    original = lifecycle.orchestrator
    original_runtimes = runtime_ids(lifecycle)
    snapshot = lifecycle.restart()
    assert snapshot.status is RuntimeStatus.RUNNING
    assert snapshot.restart_count == 1
    assert lifecycle.orchestrator is original
    assert runtime_ids(lifecycle) == original_runtimes


def test_restart_from_created_starts_and_counts_one_restart():
    lifecycle = manager()
    snapshot = lifecycle.restart()
    assert snapshot.status is RuntimeStatus.RUNNING
    assert snapshot.restart_count == 1
    assert snapshot.start_count == 1
    assert snapshot.stop_count == 0


def test_restart_from_stopped_starts_and_counts_one_restart():
    lifecycle = manager()
    lifecycle.stop()
    snapshot = lifecycle.restart()
    assert snapshot.status is RuntimeStatus.RUNNING
    assert snapshot.restart_count == 1
    assert snapshot.start_count == 1
    assert snapshot.stop_count == 0


def test_reset_preserves_created():
    lifecycle = manager()
    assert lifecycle.reset().status is RuntimeStatus.CREATED


def test_reset_preserves_running():
    lifecycle = manager()
    lifecycle.start()
    assert lifecycle.reset().status is RuntimeStatus.RUNNING
    assert lifecycle.orchestrator.status is RuntimeStatus.RUNNING


def test_reset_preserves_stopped():
    lifecycle = manager()
    lifecycle.stop()
    assert lifecycle.reset().status is RuntimeStatus.STOPPED
    assert lifecycle.orchestrator.status is RuntimeStatus.STOPPED


def test_reset_does_not_reset_counters():
    lifecycle = manager()
    lifecycle.start()
    lifecycle.stop()
    snapshot = lifecycle.reset()
    assert snapshot.start_count == 1
    assert snapshot.stop_count == 1
    assert snapshot.restart_count == 0


def test_lifecycle_snapshot_is_immutable():
    snapshot = manager().snapshot()
    assert isinstance(snapshot, LifecycleSnapshot)
    with pytest.raises(FrozenInstanceError):
        snapshot.status = RuntimeStatus.RUNNING


def test_snapshot_includes_orchestrator_snapshot():
    snapshot = manager().snapshot()
    assert snapshot.orchestrator_snapshot.status is RuntimeStatus.CREATED
    assert snapshot.orchestrator_snapshot.configured_instruments


def test_status_helpers_are_correct():
    lifecycle = manager()
    assert lifecycle.is_started() is False
    assert lifecycle.is_running() is False
    assert lifecycle.is_stopped() is False
    lifecycle.start()
    assert lifecycle.is_started() is True
    assert lifecycle.is_running() is True
    assert lifecycle.is_stopped() is False
    lifecycle.stop()
    assert lifecycle.is_started() is True
    assert lifecycle.is_running() is False
    assert lifecycle.is_stopped() is True


class FailingStartOrchestrator(ApplicationOrchestrator):
    def __init__(self):
        super().__init__(EventBus())
        self.cleanup_attempted = False

    def start(self):
        raise RuntimeError("start failed")

    def stop(self):
        self.cleanup_attempted = True
        return super().stop()


def test_startup_failure_moves_to_error_and_attempts_cleanup():
    orchestrator = FailingStartOrchestrator()
    lifecycle = ApplicationLifecycleManager(orchestrator)
    with pytest.raises(RuntimeError, match="start failed"):
        lifecycle.start()
    assert lifecycle.status is RuntimeStatus.ERROR
    assert orchestrator.cleanup_attempted is True
    assert "start failed" in lifecycle.snapshot().last_error


class FailingStartAndCleanupOrchestrator(ApplicationOrchestrator):
    def __init__(self):
        super().__init__(EventBus())

    def start(self):
        raise RuntimeError("start failed")

    def stop(self):
        raise RuntimeError("cleanup failed")


def test_startup_failure_records_cleanup_failure_without_replacing_original():
    lifecycle = ApplicationLifecycleManager(FailingStartAndCleanupOrchestrator())
    with pytest.raises(RuntimeError, match="start failed"):
        lifecycle.start()
    assert lifecycle.status is RuntimeStatus.ERROR
    assert "start failed" in lifecycle.snapshot().last_error
    assert "cleanup failed" in lifecycle.snapshot().last_error


class FailingStopOrchestrator(ApplicationOrchestrator):
    def __init__(self):
        super().__init__(EventBus())

    def stop(self):
        raise RuntimeError("stop failed")


def test_stop_failure_moves_to_error_and_reraises_original():
    lifecycle = ApplicationLifecycleManager(FailingStopOrchestrator())
    lifecycle.start()
    with pytest.raises(RuntimeError, match="stop failed"):
        lifecycle.stop()
    assert lifecycle.status is RuntimeStatus.ERROR
    assert "stop failed" in lifecycle.snapshot().last_error


def test_no_duplicate_runtime_objects_are_created_by_lifecycle_transitions():
    lifecycle = manager()
    original = runtime_ids(lifecycle)
    lifecycle.start()
    lifecycle.stop()
    lifecycle.start()
    lifecycle.restart()
    lifecycle.reset()
    assert runtime_ids(lifecycle) == original
