"""
Tests for dashboard presenters.
"""

from datetime import date, datetime

from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from application.lifecycle_manager import LifecycleSnapshot
from application.models import OrchestratorSnapshot, RuntimeSnapshot
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.building_candle import BuildingCandle
from core.models.tick import Tick
from dashboard.presenters import (
    build_ai_view,
    build_dashboard_view,
    build_journal_view,
    build_market_view,
    build_position_view,
    build_runtime_view,
    build_strategy_view,
)
from engines.ai_reasoning.enums import AIMarketSummary, AgreementSummary, ConflictSummary, ReasoningConfidence, TradingSuitability
from engines.ai_reasoning.models import AIReasoningState
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context.enums import AgreementState, CPRPosition, CamarillaZone, ContextStrength, EvidenceDirection, MarketBias, MarketPhase, VWAPPosition
from engines.market_context.models import MarketContextState
from engines.order_management.enums import OrderRejectionReason, OrderSide, OrderStatus, OrderType, ProductType
from engines.order_management.models import OrderState
from engines.position.enums import PositionSide, PositionStatus, PositionUpdateType
from engines.position.models import PositionState
from engines.risk.enums import RiskDecision, RiskReductionReason, RiskRejectionReason, RiskTier
from engines.risk.models import RiskDecisionState
from engines.strategy.enums import BlockReason, EntryReference, SetupQuality, StopReference, StrategyDecision, TargetReference, TradeDirection
from engines.strategy.models import StrategyDecisionState
from engines.trade_journal.enums import TradeCompliance, TradeExitType, TradeOutcome
from engines.trade_journal.models import TradeJournalRecord
from engines.vwap.levels import VWAPLevels


TS = datetime(2026, 7, 12, 9, 15)


def empty_runtime(symbol=RuntimeInstrument.NIFTY):
    return RuntimeSnapshot(symbol, "1m", RuntimeStatus.CREATED, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None)


def full_runtime():
    tick = Tick(Instrument.NIFTY, Exchange.NSE, TS, 100.0, 10, 99.5, 100.5, 100)
    candle = BuildingCandle(Instrument.NIFTY, TimeFrame.ONE_MINUTE, TS, TS, 95.0, 101.0, 94.0, 100.0, 10)
    context = MarketContextState("NIFTY", "1m", TS, 100.0, 108.0, 94.0, MarketBias.BULLISH, MarketPhase.TRENDING_UP, AgreementState.ALIGNED, ContextStrength.STRONG, EvidenceDirection.BULLISH, EvidenceDirection.BULLISH, VWAPPosition.ABOVE, CPRPosition.ABOVE, False, CamarillaZone.H3_TO_H4, 5, 0, 0, 0, 5, (), ())
    ai = AIReasoningState("NIFTY", "1m", TS, AIMarketSummary.BULLISH, ReasoningConfidence.HIGH, AgreementSummary.ALIGNED, ConflictSummary.NONE, TradingSuitability.SUITABLE, (), "Bullish")
    strategy = StrategyDecisionState("NIFTY", "1m", TS, StrategyDecision.TRADE_ELIGIBLE, TradeDirection.BULLISH, SetupQuality.HIGH, EntryReference.PRICE_ACTION_RETEST, StopReference.LATEST_SWING, TargetReference.NEXT_STRUCTURE, BlockReason.NONE, MarketBias.BULLISH, MarketPhase.TRENDING_UP, ReasoningConfidence.HIGH, TradingSuitability.SUITABLE, ())
    risk = RiskDecisionState("NIFTY", "1m", TS, RiskDecision.APPROVED, RiskTier.STANDARD, RiskRejectionReason.NONE, RiskReductionReason.NONE, TradeDirection.BULLISH, 100000.0, 0.0, 5000.0, 5000.0, 2.0, 2000.0, 100.0, 95.0, 110.0, 5.0, 10.0, 2.0, 10, 1, 10, 1, 10, 50.0, 100.0, ())
    order = OrderState("order-1", None, "NIFTY", "NSE", "1m", TS, TS, OrderSide.BUY, OrderType.MARKET, ProductType.INTRADAY, OrderStatus.PENDING_SUBMISSION, 10, 0, 10, None, None, None, 100.0, 95.0, 110.0, 50.0, OrderRejectionReason.NONE, None, 1)
    position = PositionState("NIFTY", "NSE", "1m", PositionSide.LONG, PositionStatus.OPEN, TS, TS, None, 10, 10, 100.0, 101.0, 0.0, 10.0, 10.0, 10, 0, "fill-1", 100.0, 10, PositionUpdateType.OPEN, 1)
    journal = TradeJournalRecord("trade-1", "NIFTY", "NSE", "1m", TS, TS, 0, TradeDirection.BULLISH, TradeOutcome.WIN, TradeCompliance.COMPLIANT, TradeExitType.TARGET, 10, 10, 100.0, 110.0, 95.0, 110.0, 50.0, 100.0, 100.0, 2.0, 2.0, StrategyDecision.TRADE_ELIGIBLE, SetupQuality.HIGH, MarketBias.BULLISH, MarketPhase.TRENDING_UP, ReasoningConfidence.HIGH, TradingSuitability.SUITABLE, (), (), (), ("entry",), ("exit",))
    return RuntimeSnapshot(
        RuntimeInstrument.NIFTY, "1m", RuntimeStatus.RUNNING, tick, candle,
        VWAPLevels(Instrument.NIFTY, date(2026, 7, 12), TS, 100.25, 10, 1002.5),
        CPRLevels(date(2026, 7, 12), 105.0, 95.0, 100.0, 100.0, 98.0, 102.0, 4.0, 4.0),
        CamarillaLevels(date(2026, 7, 12), 105.0, 95.0, 100.0, 100.0, 101.0, 102.0, 103.0, 104.0, 99.0, 98.0, 97.0, 96.0),
        None, None, context, ai, strategy, risk, order, position, journal, TS,
    )


