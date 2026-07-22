"""
Tests for Application Orchestrator V1 runtime contracts.
"""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta

import pytest

from application import (
    ApplicationOrchestrator,
    ExecutionSafetyMode,
    RuntimeConfiguration,
    RuntimeInstrument,
    RuntimeSnapshot,
    RuntimeStatus,
)
from brokers.zerodha.enums import BrokerExecutionMode, BrokerResultStatus
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.events import CAMARILLA_UPDATED, CPR_UPDATED
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from engines.ai_reasoning.enums import (
    AIMarketSummary,
    AgreementSummary,
    ConflictSummary,
    ReasoningConfidence,
    TradingSuitability,
)
from engines.ai_reasoning.models import AIReasoningState
from engines.option_chain.enums import OptionType
from engines.option_chain.models import OptionChainSnapshot, OptionLeg, OptionStrike
from engines.camarilla.camarilla_engine import CamarillaEngine
from engines.cpr.cpr_engine import CPREngine
from engines.market_context.enums import (
    AgreementState,
    CPRPosition,
    CamarillaZone,
    ContextStrength,
    EvidenceDirection,
    MarketBias,
    MarketPhase,
    VWAPPosition,
)
from engines.market_context.models import MarketContextState
from engines.order_management.enums import OrderSide, OrderType, ProductType
from engines.order_management.models import OrderRequest
from engines.risk.enums import RiskDecision
from engines.risk.models import AccountRiskState, RiskPolicy, TradeRiskPlan
from engines.strategy.enums import (
    BlockReason,
    EntryReference,
    SetupQuality,
    StopReference,
    StrategyDecision,
    TargetReference,
    TradeDirection,
)
from engines.strategy.models import StrategyDecisionState, StrategySnapshot
from engines.trade_journal.enums import TradeExitType
from engines.trade_journal.models import TradeJournalSnapshot


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


def daily_ohlc(trading_date=date(2026, 7, 12)):
    return DailyOHLC(trading_date, 95.0, 105.0, 90.0, 100.0)

def option_snapshot(timestamp=TS):
    return OptionChainSnapshot(
        symbol="NIFTY",
        exchange="NSE",
        expiry_date=date(2026, 7, 30),
        timestamp=timestamp,
        underlying_price=101.0,
        strikes=(
            OptionStrike(100.0, OptionLeg(OptionType.CALL, 10.0, 1000, 25, 100), OptionLeg(OptionType.PUT, 9.0, 1200, 50, 120)),
            OptionStrike(101.0, OptionLeg(OptionType.CALL, 11.0, 1400, 30, 110), OptionLeg(OptionType.PUT, 8.0, 900, 10, 90)),
            OptionStrike(102.0, OptionLeg(OptionType.CALL, 12.0, 900, 10, 90), OptionLeg(OptionType.PUT, 7.0, 800, 5, 80)),
        ),
    )


def bullish_context(timestamp=TS):
    return MarketContextState(
        symbol="NIFTY",
        timeframe="1m",
        timestamp=timestamp,
        current_price=100.0,
        session_high=108.0,
        session_low=94.0,
        market_bias=MarketBias.BULLISH,
        market_phase=MarketPhase.TRENDING_UP,
        agreement=AgreementState.ALIGNED,
        context_strength=ContextStrength.STRONG,
        price_action_direction=EvidenceDirection.BULLISH,
        option_chain_direction=EvidenceDirection.BULLISH,
        vwap_position=VWAPPosition.ABOVE,
        cpr_position=CPRPosition.ABOVE,
        virgin_cpr=False,
        camarilla_zone=CamarillaZone.H3_TO_H4,
        bullish_evidence_count=5,
        bearish_evidence_count=0,
        neutral_evidence_count=0,
        mixed_evidence_count=0,
        available_source_count=5,
        evidence=(),
        missing_sources=(),
    )


def bullish_ai(timestamp=TS):
    return AIReasoningState(
        symbol="NIFTY",
        timeframe="1m",
        timestamp=timestamp,
        market_summary=AIMarketSummary.BULLISH,
        confidence=ReasoningConfidence.HIGH,
        agreement_summary=AgreementSummary.ALIGNED,
        conflict_summary=ConflictSummary.NONE,
        trading_suitability=TradingSuitability.SUITABLE,
        missing_information=(),
        explanation="Deterministic bullish context.",
    )


