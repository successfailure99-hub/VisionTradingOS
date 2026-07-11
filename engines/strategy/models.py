"""
Immutable Strategy Engine V1 models.
"""

from dataclasses import dataclass
from datetime import datetime

from engines.ai_reasoning.enums import ReasoningConfidence, TradingSuitability
from engines.ai_reasoning.models import AIReasoningState
from engines.market_context.enums import MarketBias, MarketPhase
from engines.market_context.models import MarketContextState
from engines.strategy.enums import (
    BlockReason,
    EntryReference,
    SetupQuality,
    StopReference,
    StrategyDecision,
    TargetReference,
    TradeDirection,
)


@dataclass(frozen=True, slots=True)
class StrategySnapshot:
    symbol: str
    timeframe: str
    timestamp: datetime
    ai_reasoning: AIReasoningState
    market_context: MarketContextState

    def __post_init__(self) -> None:
        if isinstance(self.symbol, str):
            object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if isinstance(self.timeframe, str):
            object.__setattr__(self, "timeframe", self.timeframe.strip())


@dataclass(frozen=True, slots=True)
class StrategyDecisionState:
    symbol: str
    timeframe: str
    timestamp: datetime

    decision: StrategyDecision
    direction: TradeDirection
    setup_quality: SetupQuality

    entry_reference: EntryReference
    stop_reference: StopReference
    target_reference: TargetReference

    block_reason: BlockReason

    market_bias: MarketBias
    market_phase: MarketPhase
    confidence: ReasoningConfidence
    trading_suitability: TradingSuitability

    rationale: tuple[str, ...]
