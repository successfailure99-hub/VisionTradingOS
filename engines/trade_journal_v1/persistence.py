"""
Durable JSONL/checkpoint storage for Trade Journal V1.
"""

from __future__ import annotations

import json
import os
from dataclasses import fields
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator

from core.enums.instrument import Instrument
from engines.position_management_v1.enums import PositionExitReason
from engines.trade_journal_v1.enums import PaperRecoveryStatus, TradeOutcome
from engines.trade_journal_v1.models import (
    ActivePaperPositionCheckpoint,
    PaperRecoverySnapshot,
    VisionTradeJournalRecord,
)

JOURNAL_SCHEMA_VERSION = 1
CHECKPOINT_SCHEMA_VERSION = 1
SENSITIVE_KEYS = ("token", "access_token", "api_key", "secret", "credential", "password")


class TradeJournalPersistence:
    def __init__(self, *, journal_path: Path | str | None, checkpoint_path: Path | str | None, enabled: bool = True):
        self.journal_path = Path(journal_path) if journal_path is not None else None
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path is not None else None
        self.enabled = bool(enabled)
        self.write_count = 0
        self.duplicate_count = 0
        self.malformed_count = 0
        self.last_error: str | None = None

    def append_record(self, record: VisionTradeJournalRecord) -> bool:
        if not isinstance(record, VisionTradeJournalRecord):
            raise TypeError("record must be VisionTradeJournalRecord")
        if not self.enabled or self.journal_path is None:
            return False
        existing = self.get_record(record.trade_id)
        if existing is not None:
            if existing != record:
                raise ValueError("durable duplicate trade identity has different content")
            self.duplicate_count += 1
            return False
        payload = {"schema_version": JOURNAL_SCHEMA_VERSION, "record": _record_to_payload(record)}
        _reject_sensitive_payload(payload)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        fd = os.open(self.journal_path, flags, 0o644)
        try:
            _write_all(fd, line.encode("utf-8"))
            os.fsync(fd)
            self.write_count += 1
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = _safe_error(exc)
            raise
        finally:
            os.close(fd)

    def iter_records(self, query: "TradeJournalQuery | None" = None) -> Iterator[VisionTradeJournalRecord]:
        query = query or TradeJournalQuery()
        if not self.enabled or self.journal_path is None or not self.journal_path.exists():
            return
        with self.journal_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    if payload.get("schema_version") != JOURNAL_SCHEMA_VERSION:
                        raise ValueError("unsupported journal schema")
                    record = _record_from_payload(payload["record"])
                except Exception:
                    self.malformed_count += 1
                    continue
                if query.matches(record):
                    yield record

    def records(self, query: "TradeJournalQuery | None" = None, *, limit: int | None = None) -> tuple[VisionTradeJournalRecord, ...]:
        items = []
        for record in self.iter_records(query):
            items.append(record)
            if limit is not None and len(items) >= limit:
                break
        return tuple(items)

    def get_record(self, trade_id: str) -> VisionTradeJournalRecord | None:
        query = TradeJournalQuery(trade_id=trade_id)
        return next(self.iter_records(query), None)

    def save_checkpoint(self, checkpoint: ActivePaperPositionCheckpoint) -> None:
        if not isinstance(checkpoint, ActivePaperPositionCheckpoint):
            raise TypeError("checkpoint must be ActivePaperPositionCheckpoint")
        if not self.enabled or self.checkpoint_path is None:
            return
        payload = {"schema_version": CHECKPOINT_SCHEMA_VERSION, "checkpoint": _checkpoint_to_payload(checkpoint)}
        _reject_sensitive_payload(payload)
        _atomic_write_json(self.checkpoint_path, payload)

    def load_checkpoint(self, *, now: datetime, expected_instrument: Instrument | None = None, trading_date: date | None = None) -> PaperRecoverySnapshot:
        _aware(now, "now")
        if not self.enabled or self.checkpoint_path is None or not self.checkpoint_path.exists():
            return PaperRecoverySnapshot(PaperRecoveryStatus.NO_POSITION, None, None, now, "No active paper-position checkpoint.")
        try:
            payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
                raise ValueError("unsupported checkpoint schema")
            checkpoint = _checkpoint_from_payload(payload["checkpoint"])
            if expected_instrument is not None and checkpoint.instrument is not expected_instrument:
                return PaperRecoverySnapshot(PaperRecoveryStatus.RECOVERY_BLOCKED, checkpoint.trade_id, checkpoint, now, "Checkpoint instrument mismatch.")
            if trading_date is not None and checkpoint.trading_date != trading_date:
                return PaperRecoverySnapshot(PaperRecoveryStatus.CLOSED_BEFORE_SHUTDOWN, checkpoint.trade_id, checkpoint, now, "Checkpoint belongs to a previous trading session.")
            return PaperRecoverySnapshot(PaperRecoveryStatus.RESTORED, checkpoint.trade_id, checkpoint, now, "Active paper position checkpoint restored.")
        except Exception as exc:
            self.last_error = _safe_error(exc)
            return PaperRecoverySnapshot(PaperRecoveryStatus.RECOVERY_FAILED, None, None, now, self.last_error)

    def clear_checkpoint(self) -> None:
        if self.checkpoint_path is not None and self.checkpoint_path.exists():
            self.checkpoint_path.unlink()