def eligible_strategy(timestamp=TS):
    return StrategyDecisionState(
        symbol="NIFTY",
        timeframe="1m",
        timestamp=timestamp,
        decision=StrategyDecision.TRADE_ELIGIBLE,
        direction=TradeDirection.BULLISH,
        setup_quality=SetupQuality.HIGH,
        entry_reference=EntryReference.PRICE_ACTION_RETEST,
        stop_reference=StopReference.LATEST_SWING,
        target_reference=TargetReference.NEXT_STRUCTURE,
        block_reason=BlockReason.NONE,
        market_bias=MarketBias.BULLISH,
        market_phase=MarketPhase.TRENDING_UP,
        confidence=ReasoningConfidence.HIGH,
        trading_suitability=TradingSuitability.SUITABLE,
        rationale=("eligible",),
    )


def policy():
    return RiskPolicy(
        max_risk_percent=2.0,
        reduced_risk_percent=1.0,
        max_daily_loss_percent=5.0,
        max_consecutive_losses=3,
        reduced_after_consecutive_losses=2,
        max_trades_per_day=5,
        reduced_after_trades=4,
        max_lots=10,
        minimum_reward_risk=1.5,
    )


def account():
    return AccountRiskState(
        account_equity=100000.0,
        realized_pnl_today=0.0,
        trades_today=0,
        consecutive_losses=0,
    )


def trade_plan():
    return TradeRiskPlan(
        entry_price=100.0,
        stop_price=95.0,
        target_price=110.0,
        lot_size=10,
        requested_lots=1,
    )


def order_request(timestamp=TS):
    return OrderRequest(
        client_order_id="order-1",
        symbol="NIFTY",
        exchange="NSE",
        timeframe="1m",
        timestamp=timestamp,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        quantity=10,
    )


def prepare_approved_risk(orchestrator):
    runtime = orchestrator.get_runtime("nifty")
    runtime.strategy_engine.process(StrategySnapshot("NIFTY", "1m", TS, bullish_ai(), bullish_context()))
    return orchestrator.run_risk(
        "NIFTY",
        policy=policy(),
        account=account(),
        trade_plan=trade_plan(),
    )


def test_cpr_and_camarilla_engines_are_owned_and_preserve_lifecycle():
    events = {CPR_UPDATED: [], CAMARILLA_UPDATED: []}
    bus = EventBus()
    bus.subscribe(CPR_UPDATED, events[CPR_UPDATED].append)
    bus.subscribe(CAMARILLA_UPDATED, events[CAMARILLA_UPDATED].append)
    orchestrator = ApplicationOrchestrator(bus)
    runtime = orchestrator.get_runtime("NIFTY")
    assert isinstance(runtime.cpr_engine, CPREngine)
    assert isinstance(runtime.camarilla_engine, CamarillaEngine)

    orchestrator.start()
    cpr, camarilla = orchestrator.process_daily_ohlc("NIFTY", daily_ohlc())
    assert runtime.cpr is cpr
    assert runtime.camarilla is camarilla
    assert runtime.cpr_engine.is_ready() is True
    assert runtime.camarilla_engine.is_ready() is True
    assert len(events[CPR_UPDATED]) == 1
    assert len(events[CAMARILLA_UPDATED]) == 1

    orchestrator.process_daily_ohlc("NIFTY", daily_ohlc())
    assert len(events[CPR_UPDATED]) == 1
    assert len(events[CAMARILLA_UPDATED]) == 1

    orchestrator.reset_symbol("NIFTY")
    assert runtime.cpr is None
    assert runtime.camarilla is None
    assert runtime.cpr_engine.is_ready() is False
    assert runtime.camarilla_engine.is_ready() is False


def test_configuration_preserves_primary_timeframe_backward_compatibility():
    config = RuntimeConfiguration(timeframe=" 1m ")
    orchestrator = ApplicationOrchestrator(EventBus(), config)
    runtime = orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    assert config.timeframe == "1m"
    assert runtime.candle_engine.timeframe.value == "1m"

    five_minute = RuntimeConfiguration(timeframe="5m")
    assert five_minute.timeframe == "5m"
    assert five_minute.timeframes == ("5m",)