def lifecycle(*runtimes):
    orchestrator = OrchestratorSnapshot(RuntimeStatus.RUNNING, ExecutionSafetyMode.ANALYSIS_ONLY, BrokerExecutionMode.DRY_RUN, tuple(runtime.symbol for runtime in runtimes), True, False, runtimes)
    return LifecycleSnapshot(RuntimeStatus.RUNNING, 1, 0, 0, TS, None, None, orchestrator)


def test_empty_runtime_snapshot_produces_safe_values():
    market = build_market_view(empty_runtime())
    assert market.last_price is None
    assert market.market_bias == "-"
    assert build_ai_view(empty_runtime()).explanation == "-"


def test_tick_candle_vwap_cpr_camarilla_and_context_map_correctly():
    market = build_market_view(full_runtime())
    assert market.last_price == 100.0
    assert market.bid_price == 99.5
    assert market.latest_candle_open == 95.0
    assert market.vwap == 100.25
    assert market.cpr_pivot == 100.0
    assert market.camarilla_h6 == 104.0
    assert market.session_high == 108.0
    assert market.market_bias == "Bullish"


def test_ai_strategy_risk_order_position_and_journal_map_correctly():
    runtime = full_runtime()
    assert build_ai_view(runtime).market_summary == "Bullish"
    strategy = build_strategy_view(runtime)
    assert strategy.risk_decision == "Approved"
    assert strategy.approved_quantity == 10
    assert strategy.latest_order_status == "Pending Submission"
    position = build_position_view(runtime)
    assert position.has_position is True
    assert position.stop_price == 95.0
    journal = build_journal_view(runtime)
    assert journal.latest_trade_id == "trade-1"
    assert journal.latest_exit_type == "Target"


def test_runtime_order_is_preserved_and_sources_are_not_mutated():
    first = full_runtime()
    second = empty_runtime(RuntimeInstrument.BANKNIFTY)
    view = build_dashboard_view(lifecycle(first, second))
    assert tuple(market.symbol for market in view.markets) == ("NIFTY", "BANKNIFTY")
    assert first.latest_tick.last_price == 100.0


def test_runtime_view_maps_lifecycle_metadata():
    view = build_runtime_view(lifecycle(full_runtime()))
    assert view.application_status == "Running"
    assert view.configured_instruments == ("NIFTY",)
    assert view.market_data_ready is True
