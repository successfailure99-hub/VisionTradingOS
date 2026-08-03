"""
Tests for dashboard presenters.
"""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from application.lifecycle_manager import LifecycleSnapshot
from application.models import (
    OrchestratorSnapshot,
    RuntimeDiagnostics,
    RuntimeSnapshot,
    RuntimeTradingSession,
    RuntimeVerificationStage,
)
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
    build_price_action_view,
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
from engines.price_action.enums import BreakDirection, LiquiditySweep, MarketStructure, PullbackState, RangeState, StructureType, SwingType, Trend
from engines.price_action.models import PriceActionState, SwingPoint
from engines.risk.enums import RiskDecision, RiskReductionReason, RiskRejectionReason, RiskTier
from engines.risk.models import RiskDecisionState
from engines.runtime_adapter import adapt_vision_method_to_trade_candidate
from engines.strategy.enums import BlockReason, EntryReference, SetupQuality, StopReference, StrategyDecision, TargetReference, TradeDirection
from engines.strategy.models import StrategyDecisionState
from engines.trade_journal.enums import TradeCompliance, TradeExitType, TradeOutcome
from engines.trade_journal.models import TradeJournalRecord
from engines.vision_method import VisionOptionConfirmation, validate_vision_method
from engines.vwap.levels import VWAPLevels
from tests.test_vision_method_validation_v1 import option as vision_option
from tests.test_vision_method_validation_v1 import snapshot as vision_method_snapshot


TS = datetime(2026, 7, 12, 9, 15)


def empty_runtime(symbol=RuntimeInstrument.NIFTY):
    return RuntimeSnapshot(symbol, "1m", RuntimeStatus.CREATED, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None)


def swing(swing_type, structure_type, price):
    return SwingPoint("NIFTY", "1m", swing_type, structure_type, price, TS, TS, 1)


def price_action_state():
    hh = swing(SwingType.HIGH, StructureType.HIGHER_HIGH, 111.0)
    hl = swing(SwingType.LOW, StructureType.HIGHER_LOW, 101.0)
    lh = swing(SwingType.HIGH, StructureType.LOWER_HIGH, 109.0)
    ll = swing(SwingType.LOW, StructureType.LOWER_LOW, 99.0)
    candle = BuildingCandle(Instrument.NIFTY, TimeFrame.ONE_MINUTE, TS, TS, 100.0, 112.0, 98.0, 110.0, 10)
    return PriceActionState(
        "NIFTY",
        "1m",
        5,
        candle,
        Trend.BULLISH,
        hh,
        hl,
        lh,
        ll,
        None,
        MarketStructure.BULLISH,
        hh,
        hl,
        lh,
        ll,
        hh,
        hl,
        BreakDirection.BULLISH,
        BreakDirection.NONE,
        PullbackState.BULLISH_PULLBACK,
        RangeState.NOT_RANGE,
        LiquiditySweep.BUY_SIDE,
        111.0,
        101.0,
        TS,
    )


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
        price_action_state(), None, context, ai, strategy, risk, order, position, journal, TS,
    )


def lifecycle(*runtimes):
    orchestrator = OrchestratorSnapshot(RuntimeStatus.RUNNING, ExecutionSafetyMode.ANALYSIS_ONLY, BrokerExecutionMode.DRY_RUN, tuple(runtime.symbol for runtime in runtimes), True, False, runtimes)
    return LifecycleSnapshot(RuntimeStatus.RUNNING, 1, 0, 0, TS, None, None, orchestrator)


def test_empty_runtime_snapshot_produces_safe_values():
    market = build_market_view(empty_runtime())
    assert market.last_price is None
    assert market.market_bias == "-"
    assert build_ai_view(empty_runtime()).explanation == "-"
    price_action = build_price_action_view(empty_runtime())
    assert price_action.available is False
    assert price_action.trend == "-"


def test_tick_candle_vwap_cpr_camarilla_and_context_map_correctly():
    market = build_market_view(full_runtime())
    assert market.last_price == 100.0
    assert market.bid_price == 99.5
    assert market.latest_candle_open == 95.0
    assert market.vwap == 100.25
    assert market.vwap_source == "NIFTY Spot"
    assert market.cpr_pivot == 100.0
    assert market.camarilla_h6 == 104.0
    assert market.session_high == 108.0
    assert market.market_bias == "Bullish"