def test_process_tick_returns_immutable_runtime_snapshot_with_dashboard_state():
    orchestrator = ApplicationOrchestrator(EventBus())
    orchestrator.start()
    snapshot = orchestrator.process_tick(tick(price=101.0))
    assert isinstance(snapshot, RuntimeSnapshot)
    assert snapshot.symbol is RuntimeInstrument.NIFTY
    assert snapshot.timeframe == "1m"
    assert snapshot.latest_tick.last_price == 101.0
    assert snapshot.latest_candle is not None
    assert snapshot.vwap is not None
    assert snapshot.updated_at == TS
    assert snapshot.cpr is None
    assert snapshot.market_context is not None
    assert snapshot.market_context.current_price == 101.0
    assert snapshot.market_context.session_high == 101.0
    assert snapshot.market_context.session_low == 101.0
    assert snapshot.ai_reasoning is not None
    assert snapshot.strategy is not None
    assert snapshot.risk is None
    assert snapshot.latest_order is None
    with pytest.raises(FrozenInstanceError):
        snapshot.updated_at = TS + timedelta(minutes=1)

    duplicate = orchestrator.process_tick(tick(price=101.0))
    assert isinstance(duplicate, RuntimeSnapshot)
    assert duplicate.latest_tick == snapshot.latest_tick
    assert duplicate.market_context == snapshot.market_context
    assert duplicate.ai_reasoning == snapshot.ai_reasoning
    assert duplicate.strategy == snapshot.strategy


def test_option_chain_update_refreshes_dashboard_analysis_after_spot_tick():
    orchestrator = ApplicationOrchestrator(EventBus(), RuntimeConfiguration(option_expiry_date=date(2026, 7, 30)))
    orchestrator.start()
    first = orchestrator.process_tick(tick(price=101.0))
    first_context = first.market_context

    state = orchestrator.process_option_chain("NIFTY", option_snapshot())
    snapshot = orchestrator.snapshot().runtime_snapshots[0]

    assert snapshot.option_chain == state
    assert snapshot.market_context is not None
    assert snapshot.market_context != first_context
    assert snapshot.market_context.option_chain_direction is not EvidenceDirection.UNKNOWN
    assert snapshot.ai_reasoning is not None
    assert snapshot.strategy is not None
    assert snapshot.latest_order is None

def test_build_market_context_uses_explicit_session_high_and_low():
    orchestrator = ApplicationOrchestrator(EventBus())
    orchestrator.start()
    orchestrator.process_tick(tick(price=100.0))
    context = orchestrator.build_market_context(
        "nifty",
        timestamp=TS,
        current_price=100.0,
        session_high=112.0,
        session_low=91.0,
    )
    assert context.current_price == 100.0
    assert context.session_high == 112.0
    assert context.session_low == 91.0
    snapshot = orchestrator.snapshot().runtime_snapshots[0]
    assert snapshot.market_context == context


def test_run_risk_constructs_snapshot_from_stored_strategy_state():
    orchestrator = ApplicationOrchestrator(EventBus())
    orchestrator.start()
    risk = prepare_approved_risk(orchestrator)
    assert risk.decision is RiskDecision.APPROVED
    assert risk.approved_quantity == 10
    assert orchestrator.get_runtime("NIFTY").snapshot().risk == risk


def test_create_order_constructs_snapshot_from_stored_risk_state():
    orchestrator = ApplicationOrchestrator(EventBus())
    orchestrator.start()
    prepare_approved_risk(orchestrator)
    order = orchestrator.create_order("NIFTY", order_request())
    assert order.client_order_id == "order-1"
    assert order.quantity == 10
    assert order.risk_entry_price == 100.0
    assert orchestrator.get_runtime("nifty").snapshot().latest_order == order


def test_reset_all_preserves_created_running_and_stopped_status():
    created = ApplicationOrchestrator(EventBus())
    assert created.reset_all().status is RuntimeStatus.CREATED
    assert all(runtime.status is RuntimeStatus.CREATED for runtime in created.runtimes)

    running = ApplicationOrchestrator(EventBus())
    running.start()
    running.process_tick(tick())
    assert running.reset_all().status is RuntimeStatus.RUNNING
    assert all(runtime.status is RuntimeStatus.RUNNING for runtime in running.runtimes)

    stopped = ApplicationOrchestrator(EventBus())
    stopped.start()
    stopped.stop()
    assert stopped.reset_all().status is RuntimeStatus.STOPPED
    assert all(runtime.status is RuntimeStatus.STOPPED for runtime in stopped.runtimes)


