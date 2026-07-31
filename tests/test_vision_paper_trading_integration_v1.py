from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from core.models.daily_ohlc import DailyOHLC
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.event_bus import EventBus
from core.models.tick import Tick
from dashboard.presenters import build_journal_view
from engines.risk_management_v2 import AccountRiskState, InstrumentExposureState, RiskManagementV2Input, SessionRiskState
from engines.risk_management_v2.enums import RiskDecision
from engines.runtime_adapter import TradeCandidateDirection, TradeCandidateState
from engines.strategy_decision_v2.enums import StrategyAction, StrategyDirection
from engines.trade_journal_v1.enums import TradeRecordStatus
from engines.vision_method import VisionCandidateState, validate_vision_method
from tests.test_vision_method_validation_v1 import NOW, option, setup, snapshot


def tick(price=100.0, *, timestamp=NOW):
    return Tick(
        symbol=Instrument.NIFTY,
        exchange=Exchange.NSE,
        timestamp=timestamp,
        last_price=price,
        volume=100,
        bid_price=price - 0.1,
        ask_price=price + 0.1,
        open_interest=0,
    )


def runtime():
    item = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    item.start()
    item._last_tick = tick()
    return item


def process(item, method_snapshot):
    report = validate_vision_method(method_snapshot)
    return item.process_vision_method_paper_trade(method_snapshot, report), report


def test_long_candidate_reaches_existing_risk_lifecycle_and_paper_tick():
    item = runtime()
    paper_calls = []
    original_on_tick = item.paper_trading_engine.on_tick

    def paper_spy(live_tick, *, strategy=None, risk=None):
        paper_calls.append((strategy, risk))
        return original_on_tick(live_tick, strategy=strategy, risk=risk)

    item.paper_trading_engine.on_tick = paper_spy

    candidate, _ = process(item, snapshot())
    lifecycle_timestamp = item.trade_lifecycle_v1.snapshot().timestamp
    item._process_paper_tick(tick(101.0, timestamp=lifecycle_timestamp + timedelta(seconds=1)))

    view = item.snapshot()
    assert candidate.candidate_state is TradeCandidateState.LONG
    assert candidate.direction is TradeCandidateDirection.LONG
    assert view.vision_trade_candidate is candidate
    assert view.ai_reasoning_v2 is None
    assert view.vision_ai_explanation.startswith("Vision Method produced a long candidate")
    assert view.strategy_decision_v2.action is StrategyAction.CONSIDER_LONG
    assert view.strategy_decision_v2.ai_reasoning is None
    assert view.strategy_decision_v2.trade_source == "VISION_METHOD"
    assert view.risk_management_v2.decision in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED}
    assert view.trade_lifecycle_v1.position_snapshot.has_open_position is True
    assert view.decision_audit.rejected is False
    assert view.runtime_diagnostics.current_candidate == "long"
    assert view.runtime_diagnostics.last_validation == "valid"
    assert paper_calls
    assert paper_calls[-1][0] is view.strategy_decision_v2
    assert paper_calls[-1][1] is view.risk_management_v2


def test_runtime_snapshot_uses_canonical_market_timestamp_session_and_verification_report():
    item = runtime()
    previous_day = NOW.date() - timedelta(days=1)
    item.process_daily_ohlc(
        DailyOHLC(previous_day, 100.0, 110.0, 90.0, 105.0),
        levels_trading_date=NOW.date(),
    )
    item.process_tick(tick(timestamp=NOW))

    view = item.snapshot()

    assert view.snapshot_created_at == view.latest_tick_at
    assert view.runtime_session is not None
    assert view.runtime_session.market_timestamp == view.latest_tick_at
    assert view.runtime_session.trading_date == NOW.date()
    assert view.runtime_session.previous_completed_trading_date == previous_day
    assert view.runtime_session.cpr_trading_date == NOW.date()
    assert view.runtime_session.camarilla_trading_date == NOW.date()
    stages = {stage.stage: stage for stage in view.runtime_verification_report}
    assert stages["Market Data"].owner == "SymbolRuntime"
    assert stages["Daily Context"].producer == "CPR/Camarilla/ADR/VWAP"
    assert stages["Daily Context"].session is view.runtime_session
    assert view.runtime_diagnostics.market_timestamp == view.latest_tick_at
    assert view.runtime_diagnostics.trading_date == NOW.date()


def test_vision_candidate_is_single_runtime_source_for_ai_explanation():
    item = runtime()

    candidate, report = process(item, snapshot())
    view = item.snapshot()

    assert view.vision_trade_candidate is candidate
    assert view.runtime_verification_report[-1].stage == "AI Explanation"
    assert view.vision_ai_explanation.startswith("Vision Method produced a long candidate")
    assert "legacy" not in view.vision_ai_explanation.lower()
    assert view.runtime_diagnostics.current_candidate == candidate.candidate_state.value
    assert report is item._vision_method_validation_report