class TradeJournalQuery:
    def __init__(
        self,
        *,
        trade_id: str | None = None,
        instrument: Instrument | str | None = None,
        trading_date: date | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        direction: str | None = None,
        setup_classification: str | None = None,
        candidate_quality: str | None = None,
        validation_result: str | None = None,
        exit_reason: str | None = None,
        outcome: TradeOutcome | str | None = None,
        trade_source: str | None = None,
        open_state: str | None = None,
    ):
        self.trade_id = _text_or_none(trade_id)
        self.instrument = instrument.value if isinstance(instrument, Instrument) else _text_or_none(instrument)
        self.trading_date = trading_date
        self.start_date = start_date
        self.end_date = end_date
        self.direction = _text_or_none(direction)
        self.setup_classification = _text_or_none(setup_classification)
        self.candidate_quality = _text_or_none(candidate_quality)
        self.validation_result = _text_or_none(validation_result)
        self.exit_reason = exit_reason.value if isinstance(exit_reason, PositionExitReason) else _text_or_none(exit_reason)
        self.outcome = outcome.value if isinstance(outcome, TradeOutcome) else _text_or_none(outcome)
        self.trade_source = _text_or_none(trade_source)
        self.open_state = _text_or_none(open_state)

    def matches(self, record: VisionTradeJournalRecord) -> bool:
        if self.trade_id is not None and record.trade_id != self.trade_id:
            return False
        if self.instrument is not None and record.instrument.value != self.instrument:
            return False
        if self.trading_date is not None and record.trading_date != self.trading_date:
            return False
        if self.start_date is not None and record.trading_date < self.start_date:
            return False
        if self.end_date is not None and record.trading_date > self.end_date:
            return False
        if self.direction is not None and record.candidate_direction != self.direction:
            return False
        if self.setup_classification is not None and record.setup_classification != self.setup_classification:
            return False
        if self.candidate_quality is not None and record.candidate_quality != self.candidate_quality:
            return False
        if self.validation_result is not None and record.validation_result != self.validation_result:
            return False
        if self.exit_reason is not None and record.exit_reason.value != self.exit_reason:
            return False
        if self.outcome is not None and record.outcome.value != self.outcome:
            return False
        if self.trade_source is not None and record.trade_source != self.trade_source:
            return False
        if self.open_state is not None and self.open_state.lower() != "closed":
            return False
        return True


def record_from_entry(entry, *, exchange: str = "NSE", timeframe: str = "1m", created_at: datetime | None = None) -> VisionTradeJournalRecord:
    created_at = created_at or entry.closed_at
    trace_ref = f"{entry.vision_method_validation_reference or '-'}:trace"
    risk_ref = f"{entry.instrument.value}:{entry.risk_decision.value}:{entry.risk_approved_quantity}"
    lifecycle_ref = f"{entry.instrument.value}:{entry.lifecycle_snapshot.timestamp.isoformat()}:{entry.lifecycle_snapshot.stage.value}"
    paper_ref = entry.lifecycle_snapshot.position_result.position.position_id
    return VisionTradeJournalRecord(
        trade_id=entry.trade_id,
        instrument=entry.instrument,
        exchange=exchange,
        timeframe=timeframe,
        trading_date=entry.opened_at.date(),
        trade_source=entry.trade_source,
        setup_classification=entry.setup_family.value,
        candidate_direction=entry.direction.value,
        candidate_quality=entry.setup_quality.value,
        validation_result="valid" if entry.vision_method_validation_reference else "not_available",
        outcome=entry.outcome,
        exit_reason=entry.exit_reason,
        vision_method_snapshot_reference=entry.vision_method_snapshot_reference or "-",
        vision_method_validation_reference=entry.vision_method_validation_reference or "-",
        trade_candidate_reference=entry.trade_candidate_reference or "-",
        risk_reference=risk_ref,
        lifecycle_reference=lifecycle_ref,
        paper_position_reference=paper_ref,
        validation_trace_reference=trace_ref,
        entry_timestamp=entry.opened_at,
        entry_price=entry.entry_price,
        quantity=entry.closed_quantity,
        stop_price=entry.invalidation_price,
        target_price=entry.objective_price,
        exit_timestamp=entry.closed_at,
        exit_price=entry.average_exit_price,
        gross_pnl=entry.realized_pnl,
        fees=0.0,
        slippage=0.0,
        net_pnl=entry.realized_pnl,
        supporting_reasons=entry.lifecycle_snapshot.strategy_decision.rationale if entry.lifecycle_snapshot.strategy_decision else (),
        blocking_reasons=entry.lifecycle_snapshot.strategy_decision.warnings if entry.lifecycle_snapshot.strategy_decision else (),
        created_at=created_at,
        updated_at=created_at,
    )


