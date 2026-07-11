"""
Immutable AI Reasoning Engine V1 models.
"""

from dataclasses import dataclass
from datetime import datetime

from engines.ai_reasoning.enums import (
    AgreementSummary,
    AIMarketSummary,
    ConflictSummary,
    ReasoningConfidence,
    TradingSuitability,
)


@dataclass(frozen=True, slots=True)
class AIReasoningState:
    symbol: str
    timeframe: str
    timestamp: datetime

    market_summary: AIMarketSummary
    confidence: ReasoningConfidence
    agreement_summary: AgreementSummary
    conflict_summary: ConflictSummary
    trading_suitability: TradingSuitability
    missing_information: tuple[str, ...]
    explanation: str