def test_price_action_maps_complete_state():
    view = build_price_action_view(full_runtime())
    assert view.available is True
    assert view.symbol == "NIFTY"
    assert view.trend == "Bullish"
    assert view.market_structure == "Bullish"
    assert view.latest_hh == 111.0
    assert view.latest_hl == 101.0
    assert view.latest_lh == 109.0
    assert view.latest_ll == 99.0
    assert view.swing_high == 111.0
    assert view.swing_low == 101.0
    assert view.bos_direction == "Bullish"
    assert view.choch_direction == "None"
    assert view.pullback_state == "Bullish Pullback"
    assert view.range_state == "Not Range"
    assert view.liquidity_sweep == "Buy Side"
    assert view.updated_at is TS


def test_ai_strategy_risk_order_position_and_journal_map_correctly():
    runtime = full_runtime()
    assert build_ai_view(runtime).market_summary == "Bullish"
    assert build_ai_view(runtime).agreement == "LEGACY_DIAGNOSTIC"
    strategy = build_strategy_view(runtime)
    assert strategy.risk_decision == "Approved"
    assert strategy.approved_quantity == 10
    assert strategy.latest_order_status == "Pending Submission"
    position = build_position_view(runtime)
    assert position.status == "Active Position"
    assert position.has_position is True
    assert position.stop_price == 95.0
    journal = build_journal_view(runtime)
    assert journal.status == "Ready"
    assert journal.records == 1
    assert journal.latest_trade_id == "trade-1"
    assert journal.latest_exit_type == "Target"


def test_ai_and_strategy_views_reflect_canonical_vision_candidate_from_runtime_snapshot():
    method_snapshot = vision_method_snapshot(
        option_confirmation_context=vision_option(state=VisionOptionConfirmation.UNAVAILABLE)
    )
    validation = validate_vision_method(method_snapshot)
    candidate = adapt_vision_method_to_trade_candidate(method_snapshot, validation)
    runtime = replace(
        full_runtime(),
        vision_method_snapshot=method_snapshot,
        vision_method_validation_report=validation,
        vision_trade_candidate=candidate,
        strategy_decision_v2=None,
        ai_reasoning_v2=object(),
    )

    ai = build_ai_view(runtime)
    strategy = build_strategy_view(runtime)

    assert validation.candidate_state.value == "prepare_long"
    assert candidate.candidate_state.value == "waiting_long"
    assert ai.market_summary == "Vision Method: Waiting Long"
    assert ai.trading_suitability == "Waiting Long"
    assert ai.agreement == "Vision Method"
    assert strategy.candidate_state == "Waiting Long"
    assert strategy.candidate_direction == "Long"
    assert strategy.candidate_validation == "Partial"
    assert strategy.candidate_source == "VISION_METHOD"
    assert strategy.strategy_source == "LEGACY_DIAGNOSTIC"


def test_empty_position_and_journal_readiness_are_explicit():
    runtime = empty_runtime()
    position = build_position_view(runtime)
    assert position.status == "No Active Position"
    assert position.has_position is False
    journal = build_journal_view(runtime)
    assert journal.status == "Ready"
    assert journal.records == 0
    assert journal.message == "No completed DRY_RUN trades"


def test_mismatched_price_action_state_does_not_render_under_selected_instrument():
    runtime = RuntimeSnapshot(
        RuntimeInstrument.BANKNIFTY,
        "1m",
        RuntimeStatus.RUNNING,
        None,
        None,
        None,
        None,
        None,
        price_action_state(),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        TS,
    )
    view = build_price_action_view(runtime)
    assert view.symbol == "BANKNIFTY"
    assert view.available is False
    assert view.trend == "-"


def test_runtime_order_is_preserved_and_sources_are_not_mutated():
    first = full_runtime()
    second = empty_runtime(RuntimeInstrument.BANKNIFTY)
    view = build_dashboard_view(lifecycle(first, second))
    assert tuple(market.symbol for market in view.markets) == ("NIFTY", "BANKNIFTY")
    assert first.latest_tick.last_price == 100.0


def test_runtime_views_use_stable_professional_instrument_order():
    banknifty = empty_runtime(RuntimeInstrument.BANKNIFTY)
    sensex = empty_runtime(RuntimeInstrument.SENSEX)
    nifty = full_runtime()
    view = build_dashboard_view(lifecycle(sensex, banknifty, nifty))
    assert tuple(market.symbol for market in view.markets) == ("NIFTY", "BANKNIFTY", "SENSEX")
    assert tuple(price_action.symbol for price_action in view.price_actions) == ("NIFTY", "BANKNIFTY", "SENSEX")
    assert tuple(ai.symbol for ai in view.ai) == ("NIFTY", "BANKNIFTY", "SENSEX")
    assert tuple(strategy.symbol for strategy in view.strategies) == ("NIFTY", "BANKNIFTY", "SENSEX")


def test_runtime_view_maps_lifecycle_metadata():
    view = build_runtime_view(lifecycle(full_runtime()))
    assert view.application_status == "Running"
    assert view.configured_instruments == ("NIFTY",)
    assert view.market_data_ready is True


