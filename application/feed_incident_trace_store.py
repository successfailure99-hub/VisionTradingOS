"""
Durable bounded JSONL storage for live-feed incident traces.
"""

from __future__ import annotations

import json
from pathlib import Path


class BoundedJsonlTraceStore:
    def __init__(self, path: Path | str, *, max_events: int):
        self._path = Path(path)
        self._max_events = max_events

    @property
    def path(self) -> Path:
        return self._path

    def record(self, row: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rows = self._read_rows()
        rows.append(row)
        if len(rows) > self._max_events:
            rows = rows[-self._max_events :]
        text = "".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in rows)
        self._path.write_text(text, encoding="utf-8")

    def _read_rows(self) -> list[dict[str, object]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, object]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows
