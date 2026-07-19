"""
Deterministic completed paper-trade journal repository with JSON Lines storage.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from engines.paper_trading.enums import PaperExitType
from engines.paper_trading.models import PaperTradeRecord
from engines.performance_analytics.enums import AnalyticsRecordStatus
from engines.performance_analytics.models import AnalyticsDiagnostics, JournalRecordResult
from engines.strategy.enums import TradeDirection


SCHEMA_VERSION = 1


class JournalRepositoryConflictError(ValueError):
    pass


class PaperTradeJournalRepository:
    def __init__(self, *, path: Path | str | None = None, persistence_enabled: bool = True):
        self._path = Path(path) if path is not None else None
        self._persistence_enabled = bool(persistence_enabled)
        self._records: dict[str, PaperTradeRecord] = {}
        self._order: tuple[str, ...] = ()
        self._write_failures = 0
        self._load_failures = 0
        self._writes = 0

    @property
    def diagnostics(self) -> AnalyticsDiagnostics:
        return AnalyticsDiagnostics(
            loaded_records=len(self._records),
            persistence_writes=self._writes,
            persistence_failures=self._write_failures,
            load_failures=self._load_failures,
            broker_order_calls=0,
        )

    def load(self) -> tuple[PaperTradeRecord, ...]:
        if not self._persistence_enabled or self._path is None or not self._path.exists():
            return self.records()
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if payload.get("schema_version") != SCHEMA_VERSION:
                    raise ValueError("unsupported journal schema")
                self.add(_record_from_payload(payload["record"]), persist=False)
            except Exception:
                self._load_failures += 1
        return self.records()

    def add(self, record: PaperTradeRecord, *, persist: bool = True) -> JournalRecordResult:
        if not isinstance(record, PaperTradeRecord):
            raise TypeError("record must be PaperTradeRecord")
        existing = self._records.get(record.trade_id)
        if existing is not None:
            if existing != record:
                return JournalRecordResult(AnalyticsRecordStatus.CONFLICT, existing, "Conflicting duplicate trade_id rejected.")
            return JournalRecordResult(AnalyticsRecordStatus.DUPLICATE, existing, "Duplicate trade ignored.")
        self._records[record.trade_id] = record
        self._order = tuple(sorted(self._records, key=lambda trade_id: (self._records[trade_id].exit_time, trade_id)))
        if persist and self._persistence_enabled and self._path is not None:
            try:
                self._append(record)
            except Exception:
                self._write_failures += 1
                raise
        return JournalRecordResult(AnalyticsRecordStatus.ACCEPTED, record, "Trade accepted.")

    def records(self, *, instrument=None, start_date=None, end_date=None, direction=None, setup=None) -> tuple[PaperTradeRecord, ...]:
        normalized_instrument = instrument.upper() if isinstance(instrument, str) and instrument.strip() else None
        normalized_direction = str(getattr(direction, "value", direction)).strip() if direction is not None else None
        normalized_setup = setup.strip() if isinstance(setup, str) and setup.strip() else None
        return tuple(
            record
            for record in (self._records[trade_id] for trade_id in self._order)
            if (normalized_instrument is None or record.instrument == normalized_instrument)
            and (start_date is None or record.trading_date >= start_date)
            and (end_date is None or record.trading_date <= end_date)
            and (normalized_direction is None or getattr(record.direction, "value", record.direction) == normalized_direction)
            and (normalized_setup is None or record.strategy_setup == normalized_setup)
        )

    def latest(self, limit: int) -> tuple[PaperTradeRecord, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be positive integer")
        return tuple(reversed(self.records()[-limit:]))

    def get(self, trade_id: str) -> PaperTradeRecord:
        try:
            return self._records[trade_id]
        except KeyError as exc:
            raise ValueError("trade_id not found") from exc

    def reset(self, *, clear_persistent_data: bool = False) -> None:
        self._records.clear()
        self._order = ()
        if clear_persistent_data and self._path is not None and self._path.exists():
            self._path.unlink()

    def _append(self, record: PaperTradeRecord) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"schema_version": SCHEMA_VERSION, "record": _record_to_payload(record)}, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
            handle.flush()
        self._writes += 1


def _record_to_payload(record: PaperTradeRecord) -> dict[str, object]:
    payload = {}
    for field in record.__dataclass_fields__:
        value = getattr(record, field)
        if isinstance(value, datetime):
            payload[field] = value.isoformat()
        elif isinstance(value, date):
            payload[field] = value.isoformat()
        elif isinstance(value, tuple):
            payload[field] = list(value)
        else:
            payload[field] = getattr(value, "value", value)
    return payload


def _record_from_payload(payload: dict[str, object]) -> PaperTradeRecord:
    data = dict(payload)
    data["direction"] = TradeDirection(data["direction"])
    data["exit_type"] = PaperExitType(data["exit_type"])
    for name in ("entry_time", "exit_time"):
        data[name] = datetime.fromisoformat(data[name])
    data["trading_date"] = date.fromisoformat(data["trading_date"])
    data["strategy_reasoning"] = tuple(data.get("strategy_reasoning") or ())
    return PaperTradeRecord(**data)

