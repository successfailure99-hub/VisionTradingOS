import pytest

from application.bootstrap import ApplicationBootstrap
from application.trade_lifecycle_runtime_integration_v1 import (
    TradeLifecycleRuntimeIntegrationV1,
    TradeLifecycleRuntimeIntegrationV1Configuration,
    TradeLifecycleRuntimeIntegrationV1Factory,
)
from core.enums.instrument import Instrument
from tests.test_trade_lifecycle_v1_coordinator import coordinator


def test_factory_builds_registry_without_starting_or_processing_coordinators():
    lifecycle = ApplicationBootstrap().create_application()
    lifecycle.start()
    item = coordinator()
    integration = TradeLifecycleRuntimeIntegrationV1Factory().create(
        application_lifecycle=lifecycle,
        coordinators=(item,),
        configuration=TradeLifecycleRuntimeIntegrationV1Configuration(
            enabled_instruments=(Instrument.NIFTY,)
        ),
    )

    assert isinstance(integration, TradeLifecycleRuntimeIntegrationV1)
    assert integration.registry.get(Instrument.NIFTY) is item
    assert item.snapshot().running is False
    assert item.snapshot().processing_count == 0


def test_factory_rejects_invalid_lifecycle_and_duplicate_coordinators():
    item = coordinator()
    with pytest.raises(TypeError, match="application_lifecycle"):
        TradeLifecycleRuntimeIntegrationV1Factory().create(
            application_lifecycle=object(),
            coordinators=(item,),
        )

    lifecycle = ApplicationBootstrap().create_application()
    with pytest.raises(ValueError, match="already registered"):
        TradeLifecycleRuntimeIntegrationV1Factory().create(
            application_lifecycle=lifecycle,
            coordinators=(item, item),
        )
