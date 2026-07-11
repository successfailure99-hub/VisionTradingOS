"""
Immutable Market Context Engine V1 input and output models.
"""

from dataclasses import dataclass
from datetime import datetime

from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context.enums import (
    AgreementState,
    CamarillaZone,
    ContextStrength,
    CPRPosition,
    EvidenceDirection,
    MarketBias,
    MarketPhase,
    VWAPPosition,
)
from engines.option_chain.models import OptionChainState
from engines.price_action.models import PriceActionState
from engines.vwap.levels import VWAPLevels


@dataclass(frozen=True, slots=True)
class ContextEvidence:
    source: str
    direction: EvidenceDirection
    detail: str


@dataclass(frozen=True, slots=True)
class MarketContextSnapshot:
    symbol: str
    timeframe: str
    timestamp: datetime

    current_price: float
    session_high: float
    session_low: float

    price_action: PriceActionState | None
    option_chain: OptionChainState | None
    vwap: VWAPLevels | None
    cpr: CPRLevels | None
    camarilla: CamarillaLevels | None

    def __post_init__(self) -> None:
        if isinstance(self.symbol, str):
            object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if isinstance(self.timeframe, str):
            object.__setattr__(self, "timeframe", self.timeframe.strip())


@dataclass(frozen=True, slots=True)
class MarketContextState:
    symbol: str
    timeframe: str
    timestamp: datetime

    current_price: float
    session_high: float
    session_low: float

    market_bias: MarketBias
    market_phase: MarketPhase
    agreement: AgreementState
    context_strength: ContextStrength

    price_action_direction: EvidenceDirection
    option_chain_direction: EvidenceDirection

    vwap_position: VWAPPosition
    cpr_position: CPRPosition
    virgin_cpr: bool | None
    camarilla_zone: CamarillaZone

    bullish_evidence_count: int
    bearish_evidence_count: int
    neutral_evidence_count: int
    mixed_evidence_count: int
    available_source_count: int

    evidence: tuple[ContextEvidence, ...]
    missing_sources: tuple[str, ...]