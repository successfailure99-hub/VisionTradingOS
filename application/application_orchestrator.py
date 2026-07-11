"""
Application Orchestrator V1.
"""

from application.enums import ApplicationMode, OrchestratorAction, OrchestratorStatus
from application.models import OrchestratorResult
from brokers.zerodha.adapter import ZerodhaBrokerAdapter
from brokers.zerodha.enums import BrokerExecutionMode
from engines.ai_reasoning.models import AIReasoningState
from engines.market_context.models import MarketContextSnapshot, MarketContextState
from engines.order_management.models import OrderSnapshot, OrderState
from engines.position.models import PositionFill, PositionMark
from engines.risk.models import RiskSnapshot
from engines.strategy.models import StrategySnapshot
from engines.trade_journal.models import TradeJournalSnapshot


class ApplicationOrchestrator:
    """
    Serialized top-level coordinator for Vision Trading OS engines.

    Application Orchestrator V1 is dependency-injected, in-memory, and
    synchronous. It does not calculate indicators, strategy, risk, P&L, or
    journal statistics itself. It does not fetch market data, read
    credentials, authenticate, open WebSockets, persist data, run background
    tasks, render dashboards, produce voice alerts, or perform live trading.
    The default mode is ANALYSIS_ONLY. Broker submission is permitted only
    when the orchestrator is explicitly in DRY_RUN mode and the Zerodha
    adapter is also in DRY_RUN mode.
    """

    def __init__(
        self,
        event_bus,
        *,
        mode: ApplicationMode = ApplicationMode.ANALYSIS_ONLY,
        market_context_engine=None,
        ai_reasoning_engine=None,
        strategy_engine=None,
        risk_engine=None,
        order_engine=None,
        position_engine=None,
        trade_journal_engine=None,
        broker_adapter: ZerodhaBrokerAdapter | None = None,
    ):
        if not isinstance(mode, ApplicationMode):
            raise ValueError("mode must be an ApplicationMode.")
        self._event_bus = event_bus
        self._mode = mode
        self._market_context_engine = market_context_engine
        self._ai_reasoning_engine = ai_reasoning_engine
        self._strategy_engine = strategy_engine
        self._risk_engine = risk_engine
        self._order_engine = order_engine
        self._position_engine = position_engine
        self._trade_journal_engine = trade_journal_engine
        self._broker_adapter = broker_adapter
        self._last_result: OrchestratorResult | None = None
        self._history: list[OrchestratorResult] = []

    @property
    def mode(self) -> ApplicationMode:
        return self._mode

    @property
    def last_result(self) -> OrchestratorResult | None:
        return self._last_result

    @property
    def history(self) -> tuple[OrchestratorResult, ...]:
        return tuple(self._history)

    def process_market_context(self, snapshot: MarketContextSnapshot) -> OrchestratorResult:
        engine = self._require(self._market_context_engine, "market_context_engine")
        state = engine.process(snapshot)
        return self._remember(OrchestratorAction.MARKET_CONTEXT, OrchestratorStatus.COMPLETED, state, "Market context processed.")

    def process_ai_reasoning(self, context: MarketContextState) -> OrchestratorResult:
        engine = self._require(self._ai_reasoning_engine, "ai_reasoning_engine")
        state = engine.process(context)
        return self._remember(OrchestratorAction.AI_REASONING, OrchestratorStatus.COMPLETED, state, "AI reasoning processed.")

    def process_strategy(self, context: MarketContextState, reasoning: AIReasoningState) -> OrchestratorResult:
        engine = self._require(self._strategy_engine, "strategy_engine")
        snapshot = StrategySnapshot(
            symbol=context.symbol,
            timeframe=context.timeframe,
            timestamp=context.timestamp,
            ai_reasoning=reasoning,
            market_context=context,
        )
        state = engine.process(snapshot)
        return self._remember(OrchestratorAction.STRATEGY, OrchestratorStatus.COMPLETED, state, "Strategy processed.")

    def process_analysis(self, snapshot: MarketContextSnapshot) -> OrchestratorResult:
        context_result = self.process_market_context(snapshot)
        context = context_result.payload
        reasoning_result = self.process_ai_reasoning(context)
        strategy_result = self.process_strategy(context, reasoning_result.payload)
        return strategy_result

    def process_risk(self, snapshot: RiskSnapshot) -> OrchestratorResult:
        engine = self._require(self._risk_engine, "risk_engine")
        state = engine.process(snapshot)
        return self._remember(OrchestratorAction.RISK, OrchestratorStatus.COMPLETED, state, "Risk processed.")

    def create_order(self, snapshot: OrderSnapshot) -> OrchestratorResult:
        engine = self._require(self._order_engine, "order_engine")
        state = engine.create(snapshot)
        return self._remember(OrchestratorAction.ORDER_CREATED, OrchestratorStatus.COMPLETED, state, "Order created internally.")

    def submit_order_dry_run(self, order: OrderState) -> OrchestratorResult:
        if self._mode is not ApplicationMode.DRY_RUN:
            return self._remember(
                OrchestratorAction.BROKER_DRY_RUN,
                OrchestratorStatus.BLOCKED,
                None,
                "Broker submission is blocked unless orchestrator mode is DRY_RUN.",
            )
        adapter = self._require(self._broker_adapter, "broker_adapter")
        if not isinstance(adapter, ZerodhaBrokerAdapter) or adapter.mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("Zerodha submission requires an explicit DRY_RUN adapter.")
        result = adapter.place(order)
        return self._remember(OrchestratorAction.BROKER_DRY_RUN, OrchestratorStatus.COMPLETED, result, "Order submitted to DRY_RUN broker adapter.")

    def apply_position_fill(self, fill: PositionFill) -> OrchestratorResult:
        engine = self._require(self._position_engine, "position_engine")
        state = engine.process_fill(fill)
        return self._remember(OrchestratorAction.POSITION_UPDATED, OrchestratorStatus.COMPLETED, state, "Position fill processed.")

    def apply_position_mark(self, mark: PositionMark) -> OrchestratorResult:
        engine = self._require(self._position_engine, "position_engine")
        state = engine.process_mark(mark)
        return self._remember(OrchestratorAction.POSITION_UPDATED, OrchestratorStatus.COMPLETED, state, "Position mark processed.")

    def record_trade(self, snapshot: TradeJournalSnapshot) -> OrchestratorResult:
        engine = self._require(self._trade_journal_engine, "trade_journal_engine")
        record = engine.record(snapshot)
        return self._remember(OrchestratorAction.TRADE_RECORDED, OrchestratorStatus.COMPLETED, record, "Trade journal record stored.")

    def reset(self) -> None:
        self._last_result = None
        self._history.clear()

    def clear(self) -> None:
        self.reset()

    def _remember(
        self,
        action: OrchestratorAction,
        status: OrchestratorStatus,
        payload,
        message: str,
    ) -> OrchestratorResult:
        result = OrchestratorResult(
            action=action,
            status=status,
            mode=self._mode,
            payload=payload,
            message=message,
        )
        self._last_result = result
        self._history.append(result)
        return result

    @staticmethod
    def _require(value, name: str):
        if value is None:
            raise ValueError(f"{name} is required.")
        return value
