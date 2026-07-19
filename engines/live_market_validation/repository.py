from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path


SCHEMA_VERSION = 1


class LiveValidationRepository:
    def __init__(self, output_dir: Path | str):
        self._output_dir = Path(output_dir)
        self._finding_writes = 0
        self._report_writes = 0
        self._failures = 0

    @property
    def finding_writes(self) -> int:
        return self._finding_writes

    @property
    def report_writes(self) -> int:
        return self._report_writes

    @property
    def failures(self) -> int:
        return self._failures

    def append_finding(self, finding) -> None:
        payload = self._json_line({"schema_version": SCHEMA_VERSION, "finding": finding})
        path = self._output_dir / "findings.jsonl"
        try:
            _append_complete(path, payload)
        except Exception:
            self._failures += 1
            raise
        self._finding_writes += 1

    def write_report(self, report) -> Path:
        path = self._output_dir / f"{report.session_id}.json"
        payload = self._json_bytes({"schema_version": SCHEMA_VERSION, "report": report})
        try:
            _atomic_replace(path, payload)
        except Exception:
            self._failures += 1
            raise
        self._report_writes += 1
        return path

    def load_report(self, path: Path | str) -> dict[str, object]:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            self._failures += 1
            raise ValueError("Malformed live validation report.") from exc
        if payload.get("schema_version") != SCHEMA_VERSION:
            self._failures += 1
            raise ValueError("Unsupported live validation report schema.")
        return payload

    def reset(self, *, clear_persistent_data: bool = False) -> None:
        if clear_persistent_data and self._output_dir.exists():
            for path in self._output_dir.glob("*"):
                if path.is_file():
                    path.unlink()

    def _json_line(self, payload: dict[str, object]) -> bytes:
        return self._json_bytes(payload) + b"\n"

    def _json_bytes(self, payload: dict[str, object]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")


def _json_default(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _append_complete(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


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
            raise OSError("Unable to persist live validation record.")
        view = view[written:]

