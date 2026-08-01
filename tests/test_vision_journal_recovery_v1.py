from dataclasses import replace
from datetime import timedelta

import pytest

from application import RuntimeConfiguration, RuntimeInstrument, SymbolRuntime
from application.models import RuntimePaperPositionSnapshot
from core.event_bus import EventBus
from core.enums.instrument import Instrument
from engines.trade_journal_v1 import PaperRecoveryStatus, TradeJournalV1Configuration, TradeJournalV1Engine
from engines.trade_journal_v1.persistence import TradeJournalPersistence, TradeJournalQuery
from tests.test_trade_journal_v1_integration import closed_lifecycle
from tests.test_vision_method_validation_v1 import NOW, snapshot
from tests.test_vision_paper_trading_integration_v1 import process, tick


def journal_engine(tmp_path):
    engine = TradeJournalV1Engine(
        configuration=TradeJournalV1Configuration(
            journal_path=tmp_path / "vision_journal.jsonl",
            checkpoint_path=tmp_path / "active_checkpoint.json",
        )
    )
    engine.start()
    return engine


def runtime_with_durable_journal(tmp_path):
    item = SymbolRuntime(EventBus(), RuntimeConfiguration(), RuntimeInstrument.NIFTY)
    item.start()
    item.trade_journal_v1_engine = TradeJournalV1Engine(
        configuration=TradeJournalV1Configuration(
            journal_path=tmp_path / "vision_journal.jsonl",
            checkpoint_path=tmp_path / "active_checkpoint.json",
        )
    )
    item.trade_journal_v1_engine.start()
    item._paper_recovery = item.trade_journal_v1_engine.load_checkpoint(expected_instrument=Instrument.NIFTY)
    item._last_tick = tick()
    return item


def runtime_position():
    return RuntimePaperPositionSnapshot(
        trade_id="trade-1",
        instrument=RuntimeInstrument.NIFTY,
        source="VISION_METHOD",
        candidate_state="long",
        direction="long",
        status="open",
        lifecycle_state="position_opened",
        risk_state="approved",
        candidate_reference="candidate-1",
        vision_method_snapshot_reference="method-1",
        validation_report_reference="validation-1",
        risk_reference="risk-1",
        entry_timestamp=NOW,
        entry_price=100.0,
        current_price=101.0,
        quantity=1,
        stop_reference="Below Opening Range",
        target_reference="H4",
        stop_price=99.0,
        target_price=102.0,
        gross_pnl=1.0,
        fees=0.0,
        slippage=0.0,
        net_pnl=1.0,
        unrealized_pnl=1.0,
        realized_pnl=0.0,
        blocking_reason="-",
        recovery_status="RESTORED",
        updated_at=NOW + timedelta(minutes=1),
    )


def test_long_paper_trade_is_journaled_once_and_searchable(tmp_path):
    engine = journal_engine(tmp_path)
    lifecycle = closed_lifecycle(exit_price=120.0)

    first = engine.record(lifecycle)
    duplicate = engine.record(lifecycle)

    assert first.status.value == "recorded"
    assert duplicate.status.value == "duplicate"
    records = engine.durable_records(trade_id=first.entry.trade_id)
    assert len(records) == 1
    assert records[0].trade_id == first.entry.trade_id
    assert records[0].instrument is Instrument.NIFTY
    assert records[0].trade_source == first.entry.trade_source
    assert engine.analytics_snapshot().overall.trade_count == 1


def test_short_paper_trade_journaled_once(tmp_path):
    engine = journal_engine(tmp_path)
    lifecycle = closed_lifecycle(exit_price=90.0)

    result = engine.record(lifecycle)

    assert result.status.value == "recorded"
    assert len(engine.durable_records()) == 1
    assert engine.persistence_write_count == 1


def test_checkpoint_created_updated_and_restored_same_session(tmp_path):
    engine = journal_engine(tmp_path)
    checkpoint = engine.save_checkpoint(runtime_position(), trading_date=NOW.date())

    restored = engine.load_checkpoint(expected_instrument=Instrument.NIFTY, trading_date=NOW.date())

    assert checkpoint.trade_id == "trade-1"
    assert restored.status is PaperRecoveryStatus.RESTORED
    assert restored.checkpoint.trade_id == "trade-1"
    assert engine.checkpoint_exists is True


