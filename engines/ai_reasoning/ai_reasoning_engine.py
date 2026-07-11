"""
AI Reasoning Engine V1.
"""

from datetime import datetime

from core.base_engine import BaseEngine
from core.events import AI_DECISION_READY
from engines.ai_reasoning.calculator import AIReasoningCalculator
from engines.ai_reasoning.models import AIReasoningState
from engines.market_context.models import MarketContextState


class AIReasoningEngine(BaseEngine):
    """
    Deterministic reasoning engine for one symbol and timeframe.

    AI Reasoning Engine V1 consumes only MarketContextState from the
    upstream Market Context Engine. It performs rule-based reasoning
    only: no LLM calls, network access, broker access, indicator
    calculation, strategy logic, persistence, order generation, or trade
    execution. Calls are assumed serialized and single-threaded by
    upstream orchestration.
    """

    def __init__(self, event_bus, symbol: str, timeframe: str):
        super().__init__(event_bus)
        self._symbol = self._normalize_symbol(symbol)
        self._timeframe = self._normalize_timeframe(timeframe)
        self._context: MarketContextState | None = None
        self._state: AIReasoningState | None = None
        self._timestamp_is_aware: bool | None = None

    @property
    def context(self) -> MarketContextState | None:
        return self._context

    @property
    def state(self) -> AIReasoningState | None:
        return self._state

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    def update(self, context: MarketContextState) -> AIReasoningState:
        canonical = self._canonicalize_context(context)

        if self._context is not None:
            if canonical.timestamp < self._context.timestamp:
                raise ValueError(
                    "Stale MarketContextState received: "
                    f"{canonical.timestamp.isoformat()} < {self._context.timestamp.isoformat()}"
                )
            if canonical == self._context:
                return self._state

        state = AIReasoningCalculator.calculate(canonical)
        self._context = canonical
        self._state = state
        self._data = state
        self._event_bus.publish(AI_DECISION_READY, state)
        return state

    def process(self, context: MarketContextState) -> AIReasoningState:
        """
        Alias for update().
        """

        return self.update(context)

    def reset(self) -> None:
        super().clear()
        self._context = None
        self._state = None
        self._timestamp_is_aware = None

    def clear(self) -> None:
        self.reset()

    def _canonicalize_context(self, context: MarketContextState) -> MarketContextState:
        if not isinstance(context, MarketContextState):
            raise TypeError("AIReasoningEngine expects a MarketContextState object.")

        symbol = self._normalize_symbol(context.symbol)
        timeframe = self._normalize_timeframe(context.timeframe)
        if symbol != self._symbol:
            raise ValueError("MarketContextState symbol does not match engine context.")
        if timeframe != self._timeframe:
            raise ValueError("MarketContextState timeframe does not match engine context.")
        if not isinstance(context.timestamp, datetime):
            raise ValueError("MarketContextState timestamp must be a datetime.")

        timestamp_is_aware = context.timestamp.tzinfo is not None
        if self._timestamp_is_aware is not None and timestamp_is_aware != self._timestamp_is_aware:
            raise ValueError("MarketContextState timestamp timezone-awareness mode changed.")

        canonical = MarketContextState(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=context.timestamp,
            current_price=context.current_price,
            session_high=context.session_high,
            session_low=context.session_low,
            market_bias=context.market_bias,
            market_phase=context.market_phase,
            agreement=context.agreement,
            context_strength=context.context_strength,
            price_action_direction=context.price_action_direction,
            option_chain_direction=context.option_chain_direction,
            vwap_position=context.vwap_position,
            cpr_position=context.cpr_position,
            virgin_cpr=context.virgin_cpr,
            camarilla_zone=context.camarilla_zone,
            bullish_evidence_count=context.bullish_evidence_count,
            bearish_evidence_count=context.bearish_evidence_count,
            neutral_evidence_count=context.neutral_evidence_count,
            mixed_evidence_count=context.mixed_evidence_count,
            available_source_count=context.available_source_count,
            evidence=context.evidence,
            missing_sources=context.missing_sources,
        )

        if self._timestamp_is_aware is None:
            self._timestamp_is_aware = timestamp_is_aware
        return canonical

    def _normalize_symbol(self, symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("AIReasoningEngine symbol must be a string.")
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("AIReasoningEngine symbol cannot be empty.")
        return normalized

    def _normalize_timeframe(self, timeframe: str) -> str:
        if not isinstance(timeframe, str):
            raise ValueError("AIReasoningEngine timeframe must be a string.")
        normalized = timeframe.strip()
        if not normalized:
            raise ValueError("AIReasoningEngine timeframe cannot be empty.")
        return normalized
