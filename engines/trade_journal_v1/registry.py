"""
In-memory Trade Journal V1 registry.
"""

from threading import RLock

from engines.trade_journal_v1.configuration import TradeJournalV1Configuration
from engines.trade_journal_v1.enums import TradeRecordStatus
from engines.trade_journal_v1.models import TradeJournalEntry, TradeJournalRecordResult


class TradeJournalRegistry:
    def __init__(self, configuration: TradeJournalV1Configuration | None = None):
        self._configuration = configuration or TradeJournalV1Configuration()
        self._entries: dict[str, TradeJournalEntry] = {}
        self._order: tuple[str, ...] = ()
        self._lock = RLock()

    def add(self, entry: TradeJournalEntry) -> TradeJournalRecordResult:
        if not isinstance(entry, TradeJournalEntry):
            raise TypeError("entry must be TradeJournalEntry")
        with self._lock:
            existing = self._entries.get(entry.trade_id)
            if existing is not None:
                if existing != entry:
                    return TradeJournalRecordResult(
                        TradeRecordStatus.REJECTED,
                        existing,
                        "Duplicate trade identity has different content.",
                    )
                return TradeJournalRecordResult(
                    TradeRecordStatus.DUPLICATE,
                    existing,
                    "Duplicate trade suppressed.",
                )
            self._entries[entry.trade_id] = entry
            self._order = self._order + (entry.trade_id,)
            return TradeJournalRecordResult(
                TradeRecordStatus.RECORDED,
                entry,
                "Trade recorded.",
            )

    def get(self, trade_id: str) -> TradeJournalEntry:
        if not isinstance(trade_id, str) or not trade_id.strip():
            raise ValueError("trade_id must be non-empty")
        with self._lock:
            try:
                return self._entries[trade_id]
            except KeyError as exc:
                raise ValueError("trade is not registered") from exc

    def entries(self) -> tuple[TradeJournalEntry, ...]:
        with self._lock:
            return tuple(self._entries[trade_id] for trade_id in self._order)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._order = ()
