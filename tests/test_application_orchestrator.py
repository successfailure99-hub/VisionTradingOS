"""
Tests for complete Application Orchestrator V1 runtime architecture.
"""

from dataclasses import FrozenInstanceError
from datetime import date, datetime

import pytest

import application as application_exports
from application import (
    ApplicationOrchestrator,
    ExecutionSafetyMode,
    OrchestratorSnapshot,
    RuntimeConfiguration,
    RuntimeInstrument,
    RuntimeSnapshot,
    RuntimeStatus,
    SymbolRuntime,
)
from brokers.zerodha.adapter import ZerodhaBrokerAdapter
from brokers.zerodha.enums import BrokerExecutionMode, BrokerResultStatus
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from engines.ai_reasoning.ai_reasoning_engine import AIReasoningEngine
from engines.camarilla.levels import CamarillaLevels
from engines.candle.candle_engine import CandleEngine
from engines.cpr.levels import CPRLevels
from engines.market_context.market_context_engine import MarketContextEngine
from engines.market_data.market_data_engine import MarketDataEngine
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.order_management.enums import OrderRejectionReason, OrderSide, OrderStatus, OrderType, ProductType
from engines.order_management.models import OrderState
from engines.order_management.order_management_engine import OrderManagementEngine
from engines.position.position_engine import PositionEngine
from engines.price_action.price_action_engine import PriceActionEngine
from engines.risk.risk_engine import RiskEngine
from engines.strategy.strategy_engine import StrategyEngine
from engines.trade_journal.trade_journal_engine import TradeJournalEngine
from engines.vwap.vwap_engine import VWAPEngine


TS = datetime(2026, 7, 12, 9, 15)


def tick(symbol=Instrument.NIFTY, timestamp=TS, price=100.0, volume=10):
    return Tick(
        symbol=symbol,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=volume,
        bid_price=price - 0.5,
        ask_price=price + 0.5,
        open_interest=100,
    )


def daily_ohlc():
    return DailyOHLC(date(2026, 7, 11), 95.0, 105.0, 90.0, 100.0)


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


def test_public_exports_and_configuration_contracts():
    assert application_exports.__all__ == [
        "ApplicationOrchestrator",
        "SymbolRuntime",
        "RuntimeConfiguration",
        "RuntimeSnapshot",
        "OrchestratorSnapshot",
        "RuntimeInstrument",
        "RuntimeStatus",
        "ExecutionSafetyMode",
    ]
    assert RuntimeInstrument.NIFTY.value == "NIFTY"
    assert RuntimeInstrument.BANKNIFTY.value == "BANKNIFTY"
    assert RuntimeInstrument.SENSEX.value == "SENSEX"
    assert RuntimeStatus.CREATED.value == "created"
    assert ExecutionSafetyMode.ANALYSIS_ONLY.value == "analysis_only"
    config = RuntimeConfiguration(
        instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY),
        exchange=" nse ",
        timeframe=" 1m ",
        option_expiry_date=date(2026, 7, 30),
    )
    assert config.exchange == "NSE"
    assert config.timeframe == "1m"
    with pytest.raises(FrozenInstanceError):
        config.exchange = "BSE"
    with pytest.raises(ValueError):
        RuntimeConfiguration(instruments=())
    with pytest.raises(ValueError):
        RuntimeConfiguration(instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.NIFTY))
    with pytest.raises(ValueError):
        RuntimeConfiguration(instruments=(Instrument.FINNIFTY,))


