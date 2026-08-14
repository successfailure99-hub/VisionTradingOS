from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from core.models.daily_ohlc import DailyOHLC
from core.models.candle import Candle
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.event_bus import EventBus
from core.models.tick import Tick
from dashboard.presenters import build_journal_view, build_position_view
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


def candle(start, end, *, close=100.0, timeframe="5m"):
    return Candle(
        symbol=Instrument.NIFTY.value,
        timeframe=timeframe,
        start_time=start,
        end_time=end,
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        volume=100,
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
    item._process_paper_tick(tick(100.1, timestamp=lifecycle_timestamp + timedelta(seconds=1)))

    view = item.snapshot()
    assert candidate.candidate_state is TradeCandidateState.LONG
    assert candidate.direction is TradeCandidateDirection.LONG
    assert view.vision_trade_candidate is candidate
    assert view.vision_method_snapshot is item._vision_method_snapshot
    assert view.vision_method_validation_report is item._vision_method_validation_report
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
    assert paper_calls == []
    assert view.canonical_paper_position is not None
    assert view.canonical_paper_position.source == "VISION_METHOD"
    assert view.canonical_paper_position.candidate_reference == view.strategy_decision_v2.trade_candidate_reference
    assert view.canonical_paper_position.risk_state in {"approved", "approved_reduced"}


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
    assert view.vision_method_snapshot is item._vision_method_snapshot
    assert view.vision_method_validation_report is report
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


def test_non_actionable_vision_update_clears_stale_strategy_exposure():
    item = runtime()
    process(item, snapshot())
    actionable = item.snapshot()
    assert actionable.strategy_decision_v2 is not None

    wait_snapshot = replace(snapshot(), candidate_state=VisionCandidateState.WAIT)
    candidate, _ = process(item, wait_snapshot)
    view = item.snapshot()
    stages = {stage.stage: stage for stage in view.runtime_verification_report}

    assert view.vision_trade_candidate is candidate
    assert view.strategy_decision_v2 is None
    assert stages["Strategy"].status == "NOT_APPLICABLE"
    assert stages["Risk"].status == "NOT_APPLICABLE"
    assert "No actionable candidate" in stages["Risk"].blocking_reason


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


def test_end_to_end_vision_runtime_paper_journal_ai_dashboard_verification():
    item = runtime()

    candidate, report = process(item, snapshot())
    opened_lifecycle = item.trade_lifecycle_v1.snapshot()
    item._process_paper_tick(tick(100.1, timestamp=opened_lifecycle.timestamp + timedelta(seconds=1)))
    open_view = item.snapshot()
    open_stages = {stage.stage: stage for stage in open_view.runtime_verification_report}

    assert open_view.vision_method_snapshot is item._vision_method_snapshot
    assert open_view.vision_method_validation_report is report
    assert open_view.vision_trade_candidate is candidate
    assert open_view.strategy_decision_v2.trade_source == "VISION_METHOD"
    assert open_view.risk_management_v2.strategy is open_view.strategy_decision_v2
    assert open_view.trade_lifecycle_v1.strategy_decision is open_view.strategy_decision_v2
    assert open_stages["Vision Method"].status == "READY"
    assert open_stages["Validation"].status == "READY"
    assert open_stages["Runtime Adapter"].status == "READY"
    assert open_stages["TradeCandidate"].status == "READY"
    assert open_stages["Risk"].status == "READY"
    assert open_stages["Lifecycle"].status == "READY"
    assert open_stages["Paper Position"].producer == "PositionManagementV1"
    assert open_stages["Paper Trade"].producer == "PositionManagementV1"
    assert open_stages["Paper Trade"].status == "READY"
    assert open_stages["AI Explanation"].status == "READY"
    assert open_view.canonical_paper_position is not None
    assert open_view.runtime_diagnostics.paper_trade_state.startswith("VISION_METHOD:")
    assert open_view.vision_ai_explanation.startswith("Vision Method produced a long candidate")

    objective = open_view.trade_lifecycle_v1.risk_decision.objective_price
    closed_lifecycle = item.trade_lifecycle_v1.close_position(exit_price=objective + 0.5)
    item.trade_journal_v1_engine.record(closed_lifecycle)
    closed_view = item.snapshot()
    closed_stages = {stage.stage: stage for stage in closed_view.runtime_verification_report}

    assert closed_view.trade_journal_v1.latest_entry is not None
    assert closed_view.trade_journal_v1.latest_entry.trade_source == "VISION_METHOD"
    assert closed_view.trade_journal_v1.latest_entry.trade_candidate_reference == closed_view.strategy_decision_v2.trade_candidate_reference
    assert closed_view.trade_journal_v1.latest_entry.vision_method_snapshot_reference == candidate.snapshot_reference
    assert closed_view.trade_journal_v1.latest_entry.vision_method_validation_reference == candidate.validation_reference
    assert closed_stages["Journal"].status == "READY"
    assert build_journal_view(closed_view).latest_trade_source == "VISION_METHOD"


def test_canonical_vision_paper_position_drives_dashboard_status():
    item = runtime()
    candidate, _ = process(item, snapshot())
    opened = item.snapshot()

    canonical = opened.canonical_paper_position
    position = build_position_view(opened)

    assert canonical is not None
    assert canonical.source == "VISION_METHOD"
    assert canonical.trade_id
    assert canonical.candidate_reference == opened.strategy_decision_v2.trade_candidate_reference
    assert canonical.vision_method_snapshot_reference == candidate.snapshot_reference
    assert canonical.validation_report_reference == candidate.validation_reference
    assert canonical.recovery_status in {"RESTORED", "NO_POSITION"}
    assert position.status == "Vision Paper Position Open"
    assert position.trade_source == "VISION_METHOD"
    assert position.trade_id == canonical.trade_id
    assert position.candidate_state == "long"
    assert position.risk_state in {"approved", "approved_reduced"}
    assert position.lifecycle_state == opened.trade_lifecycle_v1.stage.value


def test_target_tick_closes_canonical_position_and_records_journal_once():
    item = runtime()
    process(item, snapshot())
    opened = item.snapshot()
    objective = opened.risk_management_v2.objective_price
    close_tick = tick(objective + 0.5, timestamp=opened.trade_lifecycle_v1.timestamp + timedelta(seconds=1))

    item._process_paper_tick(close_tick)
    first = item.snapshot()
    item._process_paper_tick(close_tick)
    second = item.snapshot()

    assert first.canonical_paper_position.status in {"closed", "objective_reached"}
    assert first.canonical_paper_position.realized_pnl > 0
    assert first.trade_journal_v1.trade_count == 1
    assert second.trade_journal_v1.trade_count == 1
    assert build_position_view(first).status in {"Vision Paper Position Open", "Vision Paper Position Closed"}


def test_stop_tick_closes_canonical_position_without_legacy_paper_engine():
    item = runtime()
    paper_calls = []
    original_on_tick = item.paper_trading_engine.on_tick

    def paper_spy(live_tick, *, strategy=None, risk=None):
        paper_calls.append((strategy, risk))
        return original_on_tick(live_tick, strategy=strategy, risk=risk)

    item.paper_trading_engine.on_tick = paper_spy
    process(item, snapshot())
    opened = item.snapshot()
    invalidation = opened.risk_management_v2.invalidation_price

    item._process_paper_tick(tick(invalidation - 0.5, timestamp=opened.trade_lifecycle_v1.timestamp + timedelta(seconds=1)))
    closed = item.snapshot()

    assert paper_calls == []
    assert closed.canonical_paper_position.status == "invalidated"
    assert closed.canonical_paper_position.realized_pnl < 0
    assert closed.trade_journal_v1.trade_count == 1


def test_duplicate_refresh_and_reconnect_do_not_duplicate_vision_position():
    item = runtime()
    method_snapshot = snapshot()
    process(item, method_snapshot)
    first = item.snapshot()

    item.snapshot()
    process(item, method_snapshot)
    item._process_paper_tick(tick(100.1, timestamp=first.trade_lifecycle_v1.timestamp + timedelta(seconds=1)))
    second = item.snapshot()

    assert second.canonical_paper_position.trade_id == first.canonical_paper_position.trade_id
    assert second.trade_lifecycle_v1.position_open_count == 1
    assert second.trade_lifecycle_v1.processing_count == first.trade_lifecycle_v1.processing_count
    assert second.paper_trading.position is None


def test_multi_candle_recovery_keeps_catchup_history_and_refreshes_latest_context_without_trade():
    item = runtime()
    item._vision_decision_timeframe = TimeFrame.FIVE_MINUTES
    first = candle(NOW.replace(hour=9, minute=15), NOW.replace(hour=9, minute=20), close=100.0)
    second = candle(NOW.replace(hour=9, minute=20), NOW.replace(hour=9, minute=25), close=101.0)
    latest = candle(NOW.replace(hour=9, minute=25), NOW.replace(hour=9, minute=30), close=102.0)
    item._last_closed_candles_by_timeframe[item._vision_decision_timeframe] = (first, second, latest)
    calls = []

    def spy(candle_item, *, allow_trade=True, provenance="LIVE"):
        calls.append((candle_item, allow_trade, provenance))

    item._process_runtime_vision_decision_candle = spy

    item._process_runtime_vision_decision_candles((item._vision_decision_timeframe,))

    assert item._vision_decision_identity(first) in item._processed_vision_decision_identities
    assert item._vision_decision_identity(second) in item._processed_vision_decision_identities
    assert item._vision_decision_identity(latest) not in item._processed_vision_decision_identities
    assert calls == [(latest, False, "RECOVERY_CONTEXT")]
    assert item._decision_audit.rejected_at == "HISTORICAL_CATCHUP"


def test_single_stale_recovered_vision_candle_is_non_trading_recovery_context():
    item = runtime()
    item._vision_decision_timeframe = TimeFrame.FIVE_MINUTES
    stale = candle(NOW.replace(hour=9, minute=15), NOW.replace(hour=9, minute=20), close=100.0)
    item._last_tick = tick(timestamp=stale.end_time + item._base_timeframe.duration + timedelta(seconds=1))
    item._last_closed_candles_by_timeframe[item._vision_decision_timeframe] = (stale,)
    calls = []

    def spy(candle_item, *, allow_trade=True, provenance="LIVE"):
        calls.append((candle_item, allow_trade, provenance))

    item._process_runtime_vision_decision_candle = spy

    item._process_runtime_vision_decision_candles((item._vision_decision_timeframe,))

    assert calls == [(stale, False, "RECOVERY_CONTEXT")]


def test_boundary_tick_closed_vision_candle_remains_live_context():
    item = runtime()
    item._vision_decision_timeframe = TimeFrame.FIVE_MINUTES
    live = candle(NOW.replace(hour=10, minute=0), NOW.replace(hour=10, minute=5), close=100.0)
    item._last_tick = tick(timestamp=live.end_time + timedelta(seconds=1))
    item._last_closed_candles_by_timeframe[item._vision_decision_timeframe] = (live,)
    calls = []

    def spy(candle_item, *, allow_trade=True, provenance="LIVE"):
        calls.append((candle_item, allow_trade, provenance))

    item._process_runtime_vision_decision_candle = spy

    item._process_runtime_vision_decision_candles((item._vision_decision_timeframe,))

    assert calls == [(live, True, "LIVE")]


def test_non_actionable_candidate_has_no_canonical_paper_position():
    item = runtime()
    process(item, replace(snapshot(), candidate_state=VisionCandidateState.WAIT))
    view = item.snapshot()

    assert view.canonical_paper_position is None
    assert build_position_view(view).status == "No Active Position"