def checkpoint_from_runtime_position(position, *, trading_date: date, exchange: str = "NSE", timeframe: str = "1m", created_at: datetime | None = None) -> ActivePaperPositionCheckpoint:
    created_at = created_at or position.updated_at
    return ActivePaperPositionCheckpoint(
        trade_id=position.trade_id,
        instrument=Instrument(position.instrument.value),
        exchange=exchange,
        timeframe=timeframe,
        trading_date=trading_date,
        candidate_identity=position.candidate_reference,
        candidate_state=position.candidate_state,
        direction=position.direction,
        entry_timestamp=position.entry_timestamp or position.updated_at or created_at,
        entry_price=position.entry_price or position.current_price or 1.0,
        quantity=max(1, position.quantity),
        stop_price=position.stop_price or position.entry_price or 1.0,
        target_price=position.target_price,
        last_market_timestamp=position.updated_at or position.entry_timestamp or created_at,
        lifecycle_state=position.lifecycle_state,
        position_state=position.status,
        unrealized_pnl=position.unrealized_pnl,
        vision_method_snapshot_reference=position.vision_method_snapshot_reference,
        vision_method_validation_reference=position.validation_report_reference,
        trade_candidate_reference=position.candidate_reference,
        risk_reference=position.risk_reference,
        created_at=created_at,
        updated_at=position.updated_at or created_at,
    )


def _record_to_payload(record: VisionTradeJournalRecord) -> dict[str, object]:
    return _to_payload(record)


def _checkpoint_to_payload(checkpoint: ActivePaperPositionCheckpoint) -> dict[str, object]:
    return _to_payload(checkpoint)


def _record_from_payload(payload: dict[str, object]) -> VisionTradeJournalRecord:
    data = dict(payload)
    data["instrument"] = Instrument(data["instrument"])
    data["trading_date"] = date.fromisoformat(data["trading_date"])
    data["outcome"] = TradeOutcome(data["outcome"])
    data["exit_reason"] = PositionExitReason(data["exit_reason"])
    for name in ("entry_timestamp", "exit_timestamp", "created_at", "updated_at"):
        data[name] = datetime.fromisoformat(data[name])
    data["supporting_reasons"] = tuple(data.get("supporting_reasons") or ())
    data["blocking_reasons"] = tuple(data.get("blocking_reasons") or ())
    return VisionTradeJournalRecord(**data)


def _checkpoint_from_payload(payload: dict[str, object]) -> ActivePaperPositionCheckpoint:
    data = dict(payload)
    data["instrument"] = Instrument(data["instrument"])
    data["trading_date"] = date.fromisoformat(data["trading_date"])
    for name in ("entry_timestamp", "last_market_timestamp", "created_at", "updated_at"):
        data[name] = datetime.fromisoformat(data[name])
    return ActivePaperPositionCheckpoint(**data)


def _to_payload(item) -> dict[str, object]:
    payload = {}
    for field in fields(item):
        value = getattr(item, field.name)
        if isinstance(value, datetime):
            payload[field.name] = value.isoformat()
        elif isinstance(value, date):
            payload[field.name] = value.isoformat()
        elif isinstance(value, tuple):
            payload[field.name] = list(value)
        else:
            payload[field.name] = getattr(value, "value", value)
    return payload


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def _reject_sensitive_payload(payload: dict[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True).lower()
    if any(key in text for key in SENSITIVE_KEYS):
        raise ValueError("journal payload contains sensitive field name")


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("Unable to append durable trade journal record.")
        view = view[written:]


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _text_or_none(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    for token in SENSITIVE_KEYS:
        text = text.replace(token, "[redacted]")
    return text
