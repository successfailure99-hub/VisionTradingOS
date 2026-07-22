"""
Immutable models for TradingView Evidence Assembly Coordinator V1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from application.enums import RuntimeInstrument
from core.models.building_candle import BuildingCandle
from core.models.candle import Candle
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.adr.models import ADRSnapshot
from engines.market_context.models import MarketContextState
from engines.moving_average_context.models import MovingAverageContextSnapshot
from engines.momentum_context.models import MomentumContextSnapshot
from engines.volume_context.models import VolumeContextSnapshot
from engines.option_chain.models import OptionChainState
from engines.price_action.models import PriceActionState
from engines.tradingview_evidence.models import TradingViewEvidenceSnapshot
from engines.vwap.levels import VWAPLevels


@dataclass(frozen=True, slots=True)
class TradingViewEvidenceAssemblyInput:
    timestamp: datetime
    instrument: RuntimeInstrument
    timeframe: str
    latest_price: float | None
    latest_candle: Candle | BuildingCandle | None
    price_action: PriceActionState | None
    camarilla: CamarillaLevels | None
    cpr: CPRLevels | None
    vwap: VWAPLevels | None
    option_chain: OptionChainState | None
    market_context: MarketContextState | None
    adr: ADRSnapshot | None = None
    moving_average_context: MovingAverageContextSnapshot | None = None
    momentum_context: MomentumContextSnapshot | None = None
    volume_context: VolumeContextSnapshot | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        _validate_aware(self.timestamp, "timestamp")
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must be non-empty text")
        object.__setattr__(self, "timeframe", self.timeframe.strip())
        if self.latest_price is not None:
            if isinstance(self.latest_price, bool) or not isinstance(self.latest_price, (int, float)):
                raise TypeError("latest_price must be numeric or None")
            object.__setattr__(self, "latest_price", float(self.latest_price))
        if self.correlation_id is not None:
            if not isinstance(self.correlation_id, str):
                raise TypeError("correlation_id must be text or None")
            object.__setattr__(self, "correlation_id", self.correlation_id.strip() or None)


@dataclass(frozen=True, slots=True)
class TradingViewEvidenceAssemblySnapshot:
    enabled: bool
    assembled_count: int
    skipped_count: int
    duplicate_count: int
    last_evidence: TradingViewEvidenceSnapshot | None
    last_wait_reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool")
        for field_name in ("assembled_count", "skipped_count", "duplicate_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.last_wait_reason is not None:
            if not isinstance(self.last_wait_reason, str):
                raise TypeError("last_wait_reason must be text or None")
            object.__setattr__(self, "last_wait_reason", self.last_wait_reason.strip() or None)


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