def test_symbol_runtime_does_not_create_wall_clock_market_timestamps():
    source = Path("application/symbol_runtime.py").read_text(encoding="utf-8")

    assert "datetime.now" not in source
    assert "utcnow" not in source


def test_short_candidate_uses_existing_risk_lifecycle_direction():
    item = runtime()
    method_snapshot = snapshot(
        setup_qualification_context=setup(supporting=("Bearish BOS",)),
        option_confirmation_context=option(supporting=("Call writing supports setup",)),
    )
    method_snapshot = replace(method_snapshot, candidate_state=VisionCandidateState.SHORT_ELIGIBLE)

    candidate, _ = process(item, method_snapshot)

    view = item.snapshot()
    assert candidate.candidate_state is TradeCandidateState.SHORT
    assert candidate.direction is TradeCandidateDirection.SHORT
    assert view.strategy_decision_v2.direction is StrategyDirection.SHORT
    assert view.risk_management_v2.strategy is view.strategy_decision_v2
    assert view.trade_lifecycle_v1.strategy_decision is view.strategy_decision_v2


def test_non_actionable_vision_states_are_blocked_before_risk():
    for state in (
        VisionCandidateState.WAIT,
        VisionCandidateState.OBSERVE,
        VisionCandidateState.AVOID,
        VisionCandidateState.INSUFFICIENT_DATA,
        VisionCandidateState.PREPARE_LONG,
        VisionCandidateState.PREPARE_SHORT,
    ):
        item = runtime()
        method_snapshot = replace(snapshot(), candidate_state=state)

        candidate, _ = process(item, method_snapshot)
        view = item.snapshot()

        assert candidate.candidate_state in {TradeCandidateState.NO_CANDIDATE, TradeCandidateState.WAITING_LONG, TradeCandidateState.WAITING_SHORT}
        assert view.risk_management_v2 is None
        assert view.trade_lifecycle_v1.processing_count == 0
        assert view.decision_audit.rejected is True
        assert view.decision_audit.rejected_at == "Vision Method"


def test_risk_rejection_is_visible_for_vision_candidate():
    item = runtime()

    def rejected_risk_input(strategy):
        entry = 100.0
        return RiskManagementV2Input(
            strategy=strategy,
            account=AccountRiskState(strategy.timestamp, 100000.0, 100000.0, 100000.0, 100000.0, 0.0, 0.0, 0.0),
            session=SessionRiskState(strategy.timestamp.date(), 0, 0, 0, 0, 0.0),
            instrument_exposure=InstrumentExposureState(strategy.instrument, 0, 0.0, 0.0),
            proposed_entry_price=entry,
            proposed_invalidation_price=99.0,
            proposed_objective_price=None,
        )

    item._build_risk_management_v2_input = rejected_risk_input

    candidate, _ = process(item, snapshot())
    view = item.snapshot()

    assert candidate.direction is TradeCandidateDirection.LONG
    assert view.risk_management_v2.decision is RiskDecision.REJECTED
    assert view.trade_lifecycle_v1.processing_count == 0
    assert view.decision_audit.rejected is True
    assert view.decision_audit.rejected_at == "Risk"
    assert "Structural objective is required" in view.decision_audit.reason
    assert view.decision_audit.vision_trade_candidate is candidate


def test_journal_preserves_vision_references_after_closed_paper_lifecycle():
    item = runtime()
    candidate, _ = process(item, snapshot())
    opened = item.trade_lifecycle_v1.snapshot()
    objective = opened.risk_decision.objective_price

    closed = item.trade_lifecycle_v1.close_position(exit_price=objective + 0.5)
    item.trade_journal_v1_engine.record(closed)

    journal = item.trade_journal_v1_engine.snapshot()
    assert journal.latest_entry is not None
    assert journal.latest_entry.trade_source == "VISION_METHOD"
    assert journal.latest_entry.trade_candidate_reference is not None
    assert journal.latest_entry.vision_method_snapshot_reference == candidate.snapshot_reference
    assert journal.latest_entry.vision_method_validation_reference == candidate.validation_reference
    assert build_journal_view(item.snapshot()).latest_trade_source == "VISION_METHOD"


def test_duplicate_candidate_does_not_reprocess_risk_or_lifecycle():
    item = runtime()
    method_snapshot = snapshot()
    process(item, method_snapshot)
    first = item.snapshot()

    process(item, method_snapshot)
    second = item.snapshot()

    assert second.risk_management_v2 is first.risk_management_v2
    assert second.trade_lifecycle_v1.processing_count == first.trade_lifecycle_v1.processing_count


def test_journal_engine_deduplicates_repeated_closed_lifecycle_reference():
    item = runtime()
    process(item, snapshot())
    opened = item.trade_lifecycle_v1.snapshot()
    objective = opened.risk_decision.objective_price
    closed = item.trade_lifecycle_v1.close_position(exit_price=objective + 0.5)
    item.trade_journal_v1_engine.record(closed)

    duplicate = item.trade_journal_v1_engine.record(closed)

    assert duplicate.status is TradeRecordStatus.DUPLICATE
