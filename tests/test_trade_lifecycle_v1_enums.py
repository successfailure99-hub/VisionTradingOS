from application.trade_lifecycle_v1 import (
    TradeLifecycleBlockSource,
    TradeLifecycleChange,
    TradeLifecycleOutcome,
    TradeLifecycleStage,
    TradeLifecycleStatus,
)


def test_exact_enum_values_and_exports():
    assert TradeLifecycleStatus.CREATED.value == "created"
    assert TradeLifecycleStage.EXECUTION_ACKNOWLEDGED.value == "execution_acknowledged"
    assert TradeLifecycleOutcome.POSITION_ACTIVE.value == "position_active"
    assert TradeLifecycleChange.POSITION_CLOSED.value == "position_closed"
    assert TradeLifecycleBlockSource.RISK.value == "risk"
    assert len({item.value for item in TradeLifecycleStage}) == len(tuple(TradeLifecycleStage))
