"""
Tests for Application Orchestrator V1.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

import application as application_exports
from application import (
    ApplicationMode,
    ApplicationOrchestrator,
    OrchestratorAction,
    OrchestratorResult,
    OrchestratorStatus,
)
from brokers.zerodha.adapter import ZerodhaBrokerAdapter
from brokers.zerodha.enums import BrokerExecutionMode, BrokerResultStatus
from core.event_bus import EventBus
from engines.order_management.enums import OrderRejectionReason, OrderSide, OrderStatus, OrderType, ProductType
from engines.order_management.models import OrderSnapshot, OrderState
from engines.position.enums import PositionSide, PositionStatus, PositionUpdateType
from engines.position.models import PositionFill, PositionMark, PositionState
from engines.risk.models import RiskSnapshot
from engines.strategy.models import StrategySnapshot
from engines.trade_journal.models import TradeJournalSnapshot


TS = datetime(2026, 7, 12, 9, 15)


class StubEngine:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def process(self, value):
        self.calls.append(("process", value))
        return self.payload

    def create(self, value):
        self.calls.append(("create", value))
        return self.payload

    def process_fill(self, value):
        self.calls.append(("process_fill", value))
        return self.payload

    def process_mark(self, value):
        self.calls.append(("process_mark", value))
        return self.payload

    def record(self, value):
        self.calls.append(("record", value))
        return self.payload


class Context:
    symbol = "NIFTY"
    timeframe = "1m"
    timestamp = TS


class Reasoning:
    pass


class Snapshot:
    pass


def order_state():
    return OrderState(
        client_order_id="order-1",
        broker_order_id=None,
        symbol="NIFTY",
        exchange="NSE",
        timeframe="1m",
        created_at=TS,
        updated_at=TS,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        status=OrderStatus.PENDING_SUBMISSION,
        quantity=10,
        filled_quantity=0,
        remaining_quantity=10,
        average_fill_price=None,
        limit_price=None,
        trigger_price=None,
        risk_entry_price=100.0,
        risk_stop_price=95.0,
        risk_target_price=110.0,
        estimated_risk_amount=50.0,
        rejection_reason=OrderRejectionReason.NONE,
        rejection_message=None,
        version=1,
    )


def position_state():
    return PositionState(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="1m",
        side=PositionSide.LONG,
        status=PositionStatus.OPEN,
        opened_at=TS,
        updated_at=TS,
        closed_at=None,
        net_quantity=10,
        absolute_quantity=10,
        average_entry_price=100.0,
        mark_price=None,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        total_pnl=0.0,
        total_buy_quantity=10,
        total_sell_quantity=0,
        last_fill_execution_id="exec-1",
        last_fill_price=100.0,
        last_fill_quantity=10,
        last_update_type=PositionUpdateType.OPEN,
        version=1,
    )


def fill():
    return PositionFill(
        execution_id="exec-1",
        client_order_id="order-1",
        broker_order_id=None,
        symbol="NIFTY",
        exchange="NSE",
        timeframe="1m",
        timestamp=TS,
        side=OrderSide.BUY,
        quantity=10,
        price=100.0,
    )


def mark():
    return PositionMark("NIFTY", "NSE", "1m", TS, 101.0)


def test_exports_modes_result_immutability_and_default_analysis_only():
    assert ApplicationMode.ANALYSIS_ONLY.value == "analysis_only"
    assert ApplicationMode.DRY_RUN.value == "dry_run"
    assert OrchestratorStatus.BLOCKED.value == "blocked"
    assert OrchestratorAction.BROKER_DRY_RUN.value == "broker_dry_run"
    assert application_exports.__all__ == [
        "ApplicationOrchestrator",
        "ApplicationMode",
        "OrchestratorAction",
        "OrchestratorStatus",
        "OrchestratorResult",
    ]

    orchestrator = ApplicationOrchestrator(EventBus())
    assert orchestrator.mode is ApplicationMode.ANALYSIS_ONLY
    assert orchestrator.last_result is None
    assert orchestrator.history == ()
    result = OrchestratorResult(OrchestratorAction.RISK, OrchestratorStatus.SKIPPED, ApplicationMode.ANALYSIS_ONLY, None, "ok")
    with pytest.raises(FrozenInstanceError):
        result.message = "changed"


def test_invalid_mode_and_missing_dependencies_are_rejected():
    with pytest.raises(ValueError):
        ApplicationOrchestrator(EventBus(), mode="dry_run")

    orchestrator = ApplicationOrchestrator(EventBus())
    with pytest.raises(ValueError):
        orchestrator.process_market_context(Snapshot())
    with pytest.raises(ValueError):
        orchestrator.process_ai_reasoning(Context())
    with pytest.raises(ValueError):
        orchestrator.process_strategy(Context(), Reasoning())
    with pytest.raises(ValueError):
        orchestrator.process_risk(Snapshot())
    with pytest.raises(ValueError):
        orchestrator.create_order(Snapshot())
    with pytest.raises(ValueError):
        orchestrator.apply_position_fill(fill())
    with pytest.raises(ValueError):
        orchestrator.record_trade(Snapshot())


def test_analysis_pipeline_uses_public_process_methods_and_records_history():
    context = Context()
    reasoning = Reasoning()
    strategy_state = object()
    market_engine = StubEngine(context)
    ai_engine = StubEngine(reasoning)
    strategy_engine = StubEngine(strategy_state)
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        market_context_engine=market_engine,
        ai_reasoning_engine=ai_engine,
        strategy_engine=strategy_engine,
    )

    result = orchestrator.process_analysis(Snapshot())
    assert result.action is OrchestratorAction.STRATEGY
    assert result.status is OrchestratorStatus.COMPLETED
    assert result.payload is strategy_state
    assert market_engine.calls[0][0] == "process"
    assert ai_engine.calls == [("process", context)]
    strategy_call = strategy_engine.calls[0]
    assert strategy_call[0] == "process"
    assert isinstance(strategy_call[1], StrategySnapshot)
    assert strategy_call[1].market_context is context
    assert strategy_call[1].ai_reasoning is reasoning
    assert orchestrator.last_result is result
    assert tuple(item.action for item in orchestrator.history) == (
        OrchestratorAction.MARKET_CONTEXT,
        OrchestratorAction.AI_REASONING,
        OrchestratorAction.STRATEGY,
    )


def test_risk_order_position_and_journal_delegation_use_public_methods():
    risk_state = object()
    order = order_state()
    position = position_state()
    journal_record = object()
    risk_engine = StubEngine(risk_state)
    order_engine = StubEngine(order)
    position_engine = StubEngine(position)
    journal_engine = StubEngine(journal_record)
    orchestrator = ApplicationOrchestrator(
        EventBus(),
        risk_engine=risk_engine,
        order_engine=order_engine,
        position_engine=position_engine,
        trade_journal_engine=journal_engine,
    )

    assert orchestrator.process_risk(Snapshot()).payload is risk_state
    assert risk_engine.calls[0][0] == "process"
    assert orchestrator.create_order(Snapshot()).payload is order
    assert order_engine.calls[0][0] == "create"
    assert orchestrator.apply_position_fill(fill()).payload is position
    assert position_engine.calls[0][0] == "process_fill"
    assert orchestrator.apply_position_mark(mark()).payload is position
    assert position_engine.calls[1][0] == "process_mark"
    assert orchestrator.record_trade(Snapshot()).payload is journal_record
    assert journal_engine.calls[0][0] == "record"


def test_broker_submission_blocked_by_default_and_allowed_only_with_explicit_dry_run():
    order = order_state()
    analysis = ApplicationOrchestrator(EventBus(), broker_adapter=ZerodhaBrokerAdapter())
    blocked = analysis.submit_order_dry_run(order)
    assert blocked.status is OrchestratorStatus.BLOCKED
    assert blocked.payload is None
    assert blocked.mode is ApplicationMode.ANALYSIS_ONLY

    dry_run = ApplicationOrchestrator(
        EventBus(),
        mode=ApplicationMode.DRY_RUN,
        broker_adapter=ZerodhaBrokerAdapter(mode=BrokerExecutionMode.DRY_RUN),
    )
    result = dry_run.submit_order_dry_run(order)
    assert result.status is OrchestratorStatus.COMPLETED
    assert result.action is OrchestratorAction.BROKER_DRY_RUN
    assert result.payload.status is BrokerResultStatus.DRY_RUN
    assert result.payload.client_order_id == "order-1"


def test_non_dry_run_broker_adapter_is_rejected_for_submission():
    class Client:
        def place_order(self, **kwargs):
            return "broker-1"

    orchestrator = ApplicationOrchestrator(
        EventBus(),
        mode=ApplicationMode.DRY_RUN,
        broker_adapter=ZerodhaBrokerAdapter(client=Client(), mode=BrokerExecutionMode.CLIENT),
    )
    with pytest.raises(ValueError):
        orchestrator.submit_order_dry_run(order_state())


def test_reset_clear_history_and_no_private_engine_access_or_forbidden_capabilities():
    orchestrator = ApplicationOrchestrator(EventBus(), risk_engine=StubEngine("risk"))
    orchestrator.process_risk(Snapshot())
    assert len(orchestrator.history) == 1
    orchestrator.reset()
    assert orchestrator.history == ()
    assert orchestrator.last_result is None
    orchestrator.process_risk(Snapshot())
    orchestrator.clear()
    assert orchestrator.history == ()

    import inspect
    import application.application_orchestrator as module

    source = inspect.getsource(module)
    forbidden = (
        "_market_context_engine._",
        "_ai_reasoning_engine._",
        "_strategy_engine._",
        "_risk_engine._",
        "_order_engine._",
        "_position_engine._",
        "_trade_journal_engine._",
        "requests",
        "websocket",
        "kiteconnect",
        "open(",
        "threading",
        "asyncio",
        "login",
        "token",
    )
    assert all(token not in source.lower() for token in forbidden)
