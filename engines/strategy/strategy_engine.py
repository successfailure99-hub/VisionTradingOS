"""
Strategy Engine V1.
"""

from datetime import datetime

from core.base_engine import BaseEngine
from core.events import STRATEGY_DECISION_READY
from engines.ai_reasoning.enums import AgreementSummary, AIMarketSummary, ReasoningConfidence
from engines.ai_reasoning.models import AIReasoningState
from engines.market_context.enums import AgreementState, ContextStrength, MarketBias
from engines.market_context.models import MarketContextState
from engines.strategy.calculator import StrategyCalculator
from engines.strategy.models import StrategyDecisionState, StrategySnapshot


class StrategyEngine(BaseEngine):
    """
    Deterministic strategy-decision engine for one symbol and timeframe.

    Strategy Engine V1 consumes AIReasoningState and MarketContextState
    only. It produces objective setup eligibility and reference
    categories for later Risk Engine processing. It does not place
    orders, select contracts, size positions, calculate monetary risk,
    fetch data, call models, use networking, or execute trades.
    """

    def __init__(self, event_bus, symbol: str, timeframe: str):
        super().__init__(event_bus)
        self._symbol = self._normalize_symbol(symbol)
        self._timeframe = self._normalize_timeframe(timeframe)
        self._snapshot: StrategySnapshot | None = None
        self._state: StrategyDecisionState | None = None
        self._timestamp_is_aware: bool | None = None

    @property
    def snapshot(self) -> StrategySnapshot | None:
        return self._snapshot

    @property
    def state(self) -> StrategyDecisionState | None:
        return self._state

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    def update(self, snapshot: StrategySnapshot) -> StrategyDecisionState:
        canonical = self._canonicalize_snapshot(snapshot)

        if self._snapshot is not None:
            if canonical.timestamp < self._snapshot.timestamp:
                raise ValueError(
                    "Stale StrategySnapshot received: "
                    f"{canonical.timestamp.isoformat()} < {self._snapshot.timestamp.isoformat()}"
                )
            if canonical == self._snapshot:
                return self._state

        state = StrategyCalculator.calculate(canonical)
        self._snapshot = canonical
        self._state = state
        self._data = state
        self._event_bus.publish(STRATEGY_DECISION_READY, state)
        return state

    def process(self, snapshot: StrategySnapshot) -> StrategyDecisionState:
        """
        Alias for update().
        """

        return self.update(snapshot)

    def reset(self) -> None:
        super().clear()
        self._snapshot = None
        self._state = None
        self._timestamp_is_aware = None

    def clear(self) -> None:
        self.reset()

    def _canonicalize_snapshot(self, snapshot: StrategySnapshot) -> StrategySnapshot:
        if not isinstance(snapshot, StrategySnapshot):
            raise TypeError("StrategyEngine expects a StrategySnapshot object.")

        symbol = self._normalize_symbol(snapshot.symbol)
        timeframe = self._normalize_timeframe(snapshot.timeframe)
        if symbol != self._symbol:
            raise ValueError("StrategySnapshot symbol does not match engine context.")
        if timeframe != self._timeframe:
            raise ValueError("StrategySnapshot timeframe does not match engine context.")
        if not isinstance(snapshot.timestamp, datetime):
            raise ValueError("StrategySnapshot timestamp must be a datetime.")

        timestamp_is_aware = snapshot.timestamp.tzinfo is not None
        if self._timestamp_is_aware is not None and timestamp_is_aware != self._timestamp_is_aware:
            raise ValueError("StrategySnapshot timestamp timezone-awareness mode changed.")

        self._validate_ai_reasoning(snapshot.ai_reasoning, symbol, timeframe, snapshot.timestamp)
        self._validate_market_context(snapshot.market_context, symbol, timeframe, snapshot.timestamp)
        self._validate_cross_state_consistency(snapshot.ai_reasoning, snapshot.market_context)

        canonical = StrategySnapshot(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=snapshot.timestamp,
            ai_reasoning=snapshot.ai_reasoning,
            market_context=snapshot.market_context,
        )
        if self._timestamp_is_aware is None:
            self._timestamp_is_aware = timestamp_is_aware
        return canonical

    def _validate_ai_reasoning(
        self,
        state: AIReasoningState,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
    ) -> None:
        if not isinstance(state, AIReasoningState):
            raise ValueError("ai_reasoning must be an AIReasoningState.")
        if self._normalize_symbol(state.symbol) != symbol:
            raise ValueError("AIReasoningState symbol does not match strategy context.")
        if self._normalize_timeframe(state.timeframe) != timeframe:
            raise ValueError("AIReasoningState timeframe does not match strategy context.")
        if state.timestamp != timestamp:
            raise ValueError("AIReasoningState timestamp must match StrategySnapshot timestamp.")

    def _validate_market_context(
        self,
        state: MarketContextState,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
    ) -> None:
        if not isinstance(state, MarketContextState):
            raise ValueError("market_context must be a MarketContextState.")
        if self._normalize_symbol(state.symbol) != symbol:
            raise ValueError("MarketContextState symbol does not match strategy context.")
        if self._normalize_timeframe(state.timeframe) != timeframe:
            raise ValueError("MarketContextState timeframe does not match strategy context.")
        if state.timestamp != timestamp:
            raise ValueError("MarketContextState timestamp must match StrategySnapshot timestamp.")

    def _validate_cross_state_consistency(
        self,
        ai: AIReasoningState,
        context: MarketContextState,
    ) -> None:
        expected_summary = {
            MarketBias.BULLISH: AIMarketSummary.BULLISH,
            MarketBias.BEARISH: AIMarketSummary.BEARISH,
            MarketBias.NEUTRAL: AIMarketSummary.NEUTRAL,
            MarketBias.MIXED: AIMarketSummary.MIXED,
            MarketBias.UNKNOWN: AIMarketSummary.INSUFFICIENT,
        }[context.market_bias]
        if ai.market_summary is not expected_summary:
            raise ValueError("AI market summary does not match Market Context bias.")

        expected_confidence = {
            ContextStrength.STRONG: ReasoningConfidence.HIGH,
            ContextStrength.MODERATE: ReasoningConfidence.MEDIUM,
            ContextStrength.WEAK: ReasoningConfidence.LOW,
            ContextStrength.INSUFFICIENT: ReasoningConfidence.INSUFFICIENT,
        }[context.context_strength]
        if ai.confidence is not expected_confidence:
            raise ValueError("AI confidence does not match Market Context strength.")

        expected_agreement = {
            AgreementState.ALIGNED: AgreementSummary.ALIGNED,
            AgreementState.CONFLICTED: AgreementSummary.CONFLICTED,
            AgreementState.PARTIAL: AgreementSummary.PARTIAL,
            AgreementState.INSUFFICIENT: AgreementSummary.INSUFFICIENT,
        }[context.agreement]
        if ai.agreement_summary is not expected_agreement:
            raise ValueError("AI agreement does not match Market Context agreement.")

        if ai.missing_information != context.missing_sources:
            raise ValueError("AI missing information does not match Market Context missing sources.")

    def _normalize_symbol(self, symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("StrategyEngine symbol must be a string.")
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("StrategyEngine symbol cannot be empty.")
        return normalized

    def _normalize_timeframe(self, timeframe: str) -> str:
        if not isinstance(timeframe, str):
            raise ValueError("StrategyEngine timeframe must be a string.")
        normalized = timeframe.strip()
        if not normalized:
            raise ValueError("StrategyEngine timeframe cannot be empty.")
        return normalized
