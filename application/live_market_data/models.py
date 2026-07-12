"""
Immutable live market-data runtime models.
"""

from dataclasses import dataclass
from datetime import datetime

from application.live_market_data.enums import LiveMarketDataRuntimeStatus
from application.models import RuntimeSnapshot
from brokers.zerodha.market_data import ZerodhaWebSocketSnapshot
from core.enums.instrument import Instrument


def _require_aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class LiveMarketDataRuntimeSnapshot:
    status: LiveMarketDataRuntimeStatus
    ready: bool
    running: bool
    configured_instruments: tuple[Instrument, ...]
    configured_tokens: tuple[int, ...]
    websocket: ZerodhaWebSocketSnapshot | None
    start_count: int
    stop_count: int
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LiveMarketDataRuntimeStatus):
            raise TypeError("status must be LiveMarketDataRuntimeStatus")
        if self.running != (self.status is LiveMarketDataRuntimeStatus.RUNNING):
            raise ValueError("running flag must agree with status")
        if self.ready != (self.status in {
            LiveMarketDataRuntimeStatus.READY,
            LiveMarketDataRuntimeStatus.STARTING,
            LiveMarketDataRuntimeStatus.RUNNING,
            LiveMarketDataRuntimeStatus.STOPPING,
        }):
            raise ValueError("ready flag must agree with status")
        object.__setattr__(self, "configured_instruments", tuple(self.configured_instruments))
        object.__setattr__(self, "configured_tokens", tuple(self.configured_tokens))
        for name in ("start_count", "stop_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        _require_aware(self.last_started_at, "last_started_at")
        _require_aware(self.last_stopped_at, "last_stopped_at")


@dataclass(frozen=True, slots=True)
class LiveMarketDataDeliverySnapshot:
    symbol: Instrument
    accepted: bool
    runtime_snapshot: RuntimeSnapshot | None
    error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, Instrument):
            raise TypeError("symbol must be Instrument")
        if self.accepted and self.runtime_snapshot is None:
            raise ValueError("accepted delivery requires a runtime_snapshot")
        if not self.accepted and not self.error:
            raise ValueError("failed delivery requires an error")