def test_orchestrator_owns_shared_services_and_one_runtime_per_configured_instrument():
    config = RuntimeConfiguration(
        instruments=(RuntimeInstrument.NIFTY, RuntimeInstrument.BANKNIFTY, RuntimeInstrument.SENSEX),
        option_expiry_date=date(2026, 7, 30),
    )
    orchestrator = ApplicationOrchestrator(EventBus(), config)
    assert orchestrator.status is RuntimeStatus.CREATED
    assert isinstance(orchestrator.market_data_engine, MarketDataEngine)
    assert isinstance(orchestrator.trade_journal_engine, TradeJournalEngine)
    assert orchestrator.broker_adapter.mode is BrokerExecutionMode.DRY_RUN
    assert len(orchestrator.runtimes) == 3
    assert tuple(runtime.instrument for runtime in orchestrator.runtimes) == config.instruments
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    assert isinstance(runtime, SymbolRuntime)
    assert isinstance(runtime.candle_engine, CandleEngine)
    assert isinstance(runtime.vwap_engine, VWAPEngine)
    assert isinstance(runtime.price_action_engine, PriceActionEngine)
    assert isinstance(runtime.option_chain_engine, OptionChainEngine)
    assert isinstance(runtime.market_context_engine, MarketContextEngine)
    assert isinstance(runtime.ai_reasoning_engine, AIReasoningEngine)
    assert isinstance(runtime.strategy_engine, StrategyEngine)
    assert isinstance(runtime.risk_engine, RiskEngine)
    assert isinstance(runtime.order_engine, OrderManagementEngine)
    assert isinstance(runtime.position_engine, PositionEngine)
    with pytest.raises(ValueError):
        orchestrator.get_runtime("NIFTY")


def test_start_stop_lifecycle_and_processing_blocked_unless_running():
    orchestrator = ApplicationOrchestrator(EventBus())
    with pytest.raises(RuntimeError):
        orchestrator.process_tick(tick())
    started = orchestrator.start()
    assert isinstance(started, OrchestratorSnapshot)
    assert orchestrator.status is RuntimeStatus.RUNNING
    assert all(snapshot.status is RuntimeStatus.RUNNING for snapshot in started.runtime_snapshots)
    stopped = orchestrator.stop()
    assert stopped.status is RuntimeStatus.STOPPED
    assert all(snapshot.status is RuntimeStatus.STOPPED for snapshot in stopped.runtime_snapshots)
    with pytest.raises(RuntimeError):
        orchestrator.process_tick(tick())


def test_process_tick_updates_shared_market_data_candle_vwap_and_runtime_snapshot():
    orchestrator = ApplicationOrchestrator(EventBus())
    orchestrator.start()
    result = orchestrator.process_tick(tick())
    runtime_result = result["runtime"]
    assert result["market_data"].symbol is Instrument.NIFTY
    assert runtime_result["candle"] is not None
    assert runtime_result["vwap"] is not None
    runtime_snapshot = orchestrator.snapshot().runtime_snapshots[0]
    assert runtime_snapshot.instrument is RuntimeInstrument.NIFTY
    assert runtime_snapshot.last_tick_timestamp == TS
    assert runtime_snapshot.latest_price == 100.0
    assert runtime_snapshot.candle_ready is True
    assert runtime_snapshot.vwap_ready is True
    duplicate = orchestrator.process_tick(tick())
    assert duplicate == {"market_data": None, "runtime": None}
    with pytest.raises(ValueError):
        orchestrator.process_tick(tick(symbol=Instrument.FINNIFTY))


def test_daily_ohlc_flow_builds_cpr_and_camarilla():
    orchestrator = ApplicationOrchestrator(EventBus())
    orchestrator.start()
    cpr, camarilla = orchestrator.process_daily_ohlc(RuntimeInstrument.NIFTY, daily_ohlc())
    assert isinstance(cpr, CPRLevels)
    assert isinstance(camarilla, CamarillaLevels)
    snapshot = orchestrator.get_runtime(RuntimeInstrument.NIFTY).snapshot()
    assert snapshot.cpr_ready is True
    assert snapshot.camarilla_ready is True


def test_market_context_ai_and_strategy_flow_uses_real_engines_when_context_is_sufficient():
    orchestrator = ApplicationOrchestrator(EventBus())
    orchestrator.start()
    orchestrator.process_tick(tick(price=100.0))
    context = orchestrator.build_market_context(RuntimeInstrument.NIFTY)
    assert context.symbol == "NIFTY"
    reasoning = orchestrator.run_ai_reasoning(RuntimeInstrument.NIFTY, context)
    assert reasoning.symbol == "NIFTY"
    strategy = orchestrator.run_strategy(RuntimeInstrument.NIFTY, context, reasoning)
    assert strategy.symbol == "NIFTY"
    runtime_snapshot = orchestrator.get_runtime(RuntimeInstrument.NIFTY).snapshot()
    assert runtime_snapshot.market_context_ready is True
    assert runtime_snapshot.ai_reasoning_ready is True
    assert runtime_snapshot.strategy_ready is True


