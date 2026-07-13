"""
Per-symbol Application Orchestrator runtime.
"""

from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from engines.ai_reasoning.ai_reasoning_engine import AIReasoningEngine
from engines.camarilla.camarilla_engine import CamarillaEngine
from engines.camarilla.levels import CamarillaLevels
from engines.candle.candle_engine import CandleEngine
from engines.cpr.cpr_engine import CPREngine
from engines.cpr.levels import CPRLevels
from engines.market_context.market_context_engine import MarketContextEngine
from engines.market_context.models import MarketContextSnapshot, MarketContextState
from engines.option_chain.models import OptionChainSnapshot, OptionChainState
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.order_management.models import OrderCommand, OrderRequest, OrderSnapshot, OrderState
from engines.order_management.order_management_engine import OrderManagementEngine
from engines.position.models import PositionFill, PositionMark, PositionState
from engines.position.position_engine import PositionEngine
from engines.price_action.price_action_engine import PriceActionEngine
from engines.risk.models import AccountRiskState, RiskDecisionState, RiskPolicy, RiskSnapshot, TradeRiskPlan
from engines.risk.risk_engine import RiskEngine
from engines.strategy.models import StrategyDecisionState, StrategySnapshot
from engines.strategy.strategy_engine import StrategyEngine
from engines.vwap.vwap_engine import VWAPEngine

from application.enums import RuntimeInstrument, RuntimeStatus
from application.models import RuntimeConfiguration, RuntimeSnapshot