def test_runtime_view_exposes_deterministic_pipeline_health_from_snapshots():
    runtime = replace(
        full_runtime(),
        tradingview_evidence=object(),
        adr=object(),
        multi_timeframe_evidence=object(),
        market_state=object(),
        setup_classification=object(),
        chart_explanation=object(),
        ai_reasoning_v2=object(),
    )
    health = {item.name: item.status for item in build_runtime_view(lifecycle(runtime)).component_health}

    assert health["Candle"] == "Ready"
    assert health["Market Data"] == "Ready"
    assert health["TradingView Evidence"] == "Ready"
    assert health["ADR"] == "Ready"
    assert health["Fusion"] == "Ready"
    assert health["Market State"] == "Ready"
    assert health["Expert Setup"] == "Ready"
    assert health["Chart Explanation"] == "Ready"
    assert health["AI Reasoning"] == "Ready"
    assert health["Lifecycle"] == "Ready"


def test_runtime_view_exposes_vision_pipeline_health_and_reasons():
    runtime = replace(
        empty_runtime(),
        runtime_diagnostics=RuntimeDiagnostics(
            current_stage="WAITING_DAILY_CONTEXT",
            blocking_stage="DAILY_OHLC",
            current_candidate="INSUFFICIENT_DATA",
            paper_trade_state="NO_CANDIDATE",
            journal_state="NO_TRADE",
            last_successful_snapshot="-",
            last_validation="INSUFFICIENT_DATA",
        ),
    )
    rows = {item.name: item for item in build_runtime_view(lifecycle(runtime)).component_health}

    assert rows["NIFTY Vision Daily Context"].status == "WAITING"
    assert rows["NIFTY Vision Daily Context"].detail == "DAILY_OHLC"
    assert rows["NIFTY Vision Level Context"].detail == "DAILY_OHLC"
    assert rows["NIFTY Vision Opening Range"].detail == "DAILY_OHLC"
    assert rows["NIFTY Vision Structure"].detail == "DAILY_OHLC"
    assert rows["NIFTY Vision Liquidity"].detail == "DAILY_OHLC"
    assert rows["NIFTY Vision Structure Events"].detail == "DAILY_OHLC"
    assert rows["NIFTY Vision Setup Qualification"].detail == "DAILY_OHLC"
    assert rows["NIFTY Vision Option Confirmation"].detail == "DAILY_OHLC"
    assert rows["NIFTY Strategy Gate"].detail == "no actionable Vision candidate"
    assert rows["NIFTY Risk Gate"].detail == "no strategy decision"


def test_runtime_view_exposes_verification_report_ownership_details():
    session = RuntimeTradingSession(
        instrument=RuntimeInstrument.NIFTY,
        exchange="NSE",
        market_timestamp=TS,
        trading_date=TS.date(),
        previous_completed_trading_date=TS.date(),
        cpr_trading_date=TS.date(),
        camarilla_trading_date=TS.date(),
        adr_trading_date=None,
        vwap_trading_date=TS.date(),
        status="READY",
    )
    runtime = replace(
        empty_runtime(),
        runtime_session=session,
        runtime_verification_report=(
            RuntimeVerificationStage(
                stage="Daily Context",
                owner="SymbolRuntime",
                producer="CPR/Camarilla/ADR/VWAP",
                consumer="Vision Level Context",
                timestamp=TS,
                session=session,
                status="READY",
            ),
        ),
    )

    rows = {item.name: item for item in build_runtime_view(lifecycle(runtime)).component_health}

    assert rows["Vision Daily Context"].status == "READY"
    assert rows["Vision Daily Context"].owner == "SymbolRuntime"
    assert rows["Vision Daily Context"].producer == "CPR/Camarilla/ADR/VWAP"
    assert rows["Vision Daily Context"].consumer == "Vision Level Context"
    assert "Owner=SymbolRuntime" in rows["Vision Daily Context"].detail
    assert "Dependency=-" in rows["Vision Daily Context"].detail
    assert "Expected=-" in rows["Vision Daily Context"].detail
    assert "Actual=READY" in rows["Vision Daily Context"].detail
    assert "Session=2026-07-12" in rows["Vision Daily Context"].detail
    assert "Suggested Action=-" in rows["Vision Daily Context"].detail


def test_dashboard_package_has_no_market_context_v2_dependency():
    dashboard_root = Path(__file__).resolve().parents[1] / "dashboard"
    source = "\n".join(path.read_text(encoding="utf-8") for path in dashboard_root.rglob("*.py"))

    assert "MarketContextV2" not in source
    assert "market_context_v2" not in source
