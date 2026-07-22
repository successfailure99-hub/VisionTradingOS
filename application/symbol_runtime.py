"""
Per-symbol Application Orchestrator runtime.
"""

from core.enums.instrument import Instrument
from core.enums.exchange import Exchange
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from engines.adr.engine import ADREngine
from engines.ai_reasoning.ai_reasoning_engine import AIReasoningEngine
from engines.ai_confidence_calibration.engine import AIConfidenceCalibrationEngine
from engines.ai_confidence_calibration.models import ConfidenceCalibrationRequest
from engines.camarilla.camarilla_engine import CamarillaEngine
from engines.camarilla.levels import CamarillaLevels
from engines.candle.candle_engine import CandleEngine
from engines.cpr.cpr_engine import CPREngine
from engines.cpr.levels import CPRLevels
from engines.market_context.market_context_engine import MarketContextEngine
from engines.market_context.models import MarketContextSnapshot, MarketContextState
from engines.moving_average_context.engine import MovingAverageContextEngine
from engines.moving_average_context.models import MovingAverageContextProfile
from engines.momentum_context.engine import MomentumContextEngine
from engines.momentum_context.models import MomentumContextProfile
from engines.option_chain.models import OptionChainSnapshot, OptionChainState
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.order_management.enums import ProductType
from engines.order_management.models import OrderCommand, OrderRequest, OrderSnapshot, OrderState
from engines.order_management.order_management_engine import OrderManagementEngine
from engines.paper_execution_coordinator.engine import PaperExecutionCoordinator
from engines.paper_execution_coordinator.models import PaperExecutionReceipt, PaperExecutionRequest
from engines.paper_trading.engine import PaperTradingEngine
from engines.position.models import PositionFill, PositionMark, PositionState
from engines.position.position_engine import PositionEngine
from engines.execution_reconciliation.engine import ExecutionReconciliationEngine
from engines.execution_reconciliation.models import ExecutionReconciliationRequest, ExecutionReconciliationReport
from engines.shadow_trading_session.engine import ShadowTradingSessionEngine
from engines.shadow_trading_session.models import ShadowTradingSessionRequest, ShadowTradingSessionSummary
from engines.price_action.price_action_engine import PriceActionEngine
from engines.risk.models import AccountRiskState, RiskDecisionState, RiskPolicy, RiskSnapshot, TradeRiskPlan
from engines.risk.risk_engine import RiskEngine
from engines.risk.trade_plan_engine import RiskTradePlanEngine
from engines.strategy.models import StrategyDecisionState, StrategySnapshot
from engines.strategy.strategy_engine import StrategyEngine
from engines.trade_decision_authorization.engine import TradeDecisionAuthorizationEngine
from engines.trade_decision_authorization.models import TradeAuthorizationRequest
from engines.trade_execution_policy.engine import TradeExecutionPolicyEngine
from engines.trade_execution_policy.enums import ExecutionMode, ExecutionPlanStatus
from engines.trade_execution_policy.models import ExecutionRequest, TradeExecutionPlan
from engines.tradingview_evidence.engine import TradingViewEvidenceMappingEngine
from engines.tradingview_evidence.models import TradingViewEvidenceRequest
from engines.vwap.vwap_engine import VWAPEngine