def test_next_session_stale_checkpoint_is_closed_before_shutdown(tmp_path):
    engine = journal_engine(tmp_path)
    engine.save_checkpoint(runtime_position(), trading_date=NOW.date())

    restored = engine.load_checkpoint(expected_instrument=Instrument.NIFTY, trading_date=NOW.date() + timedelta(days=1))

    assert restored.status is PaperRecoveryStatus.CLOSED_BEFORE_SHUTDOWN
    assert "previous trading session" in restored.reason


def test_corrupted_checkpoint_recovers_failed_without_crash(tmp_path):
    checkpoint_path = tmp_path / "active_checkpoint.json"
    checkpoint_path.write_text("not-json", encoding="utf-8")
    persistence = TradeJournalPersistence(journal_path=tmp_path / "journal.jsonl", checkpoint_path=checkpoint_path)

    restored = persistence.load_checkpoint(now=NOW, expected_instrument=Instrument.NIFTY, trading_date=NOW.date())

    assert restored.status is PaperRecoveryStatus.RECOVERY_FAILED
    assert restored.reason


def test_malformed_journal_line_does_not_block_valid_records(tmp_path):
    engine = journal_engine(tmp_path)
    first = engine.record(closed_lifecycle(exit_price=120.0))
    path = tmp_path / "vision_journal.jsonl"
    path.write_text("{bad json}\n" + path.read_text(encoding="utf-8"), encoding="utf-8")

    records = engine.durable_records(trade_id=first.entry.trade_id)

    assert len(records) == 1
    assert records[0].trade_id == first.entry.trade_id


def test_journal_filtering_by_instrument_date_setup_and_result(tmp_path):
    engine = journal_engine(tmp_path)
    result = engine.record(closed_lifecycle(exit_price=120.0))
    record = engine.durable_records(trade_id=result.entry.trade_id)[0]

    filtered = engine.durable_records(
        instrument=Instrument.NIFTY,
        trading_date=record.trading_date,
        setup_classification=record.setup_classification,
        validation_result=record.validation_result,
        outcome=record.outcome,
        trade_source=record.trade_source,
    )

    assert filtered == (record,)


def test_streaming_query_can_limit_large_journal_without_full_materialization(tmp_path):
    engine = journal_engine(tmp_path)
    engine.record(closed_lifecycle(exit_price=120.0))
    persistence = engine._persistence

    records = persistence.records(TradeJournalQuery(instrument=Instrument.NIFTY), limit=1)

    assert len(records) == 1


def test_sensitive_fields_are_never_serialized_to_journal_or_checkpoint(tmp_path):
    engine = journal_engine(tmp_path)
    result = engine.record(closed_lifecycle(exit_price=120.0))
    record = engine.durable_records(trade_id=result.entry.trade_id)[0]
    unsafe = replace(record, supporting_reasons=("access_token leaked",))

    with pytest.raises(ValueError):
        engine._persistence.append_record(unsafe)


def test_runtime_checkpoint_dashboard_and_journal_state_align(tmp_path):
    item = runtime_with_durable_journal(tmp_path)
    process(item, snapshot())

    opened = item.snapshot()

    assert opened.canonical_paper_position is not None
    assert opened.journal_persistence.active_checkpoint_status == "ACTIVE"
    assert opened.journal_persistence.recovery_status == "RESTORED"
    assert opened.canonical_paper_position.recovery_status == "RESTORED"


def test_runtime_close_clears_checkpoint_and_writes_once(tmp_path):
    item = runtime_with_durable_journal(tmp_path)
    process(item, snapshot())
    opened = item.snapshot()
    objective = opened.risk_management_v2.objective_price
    close_tick = tick(objective + 0.5, timestamp=opened.trade_lifecycle_v1.timestamp + timedelta(seconds=1))

    item._process_paper_tick(close_tick)
    item._process_paper_tick(close_tick)
    closed = item.snapshot()

    assert closed.trade_journal_v1.trade_count == 1
    assert closed.journal_persistence.active_checkpoint_status == "NONE"
    assert closed.journal_persistence.latest_journal_record_id == closed.trade_journal_v1.latest_entry.trade_id
    assert len(item.trade_journal_v1_engine.durable_records()) == 1