class SymbolRuntime:
    """
    Owns all per-instrument engines for one supported runtime instrument.

    The runtime coordinates approved public APIs only. It keeps the latest
    public outputs needed to build downstream snapshots and exposes immutable
    dashboard-facing RuntimeSnapshot objects.
    """

    def __init__(self, event_bus, configuration: RuntimeConfiguration, instrument: RuntimeInstrument):
        if instrument not in configuration.instruments:
            raise ValueError("SymbolRuntime instrument must be configured.")
        self._event_bus = event_bus
        self._configuration = configuration
        self._instrument = instrument
        self._status = RuntimeStatus.CREATED
        self._core_instrument = Instrument.from_symbol(instrument.value)
        self._last_tick: Tick | None = None
        self._updated_at = None
        self._last_processed_history_count = 0

        self.market_context_engine = MarketContextEngine(event_bus, instrument.value, configuration.timeframe)
        self.ai_reasoning_engine = AIReasoningEngine(event_bus, instrument.value, configuration.timeframe)
        self.strategy_engine = StrategyEngine(event_bus, instrument.value, configuration.timeframe)
        self.risk_engine = RiskEngine(event_bus, instrument.value, configuration.timeframe)
        self.order_engine = OrderManagementEngine(event_bus, instrument.value, configuration.timeframe)
        self.position_engine = PositionEngine(event_bus, instrument.value, configuration.exchange, configuration.timeframe)
        self.candle_engine = CandleEngine(event_bus, TimeFrame.from_value(configuration.timeframe))
        self.vwap_engine = VWAPEngine(event_bus)
        self.cpr_engine = CPREngine(event_bus)
        self.camarilla_engine = CamarillaEngine(event_bus)
        self.price_action_engine = PriceActionEngine(event_bus, instrument.value, configuration.timeframe)
        self.option_chain_engine = OptionChainEngine(
            event_bus,
            instrument.value,
            configuration.exchange,
            configuration.option_expiry_date,
        )

    @property
    def instrument(self) -> RuntimeInstrument:
        return self._instrument

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    @property
    def cpr(self) -> CPRLevels | None:
        return self.cpr_engine.levels

    @property
    def camarilla(self) -> CamarillaLevels | None:
        return self.camarilla_engine.levels

    def start(self) -> None:
        self._status = RuntimeStatus.RUNNING

    def stop(self) -> None:
        self._status = RuntimeStatus.STOPPED

    def mark_error(self) -> None:
        self._status = RuntimeStatus.ERROR

    def process_tick(self, tick: Tick) -> RuntimeSnapshot:
        self._require_running()
        if tick.symbol is not self._core_instrument:
            raise ValueError("Tick instrument does not match SymbolRuntime.")
        self.candle_engine.on_tick(tick)
        self.vwap_engine.on_tick(tick)
        self._process_closed_candles()
        self._last_tick = tick
        self._updated_at = tick.timestamp
        return self.snapshot()

    def process_daily_ohlc(self, daily_ohlc: DailyOHLC) -> tuple[CPRLevels, CamarillaLevels]:
        self._require_running()
        cpr = self.cpr_engine.update(daily_ohlc)
        camarilla = self.camarilla_engine.update(daily_ohlc)
        return cpr, camarilla

    def warm_up_candles(
        self,
        candles: tuple[Candle, ...],
        *,
        replace: bool = False,
    ) -> tuple[Candle, ...]:
        self._require_running()
        normalized = tuple(candles)
        for candle in normalized:
            if not isinstance(candle, Candle):
                raise TypeError("warm-up candles must contain Candle values.")
            if candle.symbol != self._core_instrument.value:
                raise ValueError("Warm-up candle instrument does not match SymbolRuntime.")
            if candle.timeframe != TimeFrame.ONE_MINUTE.value:
                raise ValueError("Historical warm-up supports only one-minute candles.")

        accepted = self.candle_engine.seed_history(
            self._core_instrument,
            normalized,
            replace=replace,
        )

        if replace and accepted:
            self.price_action_engine.reset()
            for candle in self.candle_engine.get_history(self._core_instrument):
                self.price_action_engine.process(candle)
        else:
            for candle in accepted:
                self.price_action_engine.process(candle)

        self._last_processed_history_count = len(
            self.candle_engine.get_history(self._core_instrument)
        )
        if accepted:
            self._updated_at = accepted[-1].end_time
        return accepted

    def get_candle_history(self) -> tuple[Candle, ...]:
        return tuple(self.candle_engine.get_history(self._core_instrument))

    def process_option_chain(self, snapshot: OptionChainSnapshot) -> OptionChainState:
        self._require_running()
        state = self.option_chain_engine.process(snapshot)
        self._updated_at = state.timestamp
        return state

    def build_market_context(
        self,
        *,
        timestamp,
        current_price: float,
        session_high: float,
        session_low: float,
    ) -> MarketContextState:
        self._require_running()
        trading_date = timestamp.date()
        cpr = self.cpr if self.cpr is not None and self.cpr.trading_date == trading_date else None
        camarilla = (
            self.camarilla
            if self.camarilla is not None and self.camarilla.trading_date == trading_date
            else None
        )
        snapshot = MarketContextSnapshot(
            symbol=self._instrument.value,
            timeframe=self._configuration.timeframe,
            timestamp=timestamp,
            current_price=current_price,
            session_high=session_high,
            session_low=session_low,
            price_action=self.price_action_engine.state,
            option_chain=self.option_chain_engine.state,
            vwap=self.vwap_engine.get_latest(self._core_instrument),
            cpr=cpr,
            camarilla=camarilla,
        )
        state = self.market_context_engine.process(snapshot)
        self._updated_at = state.timestamp
        return state

    def run_ai_reasoning(self, context: MarketContextState | None = None):
        self._require_running()
        state = self.ai_reasoning_engine.process(context or self.market_context_engine.state)
        self._updated_at = state.timestamp
        return state

    def run_strategy(self, context: MarketContextState | None = None, reasoning=None) -> StrategyDecisionState:
        self._require_running()
        market_context = context or self.market_context_engine.state
        ai_reasoning = reasoning or self.ai_reasoning_engine.state
        if market_context is None or ai_reasoning is None:
            raise ValueError("Market context and AI reasoning are required for strategy.")
        snapshot = StrategySnapshot(
            symbol=self._instrument.value,
            timeframe=self._configuration.timeframe,
            timestamp=market_context.timestamp,
            ai_reasoning=ai_reasoning,
            market_context=market_context,
        )
        state = self.strategy_engine.process(snapshot)
        self._updated_at = state.timestamp
        return state

    def run_risk(
        self,
        *,
        policy: RiskPolicy,
        account: AccountRiskState,
        trade_plan: TradeRiskPlan,
    ) -> RiskDecisionState:
        self._require_running()
        strategy = self.strategy_engine.state
        if strategy is None:
            raise ValueError("Strategy state is required for risk.")
        snapshot = RiskSnapshot(
            symbol=self._instrument.value,
            timeframe=self._configuration.timeframe,
            timestamp=strategy.timestamp,
            strategy=strategy,
            policy=policy,
            account=account,
            trade_plan=trade_plan,
        )
        state = self.risk_engine.process(snapshot)
        self._updated_at = state.timestamp
        return state

    def create_order(self, request: OrderRequest) -> OrderState:
        self._require_running()
        risk = self.risk_engine.state
        if risk is None:
            raise ValueError("Risk state is required for order creation.")
        snapshot = OrderSnapshot(
            symbol=self._instrument.value,
            timeframe=self._configuration.timeframe,
            timestamp=request.timestamp,
            risk=risk,
            request=request,
        )
        state = self.order_engine.create(snapshot)
        self._updated_at = state.updated_at
        return state

    def apply_order_command(self, command: OrderCommand) -> OrderState:
        self._require_running()
        state = self.order_engine.apply(command)
        self._updated_at = state.updated_at
        return state

    def apply_position_fill(self, fill: PositionFill) -> PositionState:
        self._require_running()
        state = self.position_engine.process_fill(fill)
        self._updated_at = state.updated_at
        return state

    def apply_position_mark(self, mark: PositionMark) -> PositionState:
        self._require_running()
        state = self.position_engine.process_mark(mark)
        self._updated_at = state.updated_at
        return state

    def reset(self) -> None:
        self.candle_engine.clear()
        self.vwap_engine.clear()
        self.cpr_engine.reset()
        self.camarilla_engine.reset()
        self.price_action_engine.reset()
        self.option_chain_engine.reset()
        self.market_context_engine.reset()
        self.ai_reasoning_engine.reset()
        self.strategy_engine.reset()
        self.risk_engine.reset()
        self.order_engine.reset()
        self.position_engine.reset()
        self._last_tick = None
        self._updated_at = None
        self._last_processed_history_count = 0
        self._status = RuntimeStatus.CREATED

    def snapshot(self, latest_journal_record=None) -> RuntimeSnapshot:
        latest_candle = self.candle_engine.get_current(self._core_instrument)
        if latest_candle is None:
            history = self.candle_engine.get_history(self._core_instrument)
            latest_candle = history[-1] if history else None
        return RuntimeSnapshot(
            symbol=self._instrument,
            timeframe=self._configuration.timeframe,
            status=self._status,
            latest_tick=self._last_tick,
            latest_candle=latest_candle,
            vwap=self.vwap_engine.get_latest(self._core_instrument),
            cpr=self.cpr,
            camarilla=self.camarilla,
            price_action=self.price_action_engine.state,
            option_chain=self.option_chain_engine.state,
            market_context=self.market_context_engine.state,
            ai_reasoning=self.ai_reasoning_engine.state,
            strategy=self.strategy_engine.state,
            risk=self.risk_engine.state,
            latest_order=self.order_engine.latest_order,
            position=self.position_engine.state,
            latest_journal_record=latest_journal_record,
            updated_at=self._updated_at,
        )

    def _process_closed_candles(self) -> None:
        history = self.candle_engine.get_history(self._core_instrument)
        for candle in history[self._last_processed_history_count :]:
            self.price_action_engine.process(candle)
        self._last_processed_history_count = len(history)

    def _require_running(self) -> None:
        if self._status is not RuntimeStatus.RUNNING:
            raise RuntimeError("SymbolRuntime processing requires RUNNING status.")