def test_string_and_enum_runtime_lookup_normalizes_and_rejects_invalid_values():
    orchestrator = ApplicationOrchestrator(EventBus())
    runtime = orchestrator.get_runtime(" nifty ")
    assert runtime is orchestrator.get_runtime(RuntimeInstrument.NIFTY)
    with pytest.raises(ValueError):
        orchestrator.get_runtime("FINNIFTY")
    with pytest.raises(ValueError):
        orchestrator.get_runtime(RuntimeInstrument.BANKNIFTY)


def test_record_trade_rejects_unsupported_symbol_and_snapshot_includes_latest_matching_record():
    orchestrator = ApplicationOrchestrator(EventBus())
    orchestrator.start()
    risk = prepare_approved_risk(orchestrator)
    strategy = orchestrator.get_runtime("NIFTY").strategy_engine.state
    ai = bullish_ai()
    snapshot = TradeJournalSnapshot(
        trade_id="trade-1",
        symbol="NIFTY",
        exchange="NSE",
        timeframe="1m",
        opened_at=TS,
        closed_at=TS + timedelta(minutes=5),
        direction=TradeDirection.BULLISH,
        entry_quantity=10,
        exit_quantity=10,
        average_entry_price=100.0,
        average_exit_price=110.0,
        planned_stop_price=95.0,
        planned_target_price=110.0,
        planned_risk_amount=50.0,
        planned_reward_amount=100.0,
        realized_gross_pnl=100.0,
        strategy=strategy,
        risk=risk,
        ai_reasoning=ai,
        entry_order_ids=("entry-1",),
        exit_order_ids=("exit-1",),
        exit_type=TradeExitType.TARGET,
    )
    record = orchestrator.record_trade(snapshot)
    assert orchestrator.snapshot().runtime_snapshots[0].latest_journal_record == record

    rejected = TradeJournalSnapshot(
        trade_id="trade-2",
        symbol="BANKNIFTY",
        exchange="NSE",
        timeframe="1m",
        opened_at=TS,
        closed_at=TS + timedelta(minutes=6),
        direction=TradeDirection.BULLISH,
        entry_quantity=10,
        exit_quantity=10,
        average_entry_price=100.0,
        average_exit_price=110.0,
        planned_stop_price=95.0,
        planned_target_price=110.0,
        planned_risk_amount=50.0,
        planned_reward_amount=100.0,
        realized_gross_pnl=100.0,
        strategy=strategy,
        risk=risk,
        ai_reasoning=ai,
        entry_order_ids=("entry-2",),
        exit_order_ids=("exit-2",),
        exit_type=TradeExitType.TARGET,
    )
    with pytest.raises(ValueError):
        orchestrator.record_trade(rejected)


def test_analysis_only_default_and_explicit_dry_run_submission_safety():
    analysis = ApplicationOrchestrator(EventBus())
    analysis.start()
    with pytest.raises(RuntimeError):
        analysis.submit_order(order_request())

    dry_run = ApplicationOrchestrator(
        EventBus(),
        RuntimeConfiguration(safety_mode=ExecutionSafetyMode.DRY_RUN),
    )
    dry_run.start()
    prepare_approved_risk(dry_run)
    order = dry_run.create_order("NIFTY", order_request())
    result = dry_run.submit_order(order)
    assert dry_run.broker_adapter.mode is BrokerExecutionMode.DRY_RUN
    assert result.status is BrokerResultStatus.DRY_RUN


def test_no_forbidden_live_execution_capabilities_or_private_engine_state_access():
    import ast
    import inspect

    import application.orchestrator as orchestrator_module
    import application.symbol_runtime as runtime_module

    source = inspect.getsource(orchestrator_module) + inspect.getsource(runtime_module)
    tree = ast.parse(source)

    forbidden_import_roots = {
        "requests",
        "websocket",
        "websockets",
        "kiteconnect",
    }
    forbidden_attribute_names = {
        "_state",
        "_data",
        "_orders",
        "access_token",
    }
    forbidden_function_names = {
        "login",
    }

    imported_roots = set()
    accessed_attributes = set()
    called_function_names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(
                alias.name.split(".", 1)[0]
                for alias in node.names
            )

        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

        elif isinstance(node, ast.Attribute):
            accessed_attributes.add(node.attr)

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_function_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_function_names.add(node.func.attr)

    assert imported_roots.isdisjoint(forbidden_import_roots)
    assert accessed_attributes.isdisjoint(forbidden_attribute_names)
    assert called_function_names.isdisjoint(forbidden_function_names)
