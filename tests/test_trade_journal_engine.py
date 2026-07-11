"""
Tests for Trade Journal Engine V1.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from math import inf, nan

import pytest

import engines.trade_journal as journal_exports
from core.event_bus import EventBus
from core.events import TRADE_RECORDED
from engines.ai_reasoning.enums import (
    AgreementSummary,
    AIMarketSummary,
    ConflictSummary,
    ReasoningConfidence,
    TradingSuitability,
)
from engines.ai_reasoning.models import AIReasoningState
from engines.market_context.enums import MarketBias, MarketPhase
from engines.risk.enums import RiskDecision, RiskRejectionReason, RiskReductionReason, RiskTier
from engines.risk.models import RiskDecisionState
from engines.strategy.enums import (
    BlockReason,
    EntryReference,
    SetupQuality,
    StopReference,
    StrategyDecision,
    TargetReference,
    TradeDirection,
)
from engines.strategy.models import StrategyDecisionState
from engines.trade_journal import (
    JournalFilter,
    TradeCompliance,
    TradeExitType,
    TradeJournalCalculator,
    TradeJournalEngine,
    TradeJournalSnapshot,
    TradeOutcome,
)


OPENED = datetime(2026, 7, 11, 9, 15)
CLOSED = datetime(2026, 7, 11, 9, 45)


class RecordingBus(EventBus):
    def __init__(self):
        super().__init__()
        self.events = []
        self.observations = []
        self.engine = None

    def publish(self, event_name, data=None):
        if self.engine is not None:
            self.observations.append((self.engine.record_count, self.engine.summary.total_trades, self.engine.latest_record))
        self.events.append((event_name, data))
        super().publish(event_name, data)


def strategy(
    symbol="NIFTY",
    timeframe="1m",
    direction=TradeDirection.BULLISH,
    decision=StrategyDecision.TRADE_ELIGIBLE,
    block_reason=BlockReason.NONE,
    market_bias=MarketBias.BULLISH,
    confidence=ReasoningConfidence.HIGH,
    suitability=TradingSuitability.SUITABLE,
):
    return StrategyDecisionState(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=OPENED,
        decision=decision,
        direction=direction,
        setup_quality=SetupQuality.HIGH,
        entry_reference=EntryReference.PRICE_ACTION_RETEST,
        stop_reference=StopReference.LATEST_SWING,
        target_reference=TargetReference.NEXT_STRUCTURE,
        block_reason=block_reason,
        market_bias=market_bias,
        market_phase=MarketPhase.TRENDING_UP,
        confidence=confidence,
        trading_suitability=suitability,
        rationale=("aligned context", "risk accepted"),
    )


def risk(
    symbol="NIFTY",
    timeframe="1m",
    direction=TradeDirection.BULLISH,
    decision=RiskDecision.APPROVED,
    rejection_reason=RiskRejectionReason.NONE,
    approved_quantity=10,
    entry_price=100.0,
    stop_price=95.0,
    target_price=110.0,
    estimated_risk_amount=50.0,
    estimated_reward_amount=100.0,
):
    return RiskDecisionState(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=OPENED,
        decision=decision,
        risk_tier=RiskTier.STANDARD,
        rejection_reason=rejection_reason,
        reduction_reason=RiskReductionReason.NONE,
        direction=direction,
        account_equity=100000.0,
        realized_pnl_today=0.0,
        daily_loss_limit_amount=2000.0,
        remaining_daily_loss_capacity=2000.0,
        applied_risk_percent=1.0,
        risk_budget=1000.0,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        stop_distance=5.0,
        target_distance=10.0,
        reward_risk_ratio=2.0,
        lot_size=10,
        requested_lots=1,
        maximum_permitted_lots=1,
        approved_lots=1,
        approved_quantity=approved_quantity,
        estimated_risk_amount=estimated_risk_amount,
        estimated_reward_amount=estimated_reward_amount,
        rationale=("risk approved",),
    )


def ai(
    symbol="NIFTY",
    timeframe="1m",
    market_summary=AIMarketSummary.BULLISH,
    confidence=ReasoningConfidence.HIGH,
    suitability=TradingSuitability.SUITABLE,
):
    return AIReasoningState(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=OPENED,
        market_summary=market_summary,
        confidence=confidence,
        agreement_summary=AgreementSummary.ALIGNED,
        conflict_summary=ConflictSummary.NONE,
        trading_suitability=suitability,
        missing_information=("none",),
        explanation="Context and strategy are aligned.",
    )


def snapshot(
    trade_id="trade-1",
    symbol="NIFTY",
    exchange="NSE",
    timeframe="1m",
    opened_at=OPENED,
    closed_at=CLOSED,
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
    strategy_state=None,
    risk_state=None,
    ai_state=None,
    entry_order_ids=("entry-1",),
    exit_order_ids=("exit-1",),
    exit_type=TradeExitType.TARGET,
):
    return TradeJournalSnapshot(
        trade_id=trade_id,
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        opened_at=opened_at,
        closed_at=closed_at,
        direction=direction,
        entry_quantity=entry_quantity,
        exit_quantity=exit_quantity,
        average_entry_price=average_entry_price,
        average_exit_price=average_exit_price,
        planned_stop_price=planned_stop_price,
        planned_target_price=planned_target_price,
        planned_risk_amount=planned_risk_amount,
        planned_reward_amount=planned_reward_amount,
        realized_gross_pnl=realized_gross_pnl,
        strategy=strategy_state or strategy(symbol=symbol.strip().upper(), timeframe=timeframe.strip(), direction=direction),
        risk=risk_state
        or risk(
            symbol=symbol.strip().upper(),
            timeframe=timeframe.strip(),
            direction=direction,
            approved_quantity=entry_quantity,
            entry_price=average_entry_price,
            stop_price=planned_stop_price,
            target_price=planned_target_price,
        ),
        ai_reasoning=ai_state or ai(symbol=symbol.strip().upper(), timeframe=timeframe.strip()),
        entry_order_ids=entry_order_ids,
        exit_order_ids=exit_order_ids,
        exit_type=exit_type,
    )


def journal():
    bus = RecordingBus()
    engine = TradeJournalEngine(bus)
    bus.engine = engine
    return engine, bus


def test_enums_models_exports_slots_frozen_and_snapshot_normalization():
    assert TradeOutcome.WIN.value == "win"
    assert TradeCompliance.NON_COMPLIANT.value == "non_compliant"
    assert TradeExitType.REVERSAL.value == "reversal"
    assert JournalFilter.WINNERS.value == "winners"
    assert journal_exports.__all__ == [
        "TradeJournalEngine",
        "TradeJournalCalculator",
        "TradeJournalSnapshot",
        "TradeJournalRecord",
        "TradeJournalSummary",
        "TradeOutcome",
        "TradeCompliance",
        "TradeExitType",
        "JournalFilter",
    ]
    snap = snapshot(trade_id=" trade-1 ", symbol=" nifty ", exchange=" nse ", timeframe=" 1m ", entry_order_ids=(" e1 ",), exit_order_ids=(" x1 ",))
    assert snap.trade_id == "trade-1"
    assert snap.symbol == "NIFTY"
    assert snap.exchange == "NSE"
    assert snap.timeframe == "1m"
    assert snap.entry_order_ids == ("e1",)
    with pytest.raises(FrozenInstanceError):
        snap.trade_id = "other"

    record = TradeJournalCalculator.create_record(snap)
    summary = TradeJournalCalculator.calculate_summary((record,))
    assert hasattr(snap, "__slots__")
    assert hasattr(record, "__slots__")
    assert hasattr(summary, "__slots__")
    with pytest.raises(FrozenInstanceError):
        record.trade_id = "other"
    with pytest.raises(FrozenInstanceError):
        summary.total_trades = 99


def test_constructor_initial_lifecycle_and_empty_summary():
    engine, _ = journal()
    assert engine.record_count == 0
    assert engine.latest_record is None
    assert engine.data is None
    assert engine.is_ready() is False
    assert engine.summary.total_trades == 0
    assert engine.summary.total_gross_pnl == 0.0
    assert engine.summary.win_rate is None
    assert engine.summary.average_holding_seconds is None


def test_validation_rejects_bad_identity_timestamp_direction_quantity_prices_and_orders_atomically():
    engine, bus = journal()
    cases = [
        lambda: engine.record(object()),
        lambda: engine.record(snapshot(trade_id="")),
        lambda: engine.record(snapshot(symbol="")),
        lambda: engine.record(snapshot(exchange="")),
        lambda: engine.record(snapshot(timeframe="")),
        lambda: engine.record(snapshot(opened_at="bad")),
        lambda: engine.record(snapshot(closed_at="bad")),
        lambda: engine.record(snapshot(opened_at=CLOSED, closed_at=OPENED)),
        lambda: engine.record(snapshot(opened_at=datetime(2026, 7, 11, 9, 15, tzinfo=timezone.utc), closed_at=CLOSED)),
        lambda: engine.record(snapshot(direction=TradeDirection.NONE)),
        lambda: engine.record(snapshot(entry_quantity=0)),
        lambda: engine.record(snapshot(entry_quantity=True)),
        lambda: engine.record(snapshot(exit_quantity=9)),
        lambda: engine.record(snapshot(average_entry_price=0.0)),
        lambda: engine.record(snapshot(average_exit_price=inf)),
        lambda: engine.record(snapshot(planned_stop_price=nan)),
        lambda: engine.record(snapshot(planned_target_price=0.0)),
        lambda: engine.record(snapshot(planned_risk_amount=0.0)),
        lambda: engine.record(snapshot(planned_reward_amount=-1.0)),
        lambda: engine.record(snapshot(realized_gross_pnl=nan)),
        lambda: engine.record(snapshot(entry_order_ids=())),
        lambda: engine.record(snapshot(exit_order_ids=())),
        lambda: engine.record(snapshot(entry_order_ids=("a", "a"))),
        lambda: engine.record(snapshot(entry_order_ids=("a",), exit_order_ids=("a",))),
    ]
    for case in cases:
        with pytest.raises((TypeError, ValueError)):
            case()
        assert engine.record_count == 0
        assert engine.data is None
        assert bus.events == []


def test_validation_rejects_wrong_or_unrelated_upstream_states():
    engine, _ = journal()
    invalids = [
        snapshot(strategy_state=object()),
        snapshot(risk_state=object()),
        snapshot(ai_state=object()),
        snapshot(strategy_state=strategy(symbol="BANKNIFTY")),
        snapshot(risk_state=risk(timeframe="5m")),
        snapshot(ai_state=ai(symbol="BANKNIFTY")),
        snapshot(strategy_state=strategy(direction=TradeDirection.BEARISH)),
        snapshot(risk_state=risk(direction=TradeDirection.BEARISH)),
        snapshot(strategy_state=strategy(decision=StrategyDecision.NO_TRADE, block_reason=BlockReason.LOW_CONFIDENCE)),
        snapshot(risk_state=risk(decision=RiskDecision.REJECTED, rejection_reason=RiskRejectionReason.INSUFFICIENT_RISK_BUDGET)),
        snapshot(risk_state=risk(approved_quantity=5)),
        snapshot(risk_state=risk(entry_price=101.0)),
        snapshot(strategy_state=strategy(market_bias=MarketBias.BEARISH)),
        snapshot(strategy_state=strategy(confidence=ReasoningConfidence.MEDIUM)),
        snapshot(strategy_state=strategy(suitability=TradingSuitability.WATCHLIST)),
        snapshot(ai_state=ai(market_summary=AIMarketSummary.NEUTRAL)),
    ]
    for invalid in invalids:
        with pytest.raises((TypeError, ValueError)):
            engine.record(invalid)
        assert engine.record_count == 0


def test_record_calculations_for_outcomes_r_multiple_fields_and_compliance():
    winner = TradeJournalCalculator.create_record(snapshot(realized_gross_pnl=50.0))
    loser = TradeJournalCalculator.create_record(snapshot(realized_gross_pnl=-50.0, average_exit_price=95.0, exit_type=TradeExitType.STOP))
    breakeven = TradeJournalCalculator.create_record(snapshot(realized_gross_pnl=0.0, average_exit_price=100.0, exit_type=TradeExitType.MANUAL))
    assert winner.outcome is TradeOutcome.WIN
    assert loser.outcome is TradeOutcome.LOSS
    assert breakeven.outcome is TradeOutcome.BREAKEVEN
    assert winner.holding_seconds == 1800
    assert winner.reward_risk_planned == 2.0
    assert winner.r_multiple == 1.0
    assert loser.r_multiple == -1.0
    assert breakeven.r_multiple == 0.0
    assert winner.strategy_decision is StrategyDecision.TRADE_ELIGIBLE
    assert winner.setup_quality is SetupQuality.HIGH
    assert winner.market_bias is MarketBias.BULLISH
    assert winner.market_phase is MarketPhase.TRENDING_UP
    assert winner.reasoning_confidence is ReasoningConfidence.HIGH
    assert winner.trading_suitability is TradingSuitability.SUITABLE
    assert winner.strategy_rationale == ("aligned context", "risk accepted")
    assert winner.ai_explanation == ("Context and strategy are aligned.",)
    assert winner.missing_information == ("none",)
    assert winner.entry_order_ids == ("entry-1",)
    assert winner.exit_order_ids == ("exit-1",)
    assert loser.exit_type is TradeExitType.STOP
    assert winner.compliance is TradeCompliance.COMPLIANT

    non_compliant = TradeJournalCalculator.create_record(snapshot(planned_risk_amount=60.0))
    assert non_compliant.compliance is TradeCompliance.NON_COMPLIANT
    assert non_compliant.r_multiple == 1.6667


def test_summary_calculations_mixed_records_rounding_and_empty_behavior():
    records = (
        TradeJournalCalculator.create_record(snapshot("win", realized_gross_pnl=100.125, planned_risk_amount=50.0, planned_reward_amount=99.999, closed_at=datetime(2026, 7, 11, 9, 45))),
        TradeJournalCalculator.create_record(snapshot("loss", average_exit_price=95.0, realized_gross_pnl=-50.0, closed_at=datetime(2026, 7, 11, 10, 15))),
        TradeJournalCalculator.create_record(snapshot("flat", average_exit_price=100.0, realized_gross_pnl=0.0, planned_risk_amount=60.0, closed_at=datetime(2026, 7, 11, 10, 45))),
    )
    summary = TradeJournalCalculator.calculate_summary(records)
    assert summary.total_trades == 3
    assert summary.winning_trades == 1
    assert summary.losing_trades == 1
    assert summary.breakeven_trades == 1
    assert summary.compliant_trades == 2
    assert summary.non_compliant_trades == 1
    assert summary.total_gross_pnl == 50.12
    assert summary.average_trade_pnl == 16.71
    assert summary.gross_profit == 100.12
    assert summary.gross_loss == 50.0
    assert summary.win_rate == 33.33
    assert summary.loss_rate == 33.33
    assert summary.average_win == 100.12
    assert summary.average_loss == -50.0
    assert summary.profit_factor == 2.0024
    assert summary.expectancy == 16.71
    assert summary.average_r_multiple == 0.3889
    assert summary.best_trade_pnl == 100.12
    assert summary.worst_trade_pnl == -50.0
    assert summary.average_holding_seconds == 3600.0

    no_loss = TradeJournalCalculator.calculate_summary((records[0],))
    assert no_loss.profit_factor is None
    assert TradeJournalCalculator.empty_summary() == TradeJournalCalculator.calculate_summary(())


def test_engine_records_after_storage_updates_summary_and_publish_order():
    engine, bus = journal()
    record = engine.record(snapshot())
    assert engine.record_count == 1
    assert engine.latest_record is record
    assert engine.data is record
    assert engine.summary.total_trades == 1
    assert engine.is_ready() is True
    assert bus.events == [(TRADE_RECORDED, record)]
    assert bus.observations == [(1, 1, record)]


def test_duplicates_stale_records_same_timestamp_and_process_alias_are_handled_atomically():
    engine, bus = journal()
    first_snapshot = snapshot()
    first = engine.process(first_snapshot)
    duplicate = engine.record(first_snapshot)
    assert duplicate is first
    assert len(bus.events) == 1

    with pytest.raises(ValueError):
        engine.record(snapshot(trade_id="trade-1", realized_gross_pnl=101.0))
    assert engine.record_count == 1
    assert engine.summary.total_trades == 1

    same_time = engine.record(snapshot(trade_id="trade-2", closed_at=CLOSED, entry_order_ids=("entry-2",), exit_order_ids=("exit-2",)))
    assert same_time.trade_id == "trade-2"
    with pytest.raises(ValueError):
        engine.record(snapshot(trade_id="old", closed_at=datetime(2026, 7, 11, 9, 30), entry_order_ids=("entry-3",), exit_order_ids=("exit-3",)))
    assert engine.record_count == 2


def test_retrieval_filters_and_order_preservation():
    engine, _ = journal()
    win = engine.record(snapshot("win", realized_gross_pnl=100.0, entry_order_ids=("e1",), exit_order_ids=("x1",)))
    loss = engine.record(snapshot("loss", average_exit_price=95.0, realized_gross_pnl=-50.0, entry_order_ids=("e2",), exit_order_ids=("x2",)))
    flat = engine.record(snapshot("flat", average_exit_price=100.0, realized_gross_pnl=0.0, planned_risk_amount=60.0, entry_order_ids=("e3",), exit_order_ids=("x3",)))
    assert engine.get_record(" win ") is win
    assert engine.get_record("missing") is None
    assert engine.get_record(123) is None
    assert engine.get_records() == (win, loss, flat)
    assert isinstance(engine.get_records(), tuple)
    assert engine.filter_records(JournalFilter.ALL) == (win, loss, flat)
    assert engine.filter_records(JournalFilter.WINNERS) == (win,)
    assert engine.filter_records(JournalFilter.LOSERS) == (loss,)
    assert engine.filter_records(JournalFilter.BREAKEVEN) == (flat,)
    assert engine.filter_records(JournalFilter.COMPLIANT) == (win, loss)
    assert engine.filter_records(JournalFilter.NON_COMPLIANT) == (flat,)
    with pytest.raises(TypeError):
        engine.filter_records("all")


def test_reset_clear_independent_instances_and_timestamp_mode_reset():
    engine, bus = journal()
    engine.record(snapshot())
    count = len(bus.events)
    engine.reset()
    assert engine.record_count == 0
    assert engine.latest_record is None
    assert engine.data is None
    assert engine.summary == TradeJournalCalculator.empty_summary()
    assert engine.is_ready() is False
    assert len(bus.events) == count

    reused = engine.record(snapshot(trade_id="trade-1", closed_at=datetime(2020, 1, 1, 9, 45), opened_at=datetime(2020, 1, 1, 9, 15)))
    assert reused.trade_id == "trade-1"
    engine.clear()
    aware = engine.record(snapshot(trade_id="aware", opened_at=datetime(2026, 7, 11, 9, 15, tzinfo=timezone.utc), closed_at=datetime(2026, 7, 11, 9, 45, tzinfo=timezone.utc)))
    assert aware.trade_id == "aware"

    other, _ = journal()
    other_record = other.record(snapshot(trade_id="other", symbol="BANKNIFTY", entry_order_ids=("be",), exit_order_ids=("bx",), strategy_state=strategy(symbol="BANKNIFTY"), risk_state=risk(symbol="BANKNIFTY"), ai_state=ai(symbol="BANKNIFTY")))
    assert other_record.symbol == "BANKNIFTY"
    assert engine.record_count == 1


def test_upstream_models_unchanged_and_no_persistence_network_dependency():
    snap = snapshot()
    strategy_before = snap.strategy
    risk_before = snap.risk
    ai_before = snap.ai_reasoning
    engine, _ = journal()
    engine.record(snap)
    assert snap.strategy is strategy_before
    assert snap.risk is risk_before
    assert snap.ai_reasoning is ai_before

    import inspect
    import engines.trade_journal.trade_journal_engine as journal_engine_module

    source = inspect.getsource(journal_engine_module).lower()
    forbidden = ("requests", "websocket", "kiteconnect", "socket", "open(", "pandas", "numpy", "csv", "json")
    assert all(token not in source for token in forbidden)
