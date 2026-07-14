from application.trade_lifecycle_runtime_integration_v1 import (
    TradeLifecycleIntegrationChange,
    TradeLifecycleRoutingResult,
    TradeLifecycleRuntimeIntegrationStatus,
)


def test_trade_lifecycle_runtime_integration_status_values_are_stable():
    assert TradeLifecycleRuntimeIntegrationStatus.CREATED.value == "created"
    assert TradeLifecycleRuntimeIntegrationStatus.READY.value == "ready"
    assert TradeLifecycleRuntimeIntegrationStatus.RUNNING.value == "running"
    assert TradeLifecycleRuntimeIntegrationStatus.STOPPED.value == "stopped"
    assert TradeLifecycleRuntimeIntegrationStatus.ERROR.value == "error"
    assert TradeLifecycleRuntimeIntegrationStatus.CLEARED.value == "cleared"


def test_trade_lifecycle_routing_result_values_are_stable():
    assert TradeLifecycleRoutingResult.PROCESSED.value == "processed"
    assert TradeLifecycleRoutingResult.WAITING.value == "waiting"
    assert TradeLifecycleRoutingResult.BLOCKED.value == "blocked"
    assert TradeLifecycleRoutingResult.REJECTED.value == "rejected"
    assert TradeLifecycleRoutingResult.INSUFFICIENT_DATA.value == "insufficient_data"
    assert TradeLifecycleRoutingResult.POSITION_UPDATED.value == "position_updated"
    assert TradeLifecycleRoutingResult.DUPLICATE.value == "duplicate"
    assert TradeLifecycleRoutingResult.NOT_READY.value == "not_ready"


def test_trade_lifecycle_integration_change_values_are_stable():
    assert TradeLifecycleIntegrationChange.INITIAL.value == "initial"
    assert TradeLifecycleIntegrationChange.VALIDATED.value == "validated"
    assert TradeLifecycleIntegrationChange.STARTED.value == "started"
    assert TradeLifecycleIntegrationChange.STOPPED.value == "stopped"
    assert TradeLifecycleIntegrationChange.REQUEST_PROCESSED.value == "request_processed"
    assert TradeLifecycleIntegrationChange.POSITION_UPDATED.value == "position_updated"
    assert TradeLifecycleIntegrationChange.POSITION_CLOSED.value == "position_closed"
    assert TradeLifecycleIntegrationChange.BECAME_ERROR.value == "became_error"
    assert TradeLifecycleIntegrationChange.CLEARED.value == "cleared"
    assert TradeLifecycleIntegrationChange.UNCHANGED.value == "unchanged"