from application.enums import RuntimeInstrument, RuntimeStatus
from application.models import RuntimeConfiguration, RuntimeSnapshot, RuntimeVWAPSource
from application.tradingview_evidence_assembly import (
    TradingViewEvidenceAssemblyCoordinator,
    TradingViewEvidenceAssemblyInput,
)


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
        self._timeframes = tuple(TimeFrame.from_value(value) for value in configuration.timeframes)
        self._primary_timeframe = self._timeframes[0]
        self._last_tick: Tick | None = None
        self._updated_at = None
        self._daily_ohlc_history: tuple[DailyOHLC, ...] = ()
        self._last_processed_history_counts = {timeframe: 0 for timeframe in self._timeframes}
        self._vwap_source_type = "-"
        self._vwap_source_exchange = "-"
        self._vwap_source_trading_symbol = "-"
        self._vwap_source_token = 1
        self._vwap_source_expiry = None
        self._vwap_source_price = None
        self._vwap_unavailable_reason = None
        self._vwap_source_state = "Unavailable"
        self._vwap_source_message = "No valid VWAP source"
        self._vwap_subscription_active = False
        self._vwap_historical_candles_loaded = 0
        self._vwap_historical_volume = 0
        self._vwap_historical_seed_complete = False
        self._vwap_bootstrap_time = None
        self._vwap_live_tick_count = 0
        self._vwap_last_live_volume = 0
        self._vwap_last_delta_volume = 0
        self._vwap_last_live_tick = None
        self._vwap_current_accumulated_volume = 0
        self._vwap_last_error = None

        self.market_context_engines = {
            timeframe: MarketContextEngine(event_bus, instrument.value, timeframe.value)
            for timeframe in self._timeframes
        }
        self.market_context_engine = self.market_context_engines[self._primary_timeframe]
        self.ai_reasoning_engine = AIReasoningEngine(event_bus, instrument.value, configuration.timeframe)
        self.strategy_engine = StrategyEngine(event_bus, instrument.value, configuration.timeframe)
        self.confidence_calibration_engine = AIConfidenceCalibrationEngine(event_bus, instrument.value, configuration.timeframe)
        self.risk_engine = RiskEngine(event_bus, instrument.value, configuration.timeframe)
        self.execution_policy_engine = TradeExecutionPolicyEngine(
            event_bus,
            instrument=instrument.value,
            timeframe=configuration.timeframe,
        )
        self.trade_authorization_engine = TradeDecisionAuthorizationEngine(
            event_bus,
            instrument=instrument.value,
            timeframe=configuration.timeframe,
        )
        self.trade_plan_engine = RiskTradePlanEngine()
        self.paper_trading_engine = PaperTradingEngine(
            event_bus,
            instrument=instrument.value,
            timeframe=configuration.timeframe,
            safety_mode=configuration.safety_mode,
            configuration=configuration.paper_trading_configuration,
        )
        self.order_engine = OrderManagementEngine(event_bus, instrument.value, configuration.timeframe)
        self.paper_execution_coordinator = PaperExecutionCoordinator(
            event_bus,
            instrument=instrument.value,
            timeframe=configuration.timeframe,
            order_management_engine=self.order_engine,
            paper_trading_engine=self.paper_trading_engine,
            exchange=configuration.exchange,
        )
        self.position_engine = PositionEngine(event_bus, instrument.value, configuration.exchange, configuration.timeframe)
        self.execution_reconciliation_engine = ExecutionReconciliationEngine(
            event_bus,
            instrument=instrument.value,
            timeframe=configuration.timeframe,
            order_management_engine=self.order_engine,
            paper_trading_engine=self.paper_trading_engine,
            position_engine=self.position_engine,
            paper_execution_coordinator=self.paper_execution_coordinator,
            execution_policy_engine=self.execution_policy_engine,
        )
        self.shadow_trading_session_engine = ShadowTradingSessionEngine(
            event_bus,
            instrument=instrument.value,
            timeframe=configuration.timeframe,
            execution_policy_engine=self.execution_policy_engine,
            paper_execution_coordinator=self.paper_execution_coordinator,
            execution_reconciliation_engine=self.execution_reconciliation_engine,
            position_engine=self.position_engine,
        )
        self.candle_engines = {
            timeframe: CandleEngine(event_bus, timeframe)
            for timeframe in self._timeframes
        }
        self.candle_engine = self.candle_engines[self._primary_timeframe]
        self.vwap_engine = VWAPEngine(event_bus)
        self.adr_engine = ADREngine(event_bus, instrument=instrument.value, period=configuration.adr_period)
        moving_average_profile = MovingAverageContextProfile(configuration.moving_average_periods)
        self.moving_average_context_engines = {
            timeframe: MovingAverageContextEngine(
                event_bus,
                instrument=instrument.value,
                timeframe=timeframe.value,
                profile=moving_average_profile,
            )
            for timeframe in self._timeframes
        }
        self.moving_average_context_engine = self.moving_average_context_engines[self._primary_timeframe]
        momentum_profile = MomentumContextProfile(configuration.momentum_period)
        self.momentum_context_engines = {
            timeframe: MomentumContextEngine(
                event_bus,
                instrument=instrument.value,
                timeframe=timeframe.value,
                profile=momentum_profile,
            )
            for timeframe in self._timeframes
        }
        self.momentum_context_engine = self.momentum_context_engines[self._primary_timeframe]
        self.cpr_engine = CPREngine(event_bus)
        self.camarilla_engine = CamarillaEngine(event_bus)
        self.price_action_engines = {
            timeframe: PriceActionEngine(event_bus, instrument.value, timeframe.value)
            for timeframe in self._timeframes
        }
        self.price_action_engine = self.price_action_engines[self._primary_timeframe]
        self.option_chain_engine = OptionChainEngine(
            event_bus,
            instrument.value,
            configuration.exchange,
            configuration.option_expiry_date,
        )
        self.tradingview_evidence_engines = {
            timeframe: TradingViewEvidenceMappingEngine(
                event_bus,
                instrument=instrument.value,
                timeframe=timeframe.value,
            )
            for timeframe in self._timeframes
        }
        self.tradingview_evidence_engine = self.tradingview_evidence_engines[self._primary_timeframe]
        self.tradingview_evidence_assembly_coordinators = {
            timeframe: TradingViewEvidenceAssemblyCoordinator(
                instrument=instrument,
                timeframe=timeframe.value,
                mapping_engine=self.tradingview_evidence_engines[timeframe],
            )
            for timeframe in self._timeframes
        }
        self.tradingview_evidence_assembly_coordinator = self.tradingview_evidence_assembly_coordinators[
            self._primary_timeframe
        ]

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
        self.confidence_calibration_engine.start()
        for engine in self.tradingview_evidence_engines.values():
            engine.start()
        self.execution_policy_engine.start()
        self.trade_authorization_engine.start()
        self.paper_execution_coordinator.start()
        self.execution_reconciliation_engine.start()
        self.shadow_trading_session_engine.start()

    def stop(self) -> None:
        self._shutdown_paper_trading()
        self.shadow_trading_session_engine.stop()
        self.execution_reconciliation_engine.stop()
        self.paper_execution_coordinator.stop()
        self.trade_authorization_engine.stop()
        self.execution_policy_engine.stop()
        for engine in self.tradingview_evidence_engines.values():
            engine.stop()
        self.confidence_calibration_engine.stop()
        self._status = RuntimeStatus.STOPPED

    def mark_error(self) -> None:
        self._status = RuntimeStatus.ERROR

    def process_tick(self, tick: Tick, *, observe_shadow: bool = True) -> RuntimeSnapshot:
        self._require_running()
        if tick.symbol is not self._core_instrument:
            raise ValueError("Tick instrument does not match SymbolRuntime.")
        for engine in self.candle_engines.values():
            engine.on_tick(tick)
        if not self._ready_futures_proxy():
            self.vwap_engine.on_tick(tick)
            levels = self.vwap_engine.get_latest(self._core_instrument)
            if tick.volume > 0 and levels is not None and levels.cumulative_volume > 0:
                self._vwap_source_type = "Spot"
                self._vwap_source_exchange = tick.exchange.value
                self._vwap_source_trading_symbol = self._instrument.value
                self._vwap_source_token = max(self._vwap_source_token, 1)
                self._vwap_source_expiry = None
                self._vwap_source_price = tick.last_price
                self._vwap_unavailable_reason = None
                self._vwap_source_state = "Ready"
                self._vwap_source_message = "Spot VWAP ready"
                self._vwap_subscription_active = False
                self._vwap_last_error = None
            elif levels is None:
                self._vwap_source_type = "-"
                self._vwap_source_exchange = "-"
                self._vwap_source_trading_symbol = "-"
                self._vwap_source_price = tick.last_price
                self._vwap_unavailable_reason = "No positive volume VWAP source"
                self._vwap_source_state = "Unavailable"
                self._vwap_source_message = self._vwap_unavailable_reason
        closed_timeframes = self._process_closed_candles()
        self._last_tick = tick
        self._updated_at = tick.timestamp
        self._refresh_adr(tick.timestamp, tick.last_price)
        self._refresh_closed_timeframe_analysis(closed_timeframes, tick.timestamp, tick.last_price)
        self._process_paper_tick(tick)
        if observe_shadow:
            self.shadow_trading_session_engine.observe_market_event("tick_processed", tick, timestamp=tick.timestamp)
        return self.snapshot()

    def process_vwap_tick(
        self,
        tick: Tick,
        *,
        source_type: str,
        source_exchange: str,
        trading_symbol: str,
        instrument_token: int,
        expiry=None,
        state: str = "Ready",
        message: str = "Futures proxy VWAP ready",
        subscription_active: bool = True,
        historical_candles_loaded: int = 0,
        historical_volume: int = 0,
        historical_seed_complete: bool = False,
        bootstrap_time=None,
        live_tick_count: int = 0,
        last_live_volume: int = 0,
        last_delta_volume: int = 0,
        last_live_tick=None,
        current_accumulated_volume: int = 0,
    ) -> RuntimeSnapshot:
        self._require_running()
        if tick.symbol is not self._core_instrument:
            raise ValueError("VWAP tick instrument does not match SymbolRuntime.")
        self.vwap_engine.on_tick(tick)
        self._vwap_source_type = _require_text(source_type, "source_type")
        self._vwap_source_exchange = _require_text(source_exchange, "source_exchange")
        self._vwap_source_trading_symbol = _require_text(trading_symbol, "trading_symbol")
        if isinstance(instrument_token, bool) or not isinstance(instrument_token, int) or instrument_token <= 0:
            raise ValueError("instrument_token must be a positive integer")
        self._vwap_source_token = instrument_token
        self._vwap_source_expiry = expiry
        self._vwap_source_price = tick.last_price
        self._vwap_unavailable_reason = None
        self._vwap_source_state = _require_text(state, "state")
        self._vwap_source_message = _require_text(message, "message")
        self._vwap_subscription_active = bool(subscription_active)
        self._vwap_historical_candles_loaded = _non_negative_int(historical_candles_loaded, "historical_candles_loaded")
        self._vwap_historical_volume = _non_negative_int(historical_volume, "historical_volume")
        self._vwap_historical_seed_complete = bool(historical_seed_complete)
        self._vwap_bootstrap_time = bootstrap_time
        self._vwap_live_tick_count = _non_negative_int(live_tick_count, "live_tick_count")
        self._vwap_last_live_volume = _non_negative_int(last_live_volume, "last_live_volume")
        self._vwap_last_delta_volume = _non_negative_int(last_delta_volume, "last_delta_volume")
        self._vwap_last_live_tick = last_live_tick
        self._vwap_current_accumulated_volume = _non_negative_int(
            current_accumulated_volume,
            "current_accumulated_volume",
        )
        self._vwap_last_error = None
        self._updated_at = tick.timestamp
        return self.snapshot()

    def mark_vwap_unavailable(
        self,
        reason: str,
        *,
        source_type: str = "-",
        source_exchange: str = "-",
        trading_symbol: str = "-",
        instrument_token: int | None = None,
        expiry=None,
        state: str = "Unavailable",
        message: str | None = None,
        subscription_active: bool = False,
        last_error: str | None = None,
    ) -> RuntimeSnapshot:
        self._vwap_unavailable_reason = _require_text(reason, "reason")
        self._vwap_source_type = _require_text(source_type, "source_type") if source_type != "-" else "-"
        self._vwap_source_exchange = _require_text(source_exchange, "source_exchange") if source_exchange != "-" else "-"
        self._vwap_source_trading_symbol = _require_text(trading_symbol, "trading_symbol") if trading_symbol != "-" else "-"
        self._vwap_source_token = instrument_token if instrument_token is not None else 1
        self._vwap_source_expiry = expiry
        self._vwap_source_state = _require_text(state, "state")
        self._vwap_source_message = _require_text(message or reason, "message")
        self._vwap_subscription_active = bool(subscription_active)
        self._vwap_last_error = last_error or reason
        return self.snapshot()

    def process_daily_ohlc(self, daily_ohlc: DailyOHLC) -> tuple[CPRLevels, CamarillaLevels]:
        self._require_running()
        self._append_daily_ohlc(daily_ohlc)
        cpr = self.cpr_engine.update(daily_ohlc)
        camarilla = self.camarilla_engine.update(daily_ohlc)
        if self._last_tick is not None:
            self._refresh_adr(self._last_tick.timestamp, self._last_tick.last_price)
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
            if candle.timeframe != self._primary_timeframe.value:
                raise ValueError("Historical warm-up candles must match the primary runtime timeframe.")

        accepted = self.candle_engine.seed_history(
            self._core_instrument,
            normalized,
            replace=replace,
        )

        if replace and accepted:
            self.price_action_engine.reset()
            self.moving_average_context_engine.reset()
            self.momentum_context_engine.reset()
            for candle in self.candle_engine.get_history(self._core_instrument):
                self.price_action_engine.process(candle)
                try:
                    self.moving_average_context_engine.process(candle)
                except Exception:
                    pass
                try:
                    self.momentum_context_engine.process(candle)
                except Exception:
                    pass
                self._seed_vwap_from_candle(candle)
        else:
            for candle in accepted:
                self.price_action_engine.process(candle)
                try:
                    self.moving_average_context_engine.process(candle)
                except Exception:
                    pass
                try:
                    self.momentum_context_engine.process(candle)
                except Exception:
                    pass
                self._seed_vwap_from_candle(candle)

        self._last_processed_history_counts[self._primary_timeframe] = len(
            self.candle_engine.get_history(self._core_instrument)
        )
        if accepted:
            self._updated_at = accepted[-1].end_time
        return accepted

    def get_candle_history(self, timeframe: str | TimeFrame | None = None) -> tuple[Candle, ...]:
        engine = self._candle_engine_for(timeframe)
        return tuple(engine.get_history(self._core_instrument))

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
        timeframe: str | TimeFrame | None = None,
    ) -> MarketContextState:
        self._require_running()
        lane = self._timeframe_for(timeframe)
        trading_date = timestamp.date()
        cpr = self.cpr if self.cpr is not None and self.cpr.trading_date <= trading_date else None
        camarilla = (
            self.camarilla
            if self.camarilla is not None and self.camarilla.trading_date <= trading_date
            else None
        )
        snapshot = MarketContextSnapshot(
            symbol=self._instrument.value,
            timeframe=lane.value,
            timestamp=timestamp,
            current_price=current_price,
            session_high=session_high,
            session_low=session_low,
            price_action=self.price_action_engines[lane].state,
            option_chain=self.option_chain_engine.state,
            vwap=self.vwap_engine.get_latest(self._core_instrument),
            cpr=cpr,
            camarilla=camarilla,
        )
        state = self.market_context_engines[lane].process(snapshot)
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
            timeframe=self._primary_timeframe.value,
            timestamp=market_context.timestamp,
            ai_reasoning=ai_reasoning,
            market_context=market_context,
        )
        state = self.strategy_engine.process(snapshot)
        if self._configuration.risk_configuration is not None:
            risk_state = self.trade_plan_engine.evaluate(
                symbol=self._instrument.value,
                timeframe=self._primary_timeframe.value,
                strategy=state,
                configuration=self._configuration.risk_configuration,
                market_context=market_context,
                price_action=self.price_action_engine.state,
                option_chain=self.option_chain_engine.state,
                camarilla=self.camarilla_engine.levels,
                cpr=self.cpr_engine.levels,
                latest_tick=self._last_tick,
                position=self.position_engine.state,
                now=state.timestamp,
            )
            self.risk_engine.record_decision(risk_state)
            self.paper_trading_engine.receive_plan(
                self.trade_plan_engine.active_plan,
                risk_state,
                strategy=state,
                ai_reasoning=ai_reasoning,
            )
        self._updated_at = state.timestamp
        return state

    def calibrate_ai_confidence(self, request: ConfidenceCalibrationRequest):
        self._require_running()
        if not isinstance(request, ConfidenceCalibrationRequest):
            raise TypeError("request must be ConfidenceCalibrationRequest")
        if request.instrument != self._instrument:
            raise ValueError("Confidence calibration request instrument does not match SymbolRuntime.")
        result = self.confidence_calibration_engine.calibrate(request)
        self._updated_at = result.timestamp
        return result

    def get_confidence_result(self, calibration_id: str):
        return self.confidence_calibration_engine.get_result(calibration_id)

    def get_confidence_snapshot(self):
        return self.confidence_calibration_engine.snapshot()

    def reset_confidence_calibration(self):
        return self.confidence_calibration_engine.reset()

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
            timeframe=self._primary_timeframe.value,
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
            timeframe=self._primary_timeframe.value,
            timestamp=request.timestamp,
            risk=risk,
            request=request,
        )
        state = self.order_engine.create(snapshot)
        self._updated_at = state.updated_at
        return state

    def evaluate_execution_policy(self, request: ExecutionRequest) -> TradeExecutionPlan:
        self._require_running()
        if request.instrument != self._instrument.value:
            raise ValueError("ExecutionRequest instrument does not match SymbolRuntime.")
        plan = self.execution_policy_engine.evaluate(request)
        self._updated_at = plan.created_at
        return plan

    def authorize_trade_decision(self, request: TradeAuthorizationRequest):
        self._require_running()
        if not isinstance(request, TradeAuthorizationRequest):
            raise TypeError("request must be TradeAuthorizationRequest")
        if request.instrument != self._instrument:
            raise ValueError("Trade authorization request instrument does not match SymbolRuntime.")
        result = self.trade_authorization_engine.authorize(request)
        self._updated_at = result.timestamp
        return result

    def get_trade_authorization_result(self, authorization_id: str):
        return self.trade_authorization_engine.get_result(authorization_id)

    def get_trade_authorization_snapshot(self):
        return self.trade_authorization_engine.snapshot()

    def reset_trade_authorization(self):
        return self.trade_authorization_engine.reset()

    def map_tradingview_evidence(self, request: TradingViewEvidenceRequest):
        if not isinstance(request, TradingViewEvidenceRequest):
            raise TypeError("request must be TradingViewEvidenceRequest")
        if request.instrument != self._instrument:
            raise ValueError("TradingView evidence request instrument does not match SymbolRuntime.")
        engine = self._tradingview_evidence_engine_for(request.timeframe)
        result = engine.map_evidence(request)
        self._updated_at = result.timestamp
        return result

    def get_tradingview_evidence(self, evidence_id: str, timeframe: str | TimeFrame | None = None):
        return self._tradingview_evidence_engine_for(timeframe).get_evidence(evidence_id)

    def tradingview_evidence_snapshot(self, timeframe: str | TimeFrame | None = None):
        return self._tradingview_evidence_engine_for(timeframe).snapshot()

    def reset_tradingview_evidence(self, timeframe: str | TimeFrame | None = None):
        return self._tradingview_evidence_engine_for(timeframe).reset()

    def create_order_from_execution_plan(self, plan: TradeExecutionPlan) -> OrderState | None:
        self._require_running()
        if not isinstance(plan, TradeExecutionPlan):
            raise TypeError("plan must be TradeExecutionPlan")
        if plan.instrument != self._instrument.value:
            raise ValueError("Execution plan instrument does not match SymbolRuntime.")
        if plan.execution_mode is not ExecutionMode.PAPER:
            return None
        if plan.status is not ExecutionPlanStatus.READY_FOR_PAPER:
            return None
        if plan.broker_submission_allowed or plan.broker_order_calls != 0:
            raise ValueError("Trade Execution Policy V1 plans cannot permit broker submission.")
        risk = self.risk_engine.state
        if risk is None:
            raise ValueError("Risk state is required for order creation.")
        request = OrderRequest(
            client_order_id=plan.execution_plan_id,
            symbol=plan.instrument,
            exchange=self._configuration.exchange,
            timeframe=self._primary_timeframe.value,
            timestamp=plan.created_at,
            side=plan.entry_side,
            order_type=plan.entry_order_type,
            product_type=ProductType.INTRADAY,
            quantity=plan.entry_quantity,
            limit_price=plan.entry_limit_price,
            trigger_price=plan.entry_trigger_price,
        )
        return self.create_order(request)

    def execute_paper_plan(self, request: PaperExecutionRequest) -> PaperExecutionReceipt:
        self._require_running()
        if not isinstance(request, PaperExecutionRequest):
            raise TypeError("request must be PaperExecutionRequest")
        if request.instrument != self._instrument.value:
            raise ValueError("PaperExecutionRequest instrument does not match SymbolRuntime.")
        receipt = self.paper_execution_coordinator.execute(request)
        self._updated_at = receipt.updated_at
        return receipt

    def cancel_paper_execution(self, receipt_id: str, *, timestamp, reason: str = "cancelled") -> PaperExecutionReceipt:
        self._require_running()
        receipt = self.paper_execution_coordinator.cancel(receipt_id, timestamp=timestamp, reason=reason)
        self._updated_at = receipt.updated_at
        return receipt

    def reconcile_paper_execution(self, request: ExecutionReconciliationRequest) -> ExecutionReconciliationReport:
        self._require_running()
        if not isinstance(request, ExecutionReconciliationRequest):
            raise TypeError("request must be ExecutionReconciliationRequest")
        if request.instrument != self._instrument.value:
            raise ValueError("ExecutionReconciliationRequest instrument does not match SymbolRuntime.")
        report = self.execution_reconciliation_engine.reconcile(request)
        self._updated_at = report.created_at
        return report

    def reconcile_paper_execution_receipt(self, receipt_id: str, *, timestamp) -> ExecutionReconciliationReport:
        self._require_running()
        report = self.execution_reconciliation_engine.reconcile_receipt(receipt_id, timestamp=timestamp)
        self._updated_at = report.created_at
        return report

    def start_shadow_session(self, request: ShadowTradingSessionRequest):
        self._require_running()
        if not isinstance(request, ShadowTradingSessionRequest):
            raise TypeError("request must be ShadowTradingSessionRequest")
        if request.instrument != self._instrument.value:
            raise ValueError("Shadow session instrument does not match SymbolRuntime.")
        return self.shadow_trading_session_engine.start_session(request)

    def observe_shadow_event(self, event_name: str, payload, *, timestamp):
        return self.shadow_trading_session_engine.observe_market_event(event_name, payload, timestamp=timestamp)

    def stop_shadow_session(self, *, timestamp, reason: str = "session_completed") -> ShadowTradingSessionSummary:
        return self.shadow_trading_session_engine.stop_session(timestamp=timestamp, reason=reason)

    def get_shadow_snapshot(self):
        return self.shadow_trading_session_engine.snapshot()

    def get_shadow_summary(self, session_id: str):
        return self.shadow_trading_session_engine.get_summary(session_id)

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
        for engine in self.candle_engines.values():
            engine.clear()
        self.vwap_engine.clear()
        self.adr_engine.reset()
        self.cpr_engine.reset()
        self.camarilla_engine.reset()
        for engine in self.price_action_engines.values():
            engine.reset()
        for engine in self.moving_average_context_engines.values():
            engine.reset()
        for engine in self.momentum_context_engines.values():
            engine.reset()
        self.option_chain_engine.reset()
        for engine in self.market_context_engines.values():
            engine.reset()
        self.ai_reasoning_engine.reset()
        self.strategy_engine.reset()
        self.confidence_calibration_engine.reset()
        for engine in self.tradingview_evidence_engines.values():
            engine.reset()
        for coordinator in self.tradingview_evidence_assembly_coordinators.values():
            coordinator.reset()
        self.risk_engine.reset()
        self.execution_policy_engine.reset_session()
        self.trade_authorization_engine.reset()
        self.paper_execution_coordinator.reset_session()
        self.execution_reconciliation_engine.reset_session()
        self.shadow_trading_session_engine.reset_session()
        self.trade_plan_engine.reset()
        self.paper_trading_engine.reset()
        self.order_engine.reset()
        self.position_engine.reset()
        self._last_tick = None
        self._updated_at = None
        self._daily_ohlc_history = ()
        self._last_processed_history_counts = {timeframe: 0 for timeframe in self._timeframes}
        self._vwap_source_type = "-"
        self._vwap_source_exchange = "-"
        self._vwap_source_trading_symbol = "-"
        self._vwap_source_token = 1
        self._vwap_source_expiry = None
        self._vwap_source_price = None
        self._vwap_unavailable_reason = None
        self._vwap_source_state = "Unavailable"
        self._vwap_source_message = "No valid VWAP source"
        self._vwap_subscription_active = False
        self._vwap_historical_candles_loaded = 0
        self._vwap_historical_volume = 0
        self._vwap_historical_seed_complete = False
        self._vwap_bootstrap_time = None
        self._vwap_live_tick_count = 0
        self._vwap_last_live_volume = 0
        self._vwap_last_delta_volume = 0
        self._vwap_last_live_tick = None
        self._vwap_current_accumulated_volume = 0
        self._vwap_last_error = None
        self._status = RuntimeStatus.CREATED

    def snapshot(self, latest_journal_record=None, *, performance_analytics=None) -> RuntimeSnapshot:
        latest_candle = self.candle_engine.get_current(self._core_instrument)
        if latest_candle is None:
            history = self.candle_engine.get_history(self._core_instrument)
            latest_candle = history[-1] if history else None
        return RuntimeSnapshot(
            symbol=self._instrument,
            timeframe=self._primary_timeframe.value,
            status=self._status,
            latest_tick=self._last_tick,
            latest_candle=latest_candle,
            vwap=self.vwap_engine.get_latest(self._core_instrument),
            adr=self.adr_engine.state,
            cpr=self.cpr,
            camarilla=self.camarilla,
            price_action=self.price_action_engine.state,
            option_chain=self.option_chain_engine.state,
            market_context=self.market_context_engine.state,
            moving_average_context=self.moving_average_context_engine.state,
            momentum_context=self.momentum_context_engine.state,
            ai_reasoning=self.ai_reasoning_engine.state,
            strategy=self.strategy_engine.state,
            risk=self.risk_engine.state,
            latest_order=self.order_engine.latest_order,
            position=self.position_engine.state,
            latest_journal_record=latest_journal_record,
            updated_at=self._updated_at,
            vwap_source=self._vwap_source_snapshot(),
            paper_trading=self.paper_trading_engine.snapshot(),
            performance_analytics=performance_analytics,
            execution_policy=self.execution_policy_engine.snapshot(),
            paper_execution=self.paper_execution_coordinator.snapshot(),
            execution_reconciliation=self.execution_reconciliation_engine.snapshot(),
            shadow_trading_session=self.shadow_trading_session_engine.snapshot(),
            confidence_calibration=self.confidence_calibration_engine.snapshot(),
            trade_authorization=self.trade_authorization_engine.snapshot(),
            tradingview_evidence=self.tradingview_evidence_engine.snapshot(),
            adr_diagnostics=self.adr_engine.snapshot(),
            moving_average_context_diagnostics=self.moving_average_context_engine.snapshot(),
            momentum_context_diagnostics=self.momentum_context_engine.snapshot(),
        )

    def _process_paper_tick(self, tick: Tick) -> None:
        record = self.paper_trading_engine.on_tick(
            tick,
            strategy=None,
            risk=None,
        )
        if record is not None:
            updated = self.trade_plan_engine.record_paper_trade_close(realized_pnl=record.net_pnl)
            if updated is not None:
                self.risk_engine.record_decision(updated)

    def _shutdown_paper_trading(self) -> None:
        timestamp = self._updated_at or getattr(self._last_tick, "timestamp", None)
        record = self.paper_trading_engine.shutdown(timestamp=timestamp) if timestamp is not None else self.paper_trading_engine.shutdown()
        if record is not None:
            updated = self.trade_plan_engine.record_paper_trade_close(realized_pnl=record.net_pnl)
            if updated is not None:
                self.risk_engine.record_decision(updated)

    def _process_closed_candles(self) -> tuple[TimeFrame, ...]:
        closed_timeframes = []
        for timeframe, candle_engine in self.candle_engines.items():
            history = candle_engine.get_history(self._core_instrument)
            last_count = self._last_processed_history_counts[timeframe]
            new_candles = history[last_count:]
            for candle in new_candles:
                self.price_action_engines[timeframe].process(candle)
                try:
                    self.moving_average_context_engines[timeframe].process(candle)
                except Exception:
                    pass
                try:
                    self.momentum_context_engines[timeframe].process(candle)
                except Exception:
                    pass
            self._last_processed_history_counts[timeframe] = len(history)
            if new_candles:
                closed_timeframes.append(timeframe)
        return tuple(closed_timeframes)

    def _refresh_closed_timeframe_analysis(
        self,
        timeframes: tuple[TimeFrame, ...],
        timestamp,
        current_price: float,
    ) -> None:
        for timeframe in timeframes:
            try:
                session_high, session_low = self._session_high_low(current_price, timeframe)
                context = self.build_market_context(
                    timestamp=timestamp,
                    current_price=current_price,
                    session_high=session_high,
                    session_low=session_low,
                    timeframe=timeframe,
                )
            except Exception:
                continue

            try:
                self._assemble_tradingview_evidence(timestamp, current_price, timeframe=timeframe)
            except Exception:
                pass

            if timeframe is self._primary_timeframe:
                self._refresh_primary_closed_candle_analysis(context)

    def _refresh_primary_closed_candle_analysis(self, context: MarketContextState) -> None:
        try:
            reasoning = self.run_ai_reasoning(context)
            self.run_strategy(context, reasoning)
        except Exception:
            # Downstream dashboard analysis must never reject an otherwise valid
            # market-data tick; engines keep their previous deterministic state.
            return

    def _assemble_tradingview_evidence(
        self,
        timestamp,
        current_price: float,
        *,
        timeframe: str | TimeFrame | None = None,
    ):
        lane = self._timeframe_for(timeframe)
        history = self.candle_engines[lane].get_history(self._core_instrument)
        latest_closed_candle = history[-1] if history else None
        source = TradingViewEvidenceAssemblyInput(
            timestamp=timestamp,
            instrument=self._instrument,
            timeframe=lane.value,
            latest_price=current_price,
            latest_candle=latest_closed_candle,
            price_action=self.price_action_engines[lane].state,
            camarilla=self.camarilla_engine.levels,
            cpr=self.cpr_engine.levels,
            vwap=self.vwap_engine.get_latest(self._core_instrument),
            adr=self.adr_engine.state,
            moving_average_context=self.moving_average_context_engines[lane].state,
            momentum_context=self.momentum_context_engines[lane].state,
            option_chain=self.option_chain_engine.state,
            market_context=self.market_context_engines[lane].state,
            correlation_id=f"{self._instrument.value}:{lane.value}:{timestamp.isoformat()}",
        )
        return self.tradingview_evidence_assembly_coordinators[lane].assemble(source)

    def _append_daily_ohlc(self, daily_ohlc: DailyOHLC) -> None:
        existing = {item.trading_date: item for item in self._daily_ohlc_history}
        existing[daily_ohlc.trading_date] = daily_ohlc
        self._daily_ohlc_history = tuple(existing[key] for key in sorted(existing))

    def _refresh_adr(self, timestamp, current_price: float) -> None:
        try:
            session_high, session_low = self._session_high_low(current_price, self._primary_timeframe)
            self.adr_engine.update(
                trading_date=timestamp.date(),
                daily_history=self._daily_ohlc_history,
                latest_price=current_price,
                session_high=session_high,
                session_low=session_low,
                timestamp=timestamp,
            )
        except Exception:
            return

    def _session_high_low(self, current_price: float, timeframe: str | TimeFrame | None = None) -> tuple[float, float]:
        lane = self._timeframe_for(timeframe)
        highs = [current_price]
        lows = [current_price]
        candle_engine = self.candle_engines[lane]
        current = candle_engine.get_current(self._core_instrument)
        if current is not None:
            highs.append(current.high)
            lows.append(current.low)
        for candle in candle_engine.get_history(self._core_instrument):
            highs.append(candle.high)
            lows.append(candle.low)
        return max(highs), min(lows)

    def _timeframe_for(self, timeframe: str | TimeFrame | None) -> TimeFrame:
        if timeframe is None:
            return self._primary_timeframe
        parsed = timeframe if isinstance(timeframe, TimeFrame) else TimeFrame.from_value(str(timeframe).strip())
        if parsed not in self.candle_engines:
            raise ValueError("timeframe is not configured for SymbolRuntime.")
        return parsed

    def _candle_engine_for(self, timeframe: str | TimeFrame | None) -> CandleEngine:
        return self.candle_engines[self._timeframe_for(timeframe)]

    def _tradingview_evidence_engine_for(self, timeframe: str | TimeFrame | None) -> TradingViewEvidenceMappingEngine:
        return self.tradingview_evidence_engines[self._timeframe_for(timeframe)]

    def _seed_vwap_from_candle(self, candle: Candle) -> None:
        if candle.volume <= 0:
            return
        tick = Tick(
            symbol=self._core_instrument,
            exchange=Exchange.NSE if self._core_instrument is not Instrument.SENSEX else Exchange.BSE,
            timestamp=candle.end_time,
            last_price=candle.close,
            volume=candle.volume,
            bid_price=0.0,
            ask_price=0.0,
            open_interest=0,
        )
        self.vwap_engine.on_tick(tick)
        if not self._ready_futures_proxy():
            self._vwap_source_type = "Spot"
            self._vwap_source_exchange = tick.exchange.value
            self._vwap_source_trading_symbol = self._instrument.value
            self._vwap_source_price = tick.last_price
            self._vwap_unavailable_reason = None
            self._vwap_source_state = "Ready"
            self._vwap_source_message = "Spot VWAP ready"

    def _vwap_source_snapshot(self) -> RuntimeVWAPSource:
        levels = self.vwap_engine.get_latest(self._core_instrument)
        return RuntimeVWAPSource(
            instrument=self._instrument,
            source_type=self._vwap_source_type,
            source_exchange=self._vwap_source_exchange,
            trading_symbol=self._vwap_source_trading_symbol,
            instrument_token=self._vwap_source_token,
            expiry=self._vwap_source_expiry,
            cumulative_volume=getattr(levels, "cumulative_volume", 0) if levels is not None else 0,
            last_source_price=self._vwap_source_price,
            updated_at=getattr(levels, "timestamp", None),
            ready=levels is not None,
            unavailable_reason=None if levels is not None else self._vwap_unavailable_reason,
            state=self._vwap_source_state,
            message=self._vwap_source_message,
            subscription_active=self._vwap_subscription_active,
            historical_candles_loaded=self._vwap_historical_candles_loaded,
            historical_volume=self._vwap_historical_volume,
            historical_seed_complete=self._vwap_historical_seed_complete,
            bootstrap_time=self._vwap_bootstrap_time,
            live_tick_count=self._vwap_live_tick_count,
            last_live_volume=self._vwap_last_live_volume,
            last_delta_volume=self._vwap_last_delta_volume,
            last_live_tick=self._vwap_last_live_tick,
            current_accumulated_volume=self._vwap_current_accumulated_volume,
            last_error=self._vwap_last_error,
        )

    def _ready_futures_proxy(self) -> bool:
        levels = self.vwap_engine.get_latest(self._core_instrument)
        return self._vwap_source_type == "Futures Proxy" and levels is not None and levels.cumulative_volume > 0

    def _require_running(self) -> None:
        if self._status is not RuntimeStatus.RUNNING:
            raise RuntimeError("SymbolRuntime processing requires RUNNING status.")


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value