def test_order_submission_safety_modes_and_explicit_dry_run():
    analysis = ApplicationOrchestrator(EventBus())
    analysis.start()
    with pytest.raises(RuntimeError):
        analysis.submit_order(order_state())

    dry_run = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(safety_mode=ExecutionSafetyMode.DRY_RUN),
    )
    dry_run.start()
    result = dry_run.submit_order(order_state())
    assert result.status is BrokerResultStatus.DRY_RUN
    assert result.client_order_id == "order-1"

    class Client:
        def place_order(self, **kwargs):
            return "broker-1"

    with pytest.raises(ValueError):
        ApplicationOrchestrator(
            EventBus(),
            RuntimeConfiguration(safety_mode=ExecutionSafetyMode.DRY_RUN),
            broker_adapter=ZerodhaBrokerAdapter(client=Client(), mode=BrokerExecutionMode.CLIENT),
        )


def test_runtime_snapshots_are_immutable_and_dashboard_facing():
    orchestrator = ApplicationOrchestrator(EventBus())
    snapshot = orchestrator.snapshot()
    assert isinstance(snapshot, OrchestratorSnapshot)
    assert snapshot.status is RuntimeStatus.CREATED
    assert snapshot.safety_mode is ExecutionSafetyMode.ANALYSIS_ONLY
    assert snapshot.broker_mode is BrokerExecutionMode.DRY_RUN
    assert snapshot.configured_instruments == (RuntimeInstrument.NIFTY,)
    assert snapshot.shared_market_data_ready is False
    assert snapshot.shared_trade_journal_ready is False
    assert isinstance(snapshot.runtime_snapshots[0], RuntimeSnapshot)
    with pytest.raises(FrozenInstanceError):
        snapshot.status = RuntimeStatus.RUNNING
    with pytest.raises(FrozenInstanceError):
        snapshot.runtime_snapshots[0].latest_price = 1.0


def test_reset_symbol_and_reset_all_clear_runtime_state_without_private_access():
    orchestrator = ApplicationOrchestrator(EventBus())
    orchestrator.start()
    orchestrator.process_tick(tick())
    assert orchestrator.snapshot().shared_market_data_ready is True
    reset_symbol_snapshot = orchestrator.reset_symbol(RuntimeInstrument.NIFTY)
    assert reset_symbol_snapshot.status is RuntimeStatus.RUNNING
    assert reset_symbol_snapshot.candle_ready is False
    assert orchestrator.status is RuntimeStatus.RUNNING
    all_snapshot = orchestrator.reset_all()
    assert all_snapshot.status is RuntimeStatus.CREATED
    assert all_snapshot.shared_market_data_ready is False
    assert all_snapshot.shared_trade_journal_ready is False
    assert all(runtime.status is RuntimeStatus.CREATED for runtime in orchestrator.runtimes)


def test_required_public_methods_exist_and_no_forbidden_capabilities_or_private_engine_access():
    orchestrator = ApplicationOrchestrator(EventBus())
    for name in (
        "start",
        "stop",
        "process_tick",
        "process_daily_ohlc",
        "process_option_chain",
        "build_market_context",
        "run_ai_reasoning",
        "run_strategy",
        "run_risk",
        "create_order",
        "submit_order",
        "apply_order_command",
        "apply_position_fill",
        "apply_position_mark",
        "record_trade",
        "reset_symbol",
        "reset_all",
    ):
        assert hasattr(orchestrator, name)

    import inspect
    import application.orchestrator as orchestrator_module
    import application.symbol_runtime as runtime_module

    source = (inspect.getsource(orchestrator_module) + inspect.getsource(runtime_module)).lower()
    forbidden = (
        "requests",
        "websocket",
        "kiteconnect",
        "open(",
        "threading",
        "asyncio",
        "login",
        "access_token",
        "._state",
        "._data",
        "._orders",
    )
    assert all(token not in source for token in forbidden)
