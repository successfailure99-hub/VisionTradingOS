from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass, replace
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from engines.deterministic_backtest.models import BACKTEST_SCHEMA_VERSION, BacktestBatchResult


class BacktestReportRepository:
    def __init__(self, output_directory: Path | str):
        self._output_directory = Path(output_directory)
        self._writes = 0
        self._failures = 0

    @property
    def writes(self) -> int:
        return self._writes

    @property
    def failures(self) -> int:
        return self._failures

    def write_report(self, result: BacktestBatchResult) -> Path:
        path = self._output_directory / f"{result.deterministic_run_fingerprint[:16]}.json"
        payload = json.dumps(
            {"schema_version": BACKTEST_SCHEMA_VERSION, "result": result},
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        ).encode("utf-8")
        try:
            _atomic_replace(path, payload)
        except Exception:
            self._failures += 1
            raise
        self._writes += 1
        return path

    def read_result_digest(self, deterministic_run_fingerprint: str) -> str | None:
        if not isinstance(deterministic_run_fingerprint, str) or not deterministic_run_fingerprint.strip():
            return None
        path = self._output_directory / f"{deterministic_run_fingerprint[:16]}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            result = payload.get("result", {})
            digest = result.get("result_digest")
        except Exception:
            return None
        return digest if isinstance(digest, str) and digest.strip() else None


def with_report_path(result: BacktestBatchResult, path: Path) -> BacktestBatchResult:
    return replace(result, report_path=path)


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp_name, path)


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        try:
            written = os.write(fd, view)
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError("Unable to persist deterministic backtest report.")
        view = view[written:]


def _json_default(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.name
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")
