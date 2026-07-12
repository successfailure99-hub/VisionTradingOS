"""
Per-symbol Application Orchestrator runtime.
"""

from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from engines.ai_reasoning.ai_reasoning_engine import AIReasoningEngine
from engines.camarilla.calculator import CamarillaCalculator
from engines.camarilla.levels import CamarillaLevels
from engines.candle.candle_engine import CandleEngine
from engines.cpr.calculator import CPRCalculator
from engines.cpr.levels import CPRLevels
from engines.market_context.market_context_engine import MarketContextEngine
from engines.market_context.models import MarketContextSnapshot, MarketContextState
from engines.option_chain.models import OptionChainSnapshot, OptionChainState
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.order_management.models import OrderCommand, OrderSnapshot, OrderState
from engines.order_management.order_management_engine import OrderManagementEngine
from engines.position.models import PositionFill, PositionMark, PositionState
from engines.position.position_engine import PositionEngine
from engines.price_action.price_action_engine import PriceActionEngine
from engines.risk.models import RiskDecisionState, RiskSnapshot
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
        self._cpr: CPRLevels | None = None
        self._camarilla: CamarillaLevels | None = None
        self._last_processed_history_count = 0

        self.market_context_engine = MarketContextEngine(event_bus, instrument.value, configuration.timeframe)
        self.ai_reasoning_engine = AIReasoningEngine(event_bus, instrument.value, configuration.timeframe)
        self.strategy_engine = StrategyEngine(event_bus, instrument.value, configuration.timeframe)
        self.risk_engine = RiskEngine(event_bus, instrument.value, configuration.timeframe)
        self.order_engine = OrderManagementEngine(event_bus, instrument.value, configuration.timeframe)
        self.position_engine = PositionEngine(event_bus, instrument.value, configuration.exchange, configuration.timeframe)
        self.candle_engine = CandleEngine(event_bus, TimeFrame.ONE_MINUTE)
        self.vwap_engine = VWAPEngine(event_bus)
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
        return self._cpr

    @property
    def camarilla(self) -> CamarillaLevels | None:
        return self._camarilla

    def start(self) -> None:
        self._status = RuntimeStatus.RUNNING

    def stop(self) -> None:
        self._status = RuntimeStatus.STOPPED

    def mark_error(self) -> None:
        self._status = RuntimeStatus.ERROR

    def process_tick(self, tick: Tick) -> dict[str, object]:
        self._require_running()
        if tick.symbol is not self._core_instrument:
            raise ValueError("Tick instrument does not match SymbolRuntime.")
        candle = self.candle_engine.on_tick(tick)
        vwap = self.vwap_engine.on_tick(tick)
        self._process_closed_candles()
        self._last_tick = tick
        return {"candle": candle, "vwap": vwap, "price_action": self.price_action_engine.state}

    def process_daily_ohlc(self, daily_ohlc: DailyOHLC) -> tuple[CPRLevels, CamarillaLevels]:
        self._require_running()
        self._cpr = CPRCalculator.calculate(daily_ohlc)
        self._camarilla = CamarillaCalculator.calculate(daily_ohlc)
        return self._cpr, self._camarilla

    def process_option_chain(self, snapshot: OptionChainSnapshot) -> OptionChainState:
        self._require_running()
        return self.option_chain_engine.process(snapshot)

    def build_market_context(self) -> MarketContextState:
        self._require_running()
        if self._last_tick is None:
            raise ValueError("Cannot build market context before a tick is accepted.")
        price = self._last_tick.last_price
        trading_date = self._last_tick.timestamp.date()
        cpr = self._cpr if self._cpr is not None and self._cpr.trading_date == trading_date else None
        camarilla = (
            self._camarilla
            if self._camarilla is not None and self._camarilla.trading_date == trading_date
            else None
        )
        snapshot = MarketContextSnapshot(
            symbol=self._instrument.value,
            timeframe=self._configuration.timeframe,
            timestamp=self._last_tick.timestamp,
            current_price=price,
            session_high=price,
            session_low=price,
            price_action=self.price_action_engine.state,
            option_chain=self.option_chain_engine.state,
            vwap=self.vwap_engine.get_latest(self._core_instrument),
            cpr=cpr,
            camarilla=camarilla,
        )
        return self.market_context_engine.process(snapshot)

    def run_ai_reasoning(self, context: MarketContextState | None = None):
        self._require_running()
        return self.ai_reasoning_engine.process(context or self.market_context_engine.state)

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
        return self.strategy_engine.process(snapshot)

    def run_risk(self, snapshot: RiskSnapshot) -> RiskDecisionState:
        self._require_running()
        return self.risk_engine.process(snapshot)

    def create_order(self, snapshot: OrderSnapshot) -> OrderState:
        self._require_running()
        return self.order_engine.create(snapshot)

    def apply_order_command(self, command: OrderCommand) -> OrderState:
        self._require_running()
        return self.order_engine.apply(command)

    def apply_position_fill(self, fill: PositionFill) -> PositionState:
        self._require_running()
        return self.position_engine.process_fill(fill)

    def apply_position_mark(self, mark: PositionMark) -> PositionState:
        self._require_running()
        return self.position_engine.process_mark(mark)

    def reset(self) -> None:
        self.candle_engine.clear()
        self.vwap_engine.clear()
        self.price_action_engine.reset()
        self.option_chain_engine.reset()
        self.market_context_engine.reset()
        self.ai_reasoning_engine.reset()
        self.strategy_engine.reset()
        self.risk_engine.reset()
        self.order_engine.reset()
        self.position_engine.reset()
        self._last_tick = None
        self._cpr = None
        self._camarilla = None
        self._last_processed_history_count = 0
        self._status = RuntimeStatus.CREATED

    def snapshot(self) -> RuntimeSnapshot:
        latest_order = self.order_engine.latest_order
        return RuntimeSnapshot(
            instrument=self._instrument,
            status=self._status,
            exchange=self._configuration.exchange,
            timeframe=self._configuration.timeframe,
            last_tick_timestamp=self._last_tick.timestamp if self._last_tick is not None else None,
            latest_price=self._last_tick.last_price if self._last_tick is not None else None,
            candle_ready=self.candle_engine.is_ready(),
            vwap_ready=self.vwap_engine.get_latest(self._core_instrument) is not None,
            cpr_ready=self._cpr is not None,
            camarilla_ready=self._camarilla is not None,
            price_action_ready=self.price_action_engine.state is not None,
            option_chain_ready=self.option_chain_engine.state is not None,
            market_context_ready=self.market_context_engine.state is not None,
            ai_reasoning_ready=self.ai_reasoning_engine.state is not None,
            strategy_ready=self.strategy_engine.state is not None,
            risk_ready=self.risk_engine.state is not None,
            latest_order_ready=latest_order is not None,
            position_ready=self.position_engine.state is not None,
        )

    def _process_closed_candles(self) -> None:
        history = self.candle_engine.get_history(self._core_instrument)
        for candle in history[self._last_processed_history_count :]:
            self.price_action_engine.process(candle)
        self._last_processed_history_count = len(history)

    def _require_running(self) -> None:
        if self._status is not RuntimeStatus.RUNNING:
            raise RuntimeError("SymbolRuntime processing requires RUNNING status.")
