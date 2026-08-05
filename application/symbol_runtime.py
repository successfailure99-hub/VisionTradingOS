"""
Per-symbol Application Orchestrator runtime.
"""

from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from core.enums.instrument import Instrument
from core.enums.exchange import Exchange
from core.enums.timeframe import TimeFrame
from core.models.candle import Candle
from core.models.daily_ohlc import DailyOHLC
from core.models.tick import Tick
from application.execution_runtime_v1 import ExecutionFillPolicy, ExecutionOrderType, ExecutionRuntimeV1, ExecutionRuntimeV1Configuration
from application.trade_lifecycle_v1 import TradeLifecycleCoordinatorV1, TradeLifecycleV1Request
from engines.adr.engine import ADREngine
from engines.ai_reasoning.ai_reasoning_engine import AIReasoningEngine
from engines.ai_reasoning_v2.engine import AIReasoningV2Engine
from engines.ai_confidence_calibration.engine import AIConfidenceCalibrationEngine
from engines.ai_confidence_calibration.models import ConfidenceCalibrationRequest
from engines.camarilla.camarilla_engine import CamarillaEngine
from engines.camarilla.levels import CamarillaLevels
from engines.chart_explanation.engine import ChartExplanationEngine
from engines.candle.candle_engine import CandleEngine
from engines.cpr.cpr_engine import CPREngine
from engines.cpr.levels import CPRLevels
from engines.market_context.market_context_engine import MarketContextEngine
from engines.market_context.models import MarketContextSnapshot, MarketContextState
from engines.market_state.engine import MarketStateEngine
from engines.moving_average_context.engine import MovingAverageContextEngine
from engines.moving_average_context.models import MovingAverageContextProfile
from engines.momentum_context.engine import MomentumContextEngine
from engines.momentum_context.models import MomentumContextProfile
from engines.multi_timeframe_evidence_fusion.engine import MultiTimeframeEvidenceFusionEngine
from engines.volume_context.engine import VolumeContextEngine
from engines.volume_context.models import VolumeContextProfile
from engines.option_chain.models import OptionChainSnapshot, OptionChainState
from engines.option_chain_analytics.models import OptionChainAnalyticsSnapshot
from engines.option_chain.option_chain_engine import OptionChainEngine
from engines.order_management.enums import ProductType
from engines.order_management.models import OrderCommand, OrderRequest, OrderSnapshot, OrderState
from engines.order_management.order_management_engine import OrderManagementEngine
from engines.paper_execution_coordinator.engine import PaperExecutionCoordinator
from engines.paper_execution_coordinator.models import PaperExecutionReceipt, PaperExecutionRequest
from engines.paper_trading.engine import PaperTradingEngine
from engines.position.models import PositionFill, PositionMark, PositionState
from engines.position.position_engine import PositionEngine
from engines.position_management_v1 import PositionManagementV1Configuration, PositionManagementV1Engine, PositionPriceUpdate
from engines.execution_reconciliation.engine import ExecutionReconciliationEngine
from engines.execution_reconciliation.models import ExecutionReconciliationRequest, ExecutionReconciliationReport
from engines.expert_setup_classification.engine import ExpertSetupClassificationEngine
from engines.shadow_trading_session.engine import ShadowTradingSessionEngine
from engines.shadow_trading_session.models import ShadowTradingSessionRequest, ShadowTradingSessionSummary
from engines.price_action.price_action_engine import PriceActionEngine
from engines.risk.models import AccountRiskState, RiskDecisionState, RiskPolicy, RiskSnapshot, TradeRiskPlan
from engines.risk.risk_engine import RiskEngine
from engines.risk.trade_plan_engine import RiskTradePlanEngine
from engines.risk_management_v2 import (
    AccountRiskState as AccountRiskStateV2,
    InstrumentExposureState,
    RiskDecision as RiskDecisionV2,
    RiskManagementV2Engine,
    RiskManagementV2Input,
    SessionRiskState,
)
from engines.runtime_adapter import (
    TradeCandidate,
    TradeCandidateDirection,
    TradeCandidateState,
    adapt_vision_method_to_trade_candidate,
)
from engines.strategy.models import StrategyDecisionState, StrategySnapshot
from engines.strategy.strategy_engine import StrategyEngine
from engines.strategy_decision_v2 import StrategyDecisionV2Engine, StrategyDecisionV2Input
from engines.strategy_decision_v2.enums import (
    StrategyAction,
    StrategyDecisionChange,
    StrategyDecisionQuality,
    StrategyDirection,
    StrategyInvalidationType,
    StrategySetupFamily,
    StrategySetupStatus,
    StrategyTriggerType,
)
from engines.strategy_decision_v2.models import (
    StrategyDecisionV2Snapshot,
    StrategyEntryCondition,
    StrategyInvalidationRule,
    StrategyRiskHandoff,
)
from engines.trade_decision_authorization.engine import TradeDecisionAuthorizationEngine
from engines.trade_decision_authorization.models import TradeAuthorizationRequest
from engines.trade_execution_policy.engine import TradeExecutionPolicyEngine
from engines.trade_execution_policy.enums import ExecutionMode, ExecutionPlanStatus
from engines.trade_execution_policy.models import ExecutionRequest, TradeExecutionPlan
from engines.tradingview_evidence.engine import TradingViewEvidenceMappingEngine
from engines.tradingview_evidence.models import TradingViewEvidenceRequest
from engines.trade_journal_v1 import TradeJournalV1Configuration, TradeJournalV1Engine
from engines.vision_method import VisionMethodSnapshot, VisionMethodValidationReport
from engines.vwap.vwap_engine import VWAPEngine

from application.enums import RuntimeInstrument, RuntimeStatus
from application.models import (
    OperationalReadinessSnapshot,
    RuntimeADRStatus,
    RuntimeConfiguration,
    RuntimeDecisionAudit,
    RuntimeDiagnostics,
    RuntimeJournalPersistenceSnapshot,
    RuntimeOptionChainStatus,
    RuntimePaperPositionSnapshot,
    RuntimeSnapshot,
    RuntimeTradingSession,
    RuntimeVerificationStage,
    RuntimeVWAPSource,
)
from application.runtime_contract import RuntimeContractContext, RuntimeContractSubject, RuntimeContractValidator, RuntimeIntegrityViolation
_OPTION_CHAIN_MAX_AGE_SECONDS = 180.0
_OPTION_CHAIN_TIMESTAMP_TOLERANCE = timedelta(seconds=1)

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
        self._canonical_market_timestamp = None
        self._previous_runtime_snapshot_timestamp = None
        self._runtime_contract_validator = RuntimeContractValidator()
        self._latest_tick_at = None
        self._latest_closed_candle_at = None
        self._latest_analysis_at = None
        self._daily_ohlc_history: tuple[DailyOHLC, ...] = ()
        self._daily_context_source_date: date | None = None
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
        volume_profile = VolumeContextProfile(configuration.volume_lookback)
        self.volume_context_engines = {
            timeframe: VolumeContextEngine(
                event_bus,
                instrument=instrument.value,
                timeframe=timeframe.value,
                profile=volume_profile,
            )
            for timeframe in self._timeframes
        }
        self.volume_context_engine = self.volume_context_engines[self._primary_timeframe]
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
        self.multi_timeframe_evidence_fusion_engine = MultiTimeframeEvidenceFusionEngine(
            event_bus,
            instrument=instrument,
            expected_timeframes=self._timeframes,
        )
        self.market_state_engine = MarketStateEngine(
            event_bus,
            instrument=instrument,
        )
        self.setup_classification_engine = ExpertSetupClassificationEngine(
            event_bus,
            instrument=instrument,
        )
        self.chart_explanation_engine = ChartExplanationEngine(
            event_bus,
            instrument=instrument,
        )
        self.ai_reasoning_v2_engine = AIReasoningV2Engine(
            instrument=self._core_instrument,
            event_bus=event_bus,
        )
        self.strategy_decision_v2_engine = StrategyDecisionV2Engine(
            instrument=self._core_instrument,
            event_bus=event_bus,
        )
        self.risk_management_v2_engine = RiskManagementV2Engine(
            instrument=self._core_instrument,
            event_bus=event_bus,
        )
        self.execution_runtime_v1 = ExecutionRuntimeV1(
            instrument=self._core_instrument,
            configuration=ExecutionRuntimeV1Configuration(
                order_type=ExecutionOrderType.MARKET,
                fill_policy=ExecutionFillPolicy.IMMEDIATE_FULL,
                require_manual_fill_confirmation=False,
            ),
            event_bus=event_bus,
        )
        self.position_management_v1_engine = PositionManagementV1Engine(
            instrument=self._core_instrument,
            event_bus=event_bus,
            configuration=PositionManagementV1Configuration(auto_full_exit_on_objective=True),
        )
        self.trade_lifecycle_v1 = TradeLifecycleCoordinatorV1(
            instrument=self._core_instrument,
            execution_runtime=self.execution_runtime_v1,
            position_engine=self.position_management_v1_engine,
            event_bus=event_bus,
        )
        self.trade_journal_v1_engine = TradeJournalV1Engine(
            configuration=TradeJournalV1Configuration(
                journal_path=_vision_journal_path(instrument),
                checkpoint_path=_vision_checkpoint_path(instrument),
            ),
            event_bus=event_bus,
        )
        self._decision_audit: RuntimeDecisionAudit | None = None
        self._vision_trade_candidate: TradeCandidate | None = None
        self._vision_strategy_decision_v2: StrategyDecisionV2Snapshot | None = None
        self._last_vision_trade_identity: str | None = None
        self._vision_method_snapshot: VisionMethodSnapshot | None = None
        self._vision_method_validation_report: VisionMethodValidationReport | None = None
        self._vision_ai_explanation: str | None = None
        self._option_chain_analytics: OptionChainAnalyticsSnapshot | None = None
        self._option_chain_last_error: str | None = None
        self._paper_recovery = None
        self._last_journal_write_timestamp: datetime | None = None

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
        self.multi_timeframe_evidence_fusion_engine.start()
        self.market_state_engine.start()
        self.setup_classification_engine.start()
        self.chart_explanation_engine.start()
        self.execution_runtime_v1.start()
        self.trade_lifecycle_v1.start()
        self.trade_journal_v1_engine.start()
        self._paper_recovery = self.trade_journal_v1_engine.load_checkpoint(expected_instrument=self._core_instrument)
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
        if self.trade_journal_v1_engine.snapshot().running:
            self.trade_journal_v1_engine.stop()
        lifecycle_snapshot = self.trade_lifecycle_v1.snapshot()
        if lifecycle_snapshot.running and not lifecycle_snapshot.execution_snapshot.open_intent_count and not lifecycle_snapshot.position_snapshot.has_open_position:
            self.trade_lifecycle_v1.stop()
        self.chart_explanation_engine.stop()
        self.setup_classification_engine.stop()
        self.market_state_engine.stop()
        self.multi_timeframe_evidence_fusion_engine.stop()
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
        self._observe_market_timestamp(tick.timestamp)
        self._latest_tick_at = tick.timestamp
        self._ensure_daily_context_for_session(tick.timestamp)
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
        self._observe_market_timestamp(tick.timestamp)
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

    def process_daily_ohlc(
        self,
        daily_ohlc: DailyOHLC,
        *,
        levels_trading_date: date | None = None,
    ) -> tuple[CPRLevels, CamarillaLevels]:
        self._require_running()
        self._append_daily_ohlc(daily_ohlc)
        levels_input = _daily_ohlc_for_levels(daily_ohlc, levels_trading_date)
        cpr = self.cpr_engine.update(levels_input)
        camarilla = self.camarilla_engine.update(levels_input)
        self._daily_context_source_date = daily_ohlc.trading_date
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
            self.volume_context_engine.reset()
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
                try:
                    self.volume_context_engine.process(candle)
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
                try:
                    self.volume_context_engine.process(candle)
                except Exception:
                    pass
                self._seed_vwap_from_candle(candle)

        self._last_processed_history_counts[self._primary_timeframe] = len(
            self.candle_engine.get_history(self._core_instrument)
        )
        if accepted:
            latest = accepted[-1]
            self._refresh_adr(latest.end_time, latest.close)
            self._observe_market_timestamp(latest.end_time)
        return accepted

    def get_candle_history(self, timeframe: str | TimeFrame | None = None) -> tuple[Candle, ...]:
        engine = self._candle_engine_for(timeframe)
        return tuple(engine.get_history(self._core_instrument))

    def process_option_chain(self, snapshot: OptionChainSnapshot) -> OptionChainState:
        self._require_running()
        market_timestamp = self._candidate_market_timestamp(getattr(snapshot, "timestamp", None))
        self._validate_option_chain_snapshot(snapshot, market_timestamp)
        try:
            state = self.option_chain_engine.process(snapshot)
        except Exception as exc:
            self._option_chain_last_error = _safe_error(exc)
            raise
        self._option_chain_last_error = None
        self._observe_market_timestamp(state.timestamp)
        return state

    def process_option_chain_runtime(
        self,
        snapshot: OptionChainSnapshot,
        analytics: OptionChainAnalyticsSnapshot | None = None,
    ) -> RuntimeSnapshot:
        self.process_option_chain(snapshot)
        if analytics is not None:
            self.process_option_chain_analytics(analytics)
        return self.snapshot()

    def process_option_chain_analytics(self, analytics: OptionChainAnalyticsSnapshot) -> OptionChainAnalyticsSnapshot:
        self._require_running()
        market_timestamp = self._candidate_market_timestamp(getattr(analytics, "timestamp", None))
        self._validate_option_chain_analytics(analytics, market_timestamp)
        self._option_chain_analytics = analytics
        self._option_chain_last_error = None
        self._observe_market_timestamp(analytics.timestamp)
        return analytics

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
        self._observe_market_timestamp(state.timestamp)
        return state

    def run_ai_reasoning(self, context: MarketContextState | None = None):
        self._require_running()
        state = self.ai_reasoning_engine.process(context or self.market_context_engine.state)
        self._observe_market_timestamp(state.timestamp)
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
        self._observe_market_timestamp(state.timestamp)
        return state

    def calibrate_ai_confidence(self, request: ConfidenceCalibrationRequest):
        self._require_running()
        if not isinstance(request, ConfidenceCalibrationRequest):
            raise TypeError("request must be ConfidenceCalibrationRequest")
        if request.instrument != self._instrument:
            raise ValueError("Confidence calibration request instrument does not match SymbolRuntime.")
        result = self.confidence_calibration_engine.calibrate(request)
        self._observe_market_timestamp(result.timestamp)
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
        self._observe_market_timestamp(state.timestamp)
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
        self._observe_market_timestamp(state.updated_at)
        return state

    def evaluate_execution_policy(self, request: ExecutionRequest) -> TradeExecutionPlan:
        self._require_running()
        if request.instrument != self._instrument.value:
            raise ValueError("ExecutionRequest instrument does not match SymbolRuntime.")
        plan = self.execution_policy_engine.evaluate(request)
        self._observe_market_timestamp(plan.created_at)
        return plan

    def authorize_trade_decision(self, request: TradeAuthorizationRequest):
        self._require_running()
        if not isinstance(request, TradeAuthorizationRequest):
            raise TypeError("request must be TradeAuthorizationRequest")
        if request.instrument != self._instrument:
            raise ValueError("Trade authorization request instrument does not match SymbolRuntime.")
        result = self.trade_authorization_engine.authorize(request)
        self._observe_market_timestamp(result.timestamp)
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
        self._observe_market_timestamp(result.timestamp)
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
        self._observe_market_timestamp(receipt.updated_at)
        return receipt

    def cancel_paper_execution(self, receipt_id: str, *, timestamp, reason: str = "cancelled") -> PaperExecutionReceipt:
        self._require_running()
        receipt = self.paper_execution_coordinator.cancel(receipt_id, timestamp=timestamp, reason=reason)
        self._observe_market_timestamp(receipt.updated_at)
        return receipt

    def reconcile_paper_execution(self, request: ExecutionReconciliationRequest) -> ExecutionReconciliationReport:
        self._require_running()
        if not isinstance(request, ExecutionReconciliationRequest):
            raise TypeError("request must be ExecutionReconciliationRequest")
        if request.instrument != self._instrument.value:
            raise ValueError("ExecutionReconciliationRequest instrument does not match SymbolRuntime.")
        report = self.execution_reconciliation_engine.reconcile(request)
        self._observe_market_timestamp(report.created_at)
        return report

    def reconcile_paper_execution_receipt(self, receipt_id: str, *, timestamp) -> ExecutionReconciliationReport:
        self._require_running()
        report = self.execution_reconciliation_engine.reconcile_receipt(receipt_id, timestamp=timestamp)
        self._observe_market_timestamp(report.created_at)
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
        self._observe_market_timestamp(state.updated_at)
        return state

    def apply_position_fill(self, fill: PositionFill) -> PositionState:
        self._require_running()
        state = self.position_engine.process_fill(fill)
        self._observe_market_timestamp(state.updated_at)
        return state

    def apply_position_mark(self, mark: PositionMark) -> PositionState:
        self._require_running()
        state = self.position_engine.process_mark(mark)
        self._observe_market_timestamp(state.updated_at)
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
        for engine in self.volume_context_engines.values():
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
        self.multi_timeframe_evidence_fusion_engine.reset()
        self.market_state_engine.reset()
        self.setup_classification_engine.reset()
        self.chart_explanation_engine.reset()
        self.ai_reasoning_v2_engine.reset()
        self.strategy_decision_v2_engine.reset()
        self.risk_management_v2_engine.reset()
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
        self._decision_audit = None
        self._last_tick = None
        self._updated_at = None
        self._canonical_market_timestamp = None
        self._latest_tick_at = None
        self._latest_closed_candle_at = None
        self._latest_analysis_at = None
        self._daily_ohlc_history = ()
        self._daily_context_source_date = None
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
        self._vision_trade_candidate = None
        self._vision_strategy_decision_v2 = None
        self._last_vision_trade_identity = None
        self._vision_method_snapshot = None
        self._vision_method_validation_report = None
        self._vision_ai_explanation = None
        self._decision_audit = None

    def snapshot(self, latest_journal_record=None, *, performance_analytics=None) -> RuntimeSnapshot:
        latest_candle = self.candle_engine.get_current(self._core_instrument)
        primary_candle_history = tuple(self.candle_engine.get_history(self._core_instrument))
        if latest_candle is None:
            latest_candle = primary_candle_history[-1] if primary_candle_history else None
        market_timestamp = self._market_timestamp(latest_candle)
        runtime_session = self._runtime_trading_session(market_timestamp)
        vwap = self.vwap_engine.get_latest(self._core_instrument)
        adr = self.adr_engine.state
        price_action = self.price_action_engine.state
        option_chain = self.option_chain_engine.state
        option_chain_snapshot = self.option_chain_engine.snapshot
        option_chain_analytics = self._option_chain_analytics
        runtime_contract_report = self._runtime_contract_report(
            market_timestamp=market_timestamp,
            runtime_session=runtime_session,
            latest_candle=latest_candle,
            candle_history=primary_candle_history,
            snapshot_candle_history_count=len(primary_candle_history),
            vwap=vwap,
            adr=adr,
            price_action=price_action,
            option_chain_snapshot=option_chain_snapshot,
            option_chain_analytics=option_chain_analytics,
        )
        self._previous_runtime_snapshot_timestamp = market_timestamp
        return RuntimeSnapshot(
            symbol=self._instrument,
            timeframe=self._primary_timeframe.value,
            status=self._status,
            latest_tick=self._last_tick,
            latest_candle=latest_candle,
            vwap=vwap,
            adr=adr,
            cpr=self.cpr,
            camarilla=self.camarilla,
            price_action=price_action,
            option_chain=option_chain,
            option_chain_snapshot=option_chain_snapshot,
            option_chain_analytics=option_chain_analytics,
            option_chain_runtime=self._option_chain_runtime_status(market_timestamp, runtime_session),
            adr_runtime=self._adr_runtime_status(runtime_session),
            market_context=self.market_context_engine.state,
            moving_average_context=self.moving_average_context_engine.state,
            momentum_context=self.momentum_context_engine.state,
            volume_context=self.volume_context_engine.state,
            ai_reasoning=self.ai_reasoning_engine.state,
            strategy=self.strategy_engine.state,
            risk=self.risk_engine.state,
            latest_order=self.order_engine.latest_order,
            position=self.position_engine.state,
            latest_journal_record=latest_journal_record,
            updated_at=self._updated_at,
            latest_tick_at=self._latest_tick_at,
            latest_closed_candle_at=self._latest_closed_candle_at,
            latest_analysis_at=self._latest_analysis_at,
            snapshot_created_at=market_timestamp,
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
            volume_context_diagnostics=self.volume_context_engine.snapshot(),
            multi_timeframe_evidence=self.multi_timeframe_evidence_fusion_engine.snapshot(),
            market_state=self.market_state_engine.snapshot(),
            setup_classification=self.setup_classification_engine.snapshot(),
            chart_explanation=self.chart_explanation_engine.snapshot(),
            ai_reasoning_v2=self.ai_reasoning_v2_engine.snapshot,
            strategy_decision_v2=self._current_strategy_decision_v2_snapshot(),
            risk_management_v2=self.risk_management_v2_engine.snapshot,
            trade_lifecycle_v1=self.trade_lifecycle_v1.snapshot(),
            trade_journal_v1=self.trade_journal_v1_engine.snapshot(),
            vision_method_snapshot=self._vision_method_snapshot,
            vision_method_validation_report=self._vision_method_validation_report,
            vision_trade_candidate=self._vision_trade_candidate,
            canonical_paper_position=self._canonical_paper_position(),
            journal_persistence=self._journal_persistence_snapshot(),
            decision_audit=self._decision_audit,
            runtime_diagnostics=self._runtime_diagnostics(market_timestamp, runtime_session),
            vision_ai_explanation=self._vision_ai_explanation,
            runtime_session=runtime_session,
            runtime_verification_report=self._runtime_verification_report(market_timestamp, runtime_session),
            operational_readiness=self._operational_readiness_snapshot(market_timestamp, runtime_session),
            runtime_contract_report=runtime_contract_report,
            candle_history_count=len(primary_candle_history),
        )

    def _process_paper_tick(self, tick: Tick) -> None:
        if self._vision_strategy_decision_v2 is not None or self._canonical_lifecycle_position() is not None:
            self._process_trade_lifecycle_price(tick)
            return
        strategy = self.strategy_decision_v2_engine.snapshot or self.strategy_engine.state
        risk = self.risk_management_v2_engine.snapshot or self.risk_engine.state
        record = self.paper_trading_engine.on_tick(
            tick,
            strategy=strategy,
            risk=risk,
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
                try:
                    self.volume_context_engines[timeframe].process(candle)
                except Exception:
                    pass
            self._last_processed_history_counts[timeframe] = len(history)
            if new_candles:
                if timeframe is self._primary_timeframe:
                    self._latest_closed_candle_at = new_candles[-1].end_time
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
        if timeframes:
            self._latest_analysis_at = timestamp
            self._fuse_multi_timeframe_evidence(timestamp)

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
            volume_context=self.volume_context_engines[lane].state,
            option_chain=self.option_chain_engine.state,
            market_context=self.market_context_engines[lane].state,
            correlation_id=f"{self._instrument.value}:{lane.value}:{timestamp.isoformat()}",
        )
        return self.tradingview_evidence_assembly_coordinators[lane].assemble(source)

    def _fuse_multi_timeframe_evidence(self, timestamp) -> None:
        snapshots = tuple(
            engine.snapshot().last_evidence
            for engine in self.tradingview_evidence_engines.values()
            if engine.snapshot().last_evidence is not None
        )
        if not snapshots:
            return
        try:
            fusion = self.multi_timeframe_evidence_fusion_engine.fuse(snapshots, timestamp=timestamp)
            market_state = self.market_state_engine.process(fusion, timestamp=timestamp)
            setup = self.setup_classification_engine.process(fusion, market_state, timestamp=timestamp)
            explanation = self.chart_explanation_engine.process(fusion, market_state, setup, timestamp=timestamp)
            self.ai_reasoning_v2_engine.process(fusion, market_state, setup, explanation, timestamp=timestamp)
        except Exception:
            self._record_decision_audit("AI", "AI Reasoning V2 runtime handoff failed.")
            return

    def _process_v2_execution_chain(self, reasoning) -> None:
        try:
            strategy = self.strategy_decision_v2_engine.process(StrategyDecisionV2Input(reasoning))
        except Exception:
            self._record_decision_audit("Strategy", "Strategy Decision V2 input was rejected.", ai_reasoning_v2=reasoning)
            return
        if not strategy.eligible:
            self._record_decision_audit(
                "Strategy",
                _strategy_rejection_reason(strategy),
                ai_reasoning_v2=reasoning,
                strategy_decision_v2=strategy,
            )
            return
        try:
            risk_input = self._build_risk_management_v2_input(strategy)
            risk = self.risk_management_v2_engine.process(risk_input)
        except Exception as exc:
            self._record_decision_audit(
                "Risk",
                f"Risk Management V2 input unavailable: {_safe_error(exc)}",
                ai_reasoning_v2=reasoning,
                strategy_decision_v2=strategy,
            )
            return
        if risk.decision not in {RiskDecisionV2.APPROVED, RiskDecisionV2.APPROVED_REDUCED} or not risk.execution_eligible:
            self._record_decision_audit(
                "Risk",
                _risk_rejection_reason(risk),
                ai_reasoning_v2=reasoning,
                strategy_decision_v2=strategy,
                risk_management_v2=risk,
            )
            return
        try:
            lifecycle = self.trade_lifecycle_v1.process(TradeLifecycleV1Request(strategy, risk))
        except Exception as exc:
            self._record_decision_audit(
                "Lifecycle",
                f"Trade Lifecycle V1 rejected the handoff: {_safe_error(exc)}",
                ai_reasoning_v2=reasoning,
                strategy_decision_v2=strategy,
                risk_management_v2=risk,
            )
            return
        if lifecycle.block_source.value != "none":
            self._record_decision_audit(
                "Lifecycle",
                _lifecycle_rejection_reason(lifecycle),
                ai_reasoning_v2=reasoning,
                strategy_decision_v2=strategy,
                risk_management_v2=risk,
                trade_lifecycle_v1=lifecycle,
            )
            return
        self._record_decision_audit(
            "NONE",
            "V2 runtime chain accepted the opportunity.",
            rejected=False,
            ai_reasoning_v2=reasoning,
            strategy_decision_v2=strategy,
            risk_management_v2=risk,
            trade_lifecycle_v1=lifecycle,
        )

    def process_vision_method_paper_trade(
        self,
        snapshot: VisionMethodSnapshot,
        validation_report: VisionMethodValidationReport,
    ) -> TradeCandidate:
        self._vision_method_snapshot = snapshot
        self._vision_method_validation_report = validation_report
        candidate = adapt_vision_method_to_trade_candidate(snapshot, validation_report)
        self._vision_trade_candidate = candidate
        self._vision_ai_explanation = _vision_method_explanation(candidate, validation_report)
        if not _is_actionable_vision_candidate(candidate):
            self._vision_strategy_decision_v2 = None
            self._record_decision_audit(
                "Vision Method",
                f"Vision Method candidate blocked: {candidate.reason}",
                vision_trade_candidate=candidate,
            )
            return candidate

        identity = _vision_trade_identity(candidate)
        if identity == self._last_vision_trade_identity:
            return candidate

        strategy = self._build_vision_strategy_decision(candidate)
        self._vision_strategy_decision_v2 = strategy
        self._last_vision_trade_identity = identity
        self._process_strategy_risk_lifecycle(
            strategy,
            accepted_message="Vision Method paper-trading chain accepted the candidate.",
            vision_trade_candidate=candidate,
        )
        return candidate

    def _current_strategy_decision_v2_snapshot(self):
        if self._vision_trade_candidate is not None:
            return self._vision_strategy_decision_v2
        return self._vision_strategy_decision_v2 or self.strategy_decision_v2_engine.snapshot

    def _process_strategy_risk_lifecycle(
        self,
        strategy: StrategyDecisionV2Snapshot,
        *,
        ai_reasoning_v2=None,
        accepted_message: str,
        vision_trade_candidate: TradeCandidate | None = None,
    ) -> None:
        try:
            risk_input = self._build_risk_management_v2_input(strategy)
            risk = self.risk_management_v2_engine.process(risk_input)
        except Exception as exc:
            self._record_decision_audit(
                "Risk",
                f"Risk Management V2 input unavailable: {_safe_error(exc)}",
                ai_reasoning_v2=ai_reasoning_v2,
                strategy_decision_v2=strategy,
                vision_trade_candidate=vision_trade_candidate,
            )
            return
        if risk.decision not in {RiskDecisionV2.APPROVED, RiskDecisionV2.APPROVED_REDUCED} or not risk.execution_eligible:
            self._record_decision_audit(
                "Risk",
                _risk_rejection_reason(risk),
                ai_reasoning_v2=ai_reasoning_v2,
                strategy_decision_v2=strategy,
                risk_management_v2=risk,
                vision_trade_candidate=vision_trade_candidate,
            )
            return
        try:
            lifecycle = self.trade_lifecycle_v1.process(TradeLifecycleV1Request(strategy, risk))
        except Exception as exc:
            self._record_decision_audit(
                "Lifecycle",
                f"Trade Lifecycle V1 rejected the handoff: {_safe_error(exc)}",
                ai_reasoning_v2=ai_reasoning_v2,
                strategy_decision_v2=strategy,
                risk_management_v2=risk,
                vision_trade_candidate=vision_trade_candidate,
            )
            return
        if lifecycle.block_source.value != "none":
            self._record_decision_audit(
                "Lifecycle",
                _lifecycle_rejection_reason(lifecycle),
                ai_reasoning_v2=ai_reasoning_v2,
                strategy_decision_v2=strategy,
                risk_management_v2=risk,
                trade_lifecycle_v1=lifecycle,
                vision_trade_candidate=vision_trade_candidate,
            )
            return
        self._record_decision_audit(
            "NONE",
            accepted_message,
            rejected=False,
            ai_reasoning_v2=ai_reasoning_v2,
            strategy_decision_v2=strategy,
            risk_management_v2=risk,
            trade_lifecycle_v1=lifecycle,
            vision_trade_candidate=vision_trade_candidate,
        )
        self._sync_paper_checkpoint()

    def _build_vision_strategy_decision(
        self,
        candidate: TradeCandidate,
    ) -> StrategyDecisionV2Snapshot:
        direction = StrategyDirection.LONG if candidate.direction is TradeCandidateDirection.LONG else StrategyDirection.SHORT
        action = StrategyAction.CONSIDER_LONG if direction is StrategyDirection.LONG else StrategyAction.CONSIDER_SHORT
        trigger = (
            StrategyTriggerType.CONFIRMED_BREAKOUT
            if "Opening Range Break" in candidate.entry_zone
            else StrategyTriggerType.STRUCTURE_CONTINUATION
        )
        invalidation = (
            StrategyInvalidationType.CLOSE_BACK_BELOW_LEVEL
            if direction is StrategyDirection.LONG
            else StrategyInvalidationType.CLOSE_BACK_ABOVE_LEVEL
        )
        quality = _strategy_quality_from_vision(candidate.confidence)
        return StrategyDecisionV2Snapshot(
            instrument=self._core_instrument,
            timestamp=candidate.timestamp,
            action=action,
            direction=direction,
            setup_family=StrategySetupFamily.STRUCTURAL_RETEST,
            setup_status=StrategySetupStatus.READY_FOR_RISK_REVIEW,
            quality=quality,
            change=StrategyDecisionChange.SETUP_APPEARED,
            ai_reasoning=None,
            current_price=None,
            setup_name="Vision Method Candidate",
            thesis="Vision Method produced an eligible deterministic trade candidate.",
            entry_conditions=(
                StrategyEntryCondition(
                    1,
                    trigger,
                    f"Vision Method entry context: {candidate.entry_zone}.",
                    None,
                    True,
                ),
            ),
            invalidation_rules=(
                StrategyInvalidationRule(
                    1,
                    invalidation,
                    f"Vision Method structural invalidation: {candidate.stop_loss_zone}.",
                    None,
                ),
            ),
            objectives=(),
            primary_reference=None,
            invalidation_reference=None,
            context_confidence=_confidence_from_vision(candidate.confidence),
            reasoning_confidence=_confidence_from_vision(candidate.confidence),
            eligible=True,
            requires_retest=False,
            risk_handoff=StrategyRiskHandoff(
                True,
                direction,
                StrategySetupStatus.READY_FOR_RISK_REVIEW,
                None,
                0,
                _confidence_from_vision(candidate.confidence),
                _confidence_from_vision(candidate.confidence),
                (
                    "Trade Source: VISION_METHOD",
                    f"Candidate Reference: {_vision_trade_identity(candidate)}",
                ),
            ),
            rationale=(
                "Trade Source: VISION_METHOD",
                candidate.reason,
                f"Vision Method Snapshot: {candidate.snapshot_reference}",
                f"Vision Method Validation: {candidate.validation_reference}",
            ),
            warnings=(),
            trade_source="VISION_METHOD",
            trade_candidate_reference=_vision_trade_identity(candidate),
            vision_method_snapshot_reference=candidate.snapshot_reference,
            vision_method_validation_reference=candidate.validation_reference,
        )

    def _market_timestamp(self, latest_candle=None) -> datetime | None:
        market_events = tuple(
            value
            for value in (
                self._canonical_market_timestamp,
                self._latest_closed_candle_at,
                self._latest_tick_at,
                getattr(self._last_tick, "timestamp", None),
                getattr(self.vwap_engine.get_latest(self._core_instrument), "timestamp", None),
                getattr(self.option_chain_engine.snapshot, "timestamp", None),
                getattr(self._option_chain_analytics, "timestamp", None),
                self._updated_at,
            )
            if isinstance(value, datetime)
        )
        if market_events:
            return max(market_events)
        candle_end = getattr(latest_candle, "end_time", None)
        return candle_end if isinstance(candle_end, datetime) else None

    def _observe_market_timestamp(self, timestamp: datetime | None) -> datetime | None:
        if not isinstance(timestamp, datetime):
            return self._market_timestamp(None)
        if self._canonical_market_timestamp is None or timestamp > self._canonical_market_timestamp:
            self._canonical_market_timestamp = timestamp
        self._updated_at = self._canonical_market_timestamp
        return self._canonical_market_timestamp

    def _candidate_market_timestamp(self, timestamp: datetime | None) -> datetime | None:
        current = self._market_timestamp(None)
        if isinstance(timestamp, datetime) and (current is None or timestamp > current):
            return timestamp
        return current

    def _runtime_trading_session(self, market_timestamp: datetime | None) -> RuntimeTradingSession:
        trading_date = market_timestamp.date() if market_timestamp is not None else None
        previous_completed = self._daily_context_source_date
        adr = self.adr_engine.state
        vwap = self.vwap_engine.get_latest(self._core_instrument)
        cpr_date = getattr(self.cpr, "trading_date", None)
        camarilla_date = getattr(self.camarilla, "trading_date", None)
        adr_date = getattr(adr, "trading_date", None)
        vwap_date = getattr(vwap, "trading_date", None)
        status = "WAITING"
        reason = "Market timestamp is unavailable."
        if trading_date is not None:
            missing = []
            stale = []
            if self.cpr is None:
                missing.append("CPR")
            elif cpr_date != trading_date:
                stale.append("CPR")
            if self.camarilla is None:
                missing.append("Camarilla")
            elif camarilla_date != trading_date:
                stale.append("Camarilla")
            if missing:
                status = "WAITING_DAILY_CONTEXT"
                reason = f"Missing daily context: {', '.join(missing)}."
            elif stale:
                status = "WAITING_DAILY_CONTEXT"
                reason = f"Stale daily context: {', '.join(stale)}."
            else:
                status = "READY"
                reason = "-"
        return RuntimeTradingSession(
            instrument=self._instrument,
            exchange=self._configuration.exchange,
            market_timestamp=market_timestamp,
            trading_date=trading_date,
            previous_completed_trading_date=previous_completed,
            cpr_trading_date=cpr_date,
            camarilla_trading_date=camarilla_date,
            adr_trading_date=adr_date,
            vwap_trading_date=vwap_date,
            status=status,
            blocking_reason=reason,
        )

    def _validate_option_chain_snapshot(self, snapshot: OptionChainSnapshot, market_timestamp: datetime) -> None:
        if not isinstance(snapshot, OptionChainSnapshot):
            raise TypeError("snapshot must be OptionChainSnapshot")
        if snapshot.symbol != self._instrument.value:
            raise ValueError("OptionChainSnapshot instrument does not match SymbolRuntime.")
        if snapshot.exchange != self.option_chain_engine.exchange:
            raise ValueError("OptionChainSnapshot exchange does not match canonical runtime option-chain engine.")
        if snapshot.expiry_date != self.option_chain_engine.expiry_date:
            raise ValueError("OptionChainSnapshot expiry does not match canonical runtime option-chain engine.")
        if not isinstance(snapshot.timestamp, datetime):
            raise TypeError("OptionChainSnapshot timestamp must be datetime.")
        snapshot_is_aware = snapshot.timestamp.tzinfo is not None and snapshot.timestamp.utcoffset() is not None
        market_is_aware = market_timestamp.tzinfo is not None and market_timestamp.utcoffset() is not None
        if snapshot_is_aware != market_is_aware:
            raise ValueError("OptionChainSnapshot timestamp timezone-awareness must match runtime timestamp.")
        if snapshot.timestamp - market_timestamp > _OPTION_CHAIN_TIMESTAMP_TOLERANCE:
            raise ValueError("OptionChainSnapshot timestamp cannot be in the future relative to runtime timestamp.")
        if snapshot.timestamp.date() != market_timestamp.date():
            raise ValueError("OptionChainSnapshot trading session does not match runtime session.")
        age = max(0.0, (market_timestamp - snapshot.timestamp).total_seconds())
        if age > _OPTION_CHAIN_MAX_AGE_SECONDS:
            raise ValueError("OptionChainSnapshot is stale for the runtime timestamp.")

    def _validate_option_chain_analytics(self, analytics: OptionChainAnalyticsSnapshot, market_timestamp: datetime) -> None:
        if not isinstance(analytics, OptionChainAnalyticsSnapshot):
            raise TypeError("analytics must be OptionChainAnalyticsSnapshot")
        if analytics.underlying.value != self._instrument.value:
            raise ValueError("OptionChainAnalyticsSnapshot instrument does not match SymbolRuntime.")
        if analytics.expiry != self.option_chain_engine.expiry_date:
            raise ValueError("OptionChainAnalyticsSnapshot expiry does not match canonical runtime option-chain engine.")
        analytics_is_aware = analytics.timestamp.tzinfo is not None and analytics.timestamp.utcoffset() is not None
        market_is_aware = market_timestamp.tzinfo is not None and market_timestamp.utcoffset() is not None
        if analytics_is_aware != market_is_aware:
            raise ValueError("OptionChainAnalyticsSnapshot timestamp timezone-awareness must match runtime timestamp.")
        if analytics.timestamp != analytics.source_snapshot.timestamp:
            raise ValueError("OptionChainAnalyticsSnapshot timestamp must match its source snapshot.")
        if analytics.source_snapshot != self.option_chain_engine.snapshot:
            raise ValueError("OptionChainAnalyticsSnapshot must reference the canonical runtime option-chain snapshot.")
        if analytics.source_analysis != self.option_chain_engine.state:
            raise ValueError("OptionChainAnalyticsSnapshot must reference the canonical runtime option-chain analysis.")
        if analytics.timestamp - market_timestamp > _OPTION_CHAIN_TIMESTAMP_TOLERANCE:
            raise ValueError("OptionChainAnalyticsSnapshot timestamp cannot be in the future relative to runtime timestamp.")
        if analytics.timestamp.date() != market_timestamp.date():
            raise ValueError("OptionChainAnalyticsSnapshot trading session does not match runtime session.")
        age = max(0.0, (market_timestamp - analytics.timestamp).total_seconds())
        if age > _OPTION_CHAIN_MAX_AGE_SECONDS:
            raise ValueError("OptionChainAnalyticsSnapshot is stale for the runtime timestamp.")

    def _adr_runtime_status(self, runtime_session: RuntimeTradingSession) -> RuntimeADRStatus:
        diagnostics = self.adr_engine.snapshot()
        period = int(getattr(diagnostics, "period", self._configuration.adr_period) or self._configuration.adr_period)
        history = tuple(self._daily_ohlc_history)
        valid_history = tuple(item for item in history if getattr(item, "trading_date", None) is not None)
        latest_history_date = max((item.trading_date for item in valid_history), default=None)
        snapshot = self.adr_engine.state
        if snapshot is not None:
            state = "READY"
            reason = "-"
            recovery = "-"
        elif len(valid_history) < period:
            state = "INSUFFICIENT_HISTORY"
            reason = f"Insufficient history - {len(valid_history)}/{period} completed sessions."
            recovery = f"Load {period - len(valid_history)} more completed daily sessions."
        elif getattr(diagnostics, "last_error", None):
            state = "INVALID_HISTORY"
            reason = str(diagnostics.last_error)
            recovery = "Load valid completed DailyOHLC history."
        else:
            state = "LOADING_HISTORY"
            reason = "ADR waiting for runtime refresh."
            recovery = "Process the next market tick or daily context refresh."
        return RuntimeADRStatus(
            state=state,
            period=period,
            required_sessions=period,
            loaded_sessions=len(history),
            valid_sessions=len(valid_history),
            latest_history_date=latest_history_date,
            adr_trading_date=getattr(snapshot, "trading_date", None),
            blocking_reason=reason,
            recovery_condition=recovery,
        )

    def _option_chain_runtime_status(
        self,
        market_timestamp: datetime | None,
        runtime_session: RuntimeTradingSession,
    ) -> RuntimeOptionChainStatus:
        snapshot = self.option_chain_engine.snapshot
        option_state = self.option_chain_engine.state
        analytics = self._option_chain_analytics
        last_update = getattr(snapshot, "timestamp", None)
        age = None
        latency_ms = None
        synchronization_status = "-"
        reason = self._option_chain_last_error or "-"
        if market_timestamp is not None and last_update is not None:
            age = max(0.0, (market_timestamp - last_update).total_seconds())
            latency_reference = self._latest_tick_at if isinstance(self._latest_tick_at, datetime) else market_timestamp
            latency_seconds = abs((latency_reference - last_update).total_seconds())
            latency_ms = latency_seconds * 1000.0
            if latency_seconds <= _OPTION_CHAIN_TIMESTAMP_TOLERANCE.total_seconds():
                synchronization_status = f"Option Chain synchronized; Latency = {latency_ms:.0f} ms; Accepted"
            else:
                synchronization_status = f"Option Chain timestamp drift exceeds tolerance; Latency = {latency_ms:.0f} ms"
        recovery = "-"
        if snapshot is None:
            feed_status = "WAITING_FOR_OPTION_TICKS"
            snapshot_status = "WAITING_FOR_DATA"
            analytics_status = "NOT_APPLICABLE"
            operational_state = "WAITING_FOR_OPTION_TICKS"
            reason = reason if reason != "-" else "Option-chain snapshot unavailable."
            recovery = "Receive a complete live option-chain snapshot."
        elif age is not None and age > _OPTION_CHAIN_MAX_AGE_SECONDS:
            feed_status = "STALE"
            snapshot_status = "STALE"
            analytics_status = "WAITING_FOR_ANALYTICS" if analytics is None else "STALE"
            operational_state = "STALE"
            reason = reason if reason != "-" else "Option-chain snapshot is stale."
            recovery = "Receive a fresh option-chain snapshot and analytics for the active session."
        elif runtime_session.trading_date is not None and snapshot.timestamp.date() != runtime_session.trading_date:
            feed_status = "BLOCKED"
            snapshot_status = "SESSION_MISMATCH"
            analytics_status = "WAITING_FOR_ANALYTICS" if analytics is None else "SESSION_MISMATCH"
            operational_state = "SESSION_MISMATCH"
            reason = reason if reason != "-" else "Option-chain snapshot belongs to a different trading session."
            recovery = "Discard stale session data and collect active-session option-chain data."
        elif analytics is None:
            feed_status = "READY"
            snapshot_status = "READY"
            analytics_status = "WAITING_FOR_ANALYTICS"
            operational_state = "WAITING_FOR_ANALYTICS"
            reason = reason if reason != "-" else "Option-chain analytics unavailable."
            recovery = "Run OptionChainAnalytics for the canonical snapshot."
        else:
            feed_status = "READY"
            snapshot_status = "READY"
            analytics_status = "READY"
            operational_state = "READY"
        return RuntimeOptionChainStatus(
            instrument=self._instrument,
            market_timestamp=market_timestamp,
            trading_date=runtime_session.trading_date,
            feed_status=feed_status,
            snapshot_status=snapshot_status,
            analytics_status=analytics_status,
            last_update=last_update,
            age_seconds=age,
            expiry=getattr(snapshot, "expiry_date", None),
            atm_strike=getattr(option_state, "atm_strike", None),
            total_strikes=getattr(option_state, "strike_count", 0) if option_state is not None else 0,
            blocking_reason=reason,
            state=operational_state,
            recovery_condition=recovery,
            latency_ms=latency_ms,
            synchronization_status=synchronization_status,
        )

    def _canonical_lifecycle_position(self):
        lifecycle = self.trade_lifecycle_v1.snapshot()
        strategy = lifecycle.strategy_decision
        if getattr(strategy, "trade_source", None) != "VISION_METHOD":
            return None
        result = lifecycle.position_result
        if result is not None and result.position is not None:
            return result.position
        return lifecycle.position_snapshot.active_position

    def _canonical_paper_position(self) -> RuntimePaperPositionSnapshot | None:
        position = self._canonical_lifecycle_position()
        if position is None:
            if self._vision_trade_candidate is not None:
                return None
            return self._paper_position_from_checkpoint()
        lifecycle = self.trade_lifecycle_v1.snapshot()
        strategy = lifecycle.strategy_decision or self._vision_strategy_decision_v2
        risk = lifecycle.risk_decision or self.risk_management_v2_engine.snapshot
        candidate = self._vision_trade_candidate
        audit = self._decision_audit
        candidate_reference = getattr(strategy, "trade_candidate_reference", None) or (
            _vision_trade_identity(candidate) if candidate is not None else "-"
        )
        snapshot_reference = getattr(strategy, "vision_method_snapshot_reference", None) or getattr(candidate, "snapshot_reference", "-")
        validation_reference = getattr(strategy, "vision_method_validation_reference", None) or getattr(candidate, "validation_reference", "-")
        risk_reference = "-"
        if risk is not None:
            risk_reference = ":".join((risk.instrument.value, risk.timestamp.isoformat(), risk.decision.value))
        quantity = position.open_quantity if position.open_quantity > 0 else position.closed_quantity
        fees = 0.0
        slippage = 0.0
        gross_pnl = position.total_pnl + fees
        return RuntimePaperPositionSnapshot(
            trade_id=position.position_id,
            instrument=self._instrument,
            source="VISION_METHOD",
            candidate_state=getattr(getattr(candidate, "candidate_state", None), "value", "-"),
            direction=position.side.value,
            status=position.status.value,
            lifecycle_state=lifecycle.stage.value,
            risk_state=getattr(getattr(risk, "decision", None), "value", "-"),
            candidate_reference=candidate_reference,
            vision_method_snapshot_reference=snapshot_reference,
            validation_report_reference=validation_reference,
            risk_reference=risk_reference,
            entry_timestamp=position.opened_at,
            entry_price=position.average_entry_price,
            current_price=position.current_price,
            quantity=quantity,
            stop_reference=getattr(candidate, "stop_loss_zone", None) or "Risk invalidation",
            target_reference=getattr(candidate, "target_zone", None) or "Risk objective",
            stop_price=position.invalidation_price,
            target_price=position.objective_price,
            gross_pnl=gross_pnl,
            fees=fees,
            slippage=slippage,
            net_pnl=position.total_pnl,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.realized_pnl,
            blocking_reason=getattr(audit, "reason", "-") if getattr(audit, "rejected", False) else "-",
            recovery_status=self._paper_recovery_status(),
            updated_at=position.updated_at,
        )


    def _sync_paper_checkpoint(self) -> None:
        canonical = self._canonical_paper_position()
        if canonical is None:
            return
        trading_date = getattr(getattr(self, "_vision_method_snapshot", None), "timestamp", None)
        date_value = trading_date.date() if trading_date is not None else (canonical.updated_at.date() if canonical.updated_at is not None else None)
        if date_value is None:
            return
        if canonical.status in {"closed", "invalidated"}:
            self.trade_journal_v1_engine.clear_checkpoint()
            self._paper_recovery = self.trade_journal_v1_engine.load_checkpoint(expected_instrument=self._core_instrument, trading_date=date_value)
            return
        checkpoint = self.trade_journal_v1_engine.save_checkpoint(
            canonical,
            trading_date=date_value,
            exchange=self._configuration.exchange,
            timeframe=self._primary_timeframe.value,
        )
        if checkpoint is not None:
            self._paper_recovery = self.trade_journal_v1_engine.load_checkpoint(expected_instrument=self._core_instrument, trading_date=date_value)

    def _paper_recovery_status(self) -> str:
        recovery = self._paper_recovery
        if recovery is None:
            return "NO_POSITION" if self._canonical_lifecycle_position() is None else "RESTORED"
        return getattr(getattr(recovery, "status", None), "value", "NO_POSITION")

    def _recovered_checkpoint(self):
        recovery = self._paper_recovery
        if recovery is None or getattr(getattr(recovery, "status", None), "value", None) != "RESTORED":
            return None
        return getattr(recovery, "checkpoint", None)

    def _paper_position_from_checkpoint(self) -> RuntimePaperPositionSnapshot | None:
        legacy_paper = self.paper_trading_engine.snapshot()
        if getattr(legacy_paper, "order", None) is not None or getattr(legacy_paper, "position", None) is not None or getattr(legacy_paper, "latest_record", None) is not None:
            return None
        checkpoint = self._recovered_checkpoint()
        if checkpoint is None:
            return None
        return RuntimePaperPositionSnapshot(
            trade_id=checkpoint.trade_id,
            instrument=self._instrument,
            source="VISION_METHOD",
            candidate_state=checkpoint.candidate_state,
            direction=checkpoint.direction,
            status=checkpoint.position_state,
            lifecycle_state=checkpoint.lifecycle_state,
            risk_state="RESTORED",
            candidate_reference=checkpoint.trade_candidate_reference,
            vision_method_snapshot_reference=checkpoint.vision_method_snapshot_reference,
            validation_report_reference=checkpoint.vision_method_validation_reference,
            risk_reference=checkpoint.risk_reference,
            entry_timestamp=checkpoint.entry_timestamp,
            entry_price=checkpoint.entry_price,
            current_price=checkpoint.entry_price,
            quantity=checkpoint.quantity,
            stop_reference="Recovered checkpoint stop",
            target_reference="Recovered checkpoint target",
            stop_price=checkpoint.stop_price,
            target_price=checkpoint.target_price,
            gross_pnl=checkpoint.unrealized_pnl,
            fees=0.0,
            slippage=0.0,
            net_pnl=checkpoint.unrealized_pnl,
            unrealized_pnl=checkpoint.unrealized_pnl,
            realized_pnl=0.0,
            blocking_reason="Recovered from durable checkpoint.",
            recovery_status="RESTORED",
            updated_at=checkpoint.updated_at,
        )

    def _journal_persistence_snapshot(self) -> RuntimeJournalPersistenceSnapshot:
        journal = self.trade_journal_v1_engine.snapshot()
        latest = getattr(journal, "latest_entry", None)
        recovery = self._paper_recovery
        checkpoint = getattr(recovery, "checkpoint", None) if recovery is not None else None
        checkpoint_exists = self.trade_journal_v1_engine.checkpoint_exists
        if journal.last_error:
            operational_state = "PERSISTENCE_ERROR"
            operational_message = f"Persistence error - {journal.last_error}"
        elif recovery is not None and getattr(getattr(recovery, "status", None), "value", "") == "BLOCKED":
            reason = getattr(recovery, "reason", "Recovery blocked.")
            operational_state = "RECOVERY_BLOCKED"
            operational_message = f"Recovery blocked - {reason}"
        elif journal.trade_count > 0:
            operational_state = "READY_WITH_RECORDS"
            operational_message = f"Ready - {journal.trade_count} completed Vision paper trades"
        else:
            operational_state = "READY_EMPTY"
            operational_message = "Ready - No completed Vision paper trades"
        return RuntimeJournalPersistenceSnapshot(
            persistence_status="READY" if journal.ready else "ERROR",
            active_checkpoint_status="ACTIVE" if checkpoint_exists else "NONE",
            recovery_status=getattr(getattr(recovery, "status", None), "value", "NO_POSITION"),
            latest_journal_record_id=getattr(latest, "trade_id", None),
            journal_write_timestamp=self._last_journal_write_timestamp,
            journal_blocking_reason=journal.last_error or "-",
            journal_record_count=journal.trade_count,
            checkpoint_trade_id=getattr(checkpoint, "trade_id", None),
            recovery_reason=getattr(recovery, "reason", "-"),
            operational_state=operational_state,
            operational_message=operational_message,
        )

    def _runtime_contract_report(
        self,
        *,
        market_timestamp: datetime | None,
        runtime_session: RuntimeTradingSession,
        latest_candle,
        candle_history: tuple[Candle, ...],
        snapshot_candle_history_count: int,
        vwap,
        adr,
        price_action,
        option_chain_snapshot,
        option_chain_analytics,
    ):
        context = RuntimeContractContext(
            instrument=self._instrument,
            timeframe=self._primary_timeframe.value,
            runtime_timestamp=market_timestamp,
            trading_date=runtime_session.trading_date,
            session=runtime_session,
            previous_runtime_timestamp=self._previous_runtime_snapshot_timestamp,
        )
        runtime_subject = RuntimeContractSubject(
            instrument=self._instrument,
            timeframe=self._primary_timeframe.value,
            timestamp=market_timestamp,
            trading_date=runtime_session.trading_date,
            session=runtime_session,
        )
        report = self._runtime_contract_validator.validate_many(
            (
                ("RuntimeSnapshot", runtime_subject, "SymbolRuntime", "RuntimeSnapshot", "Dashboard"),
                ("Candle", latest_candle, "SymbolRuntime", "CandleEngine", "Vision Method"),
                ("DailyOHLC", self._daily_ohlc_history[-1] if self._daily_ohlc_history else None, "SymbolRuntime", "Daily OHLC Warmup", "Daily Context"),
                ("CPR", self.cpr, "SymbolRuntime", "CPREngine", "Vision Level Context"),
                ("Camarilla", self.camarilla, "SymbolRuntime", "CamarillaEngine", "Vision Level Context"),
                ("ADR", adr, "SymbolRuntime", "ADREngine", "Vision Level Context"),
                ("VWAP", vwap, "SymbolRuntime", "VWAPEngine", "Vision Level Context"),
                ("OptionChainSnapshot", option_chain_snapshot, "SymbolRuntime", "OptionChainEngine", "Vision Option Confirmation"),
                ("OptionChainAnalyticsSnapshot", option_chain_analytics, "SymbolRuntime", "OptionChainAnalyticsEngine", "Vision Option Confirmation"),
                ("PriceAction", price_action, "SymbolRuntime", "PriceActionEngine", "TradingView Evidence"),
                ("Fusion", self.multi_timeframe_evidence_fusion_engine.snapshot(), "SymbolRuntime", "MultiTimeframeEvidenceFusionEngine", "Market State"),
                ("MarketState", self.market_state_engine.snapshot(), "SymbolRuntime", "MarketStateEngine", "Expert Setup"),
                ("ExpertSetup", self.setup_classification_engine.snapshot(), "SymbolRuntime", "ExpertSetupClassificationEngine", "Chart Explanation"),
                ("ChartExplanation", self.chart_explanation_engine.snapshot(), "SymbolRuntime", "ChartExplanationEngine", "AI Reasoning V2"),
                ("VisionMethodSnapshot", self._vision_method_snapshot, "SymbolRuntime", "Vision Method Calculator", "Vision Validation"),
                ("ValidationReport", self._vision_method_validation_report, "SymbolRuntime", "Vision Method Validation", "Runtime Adapter"),
            ),
            context,
        )
        integrity_violations = self._runtime_integrity_violations(
            market_timestamp=market_timestamp,
            runtime_session=runtime_session,
            candle_history=candle_history,
            snapshot_candle_history_count=snapshot_candle_history_count,
        )
        if integrity_violations:
            return replace(report, status="FAILED", integrity_violations=integrity_violations)
        return report

    def _runtime_integrity_violations(
        self,
        *,
        market_timestamp: datetime | None,
        runtime_session: RuntimeTradingSession,
        candle_history: tuple[Candle, ...],
        snapshot_candle_history_count: int,
    ) -> tuple[RuntimeIntegrityViolation, ...]:
        violations: list[RuntimeIntegrityViolation] = []
        violations.extend(
            self._candle_history_integrity_violations(
                market_timestamp=market_timestamp,
                runtime_session=runtime_session,
                candle_history=candle_history,
                snapshot_candle_history_count=snapshot_candle_history_count,
            )
        )
        violations.extend(
            self._downstream_timestamp_integrity_violations(
                market_timestamp=market_timestamp,
            )
        )
        return tuple(violations)

    def _candle_history_integrity_violations(
        self,
        *,
        market_timestamp: datetime | None,
        runtime_session: RuntimeTradingSession,
        candle_history: tuple[Candle, ...],
        snapshot_candle_history_count: int,
    ) -> tuple[RuntimeIntegrityViolation, ...]:
        violations: list[RuntimeIntegrityViolation] = []
        if snapshot_candle_history_count != len(candle_history):
            violations.append(
                self._runtime_integrity_violation(
                    "RuntimeSnapshot",
                    "Snapshot history count equals runtime history count",
                    f"{len(candle_history)} candles",
                    f"{snapshot_candle_history_count} candles",
                    market_timestamp,
                    producer="RuntimeSnapshot",
                    consumer="Dashboard",
                    recovery_action="Regenerate RuntimeSnapshot from SymbolRuntime candle history.",
                )
            )

        starts: set[datetime] = set()
        duplicates: list[datetime] = []
        for candle in candle_history:
            if candle.start_time in starts:
                duplicates.append(candle.start_time)
            starts.add(candle.start_time)
            if market_timestamp is not None and candle.end_time > market_timestamp:
                violations.append(
                    self._runtime_integrity_violation(
                        "Candle",
                        "Closed candle timestamp is not in the future",
                        f"end_time <= {market_timestamp.isoformat()}",
                        candle.end_time.isoformat(),
                        candle.end_time,
                        producer="CandleEngine",
                        consumer="Runtime History",
                        recovery_action="Reject future closed candle and wait for canonical market timestamp.",
                    )
                )
        if duplicates:
            violations.append(
                self._runtime_integrity_violation(
                    "Candle",
                    "Runtime candle history has no duplicate candle timestamps",
                    "unique candle start_time values",
                    ", ".join(item.isoformat() for item in duplicates),
                    market_timestamp,
                    producer="CandleEngine",
                    consumer="Runtime History",
                    recovery_action="Reject duplicate candle publication and keep canonical candle history.",
                )
            )

        active_history = self._active_session_candle_history(candle_history, runtime_session)
        expected_delta = self._primary_timeframe.duration
        for previous, current in zip(active_history, active_history[1:]):
            if previous.start_time >= current.start_time:
                violations.append(
                    self._runtime_integrity_violation(
                        "Candle",
                        "Runtime candle history is chronological",
                        "strictly increasing candle start_time values",
                        f"{previous.start_time.isoformat()} before {current.start_time.isoformat()}",
                        current.start_time,
                        producer="CandleEngine",
                        consumer="Runtime History",
                        recovery_action="Reject non-chronological candle history and rebuild from canonical producer.",
                    )
                )
            if previous.end_time > current.start_time:
                violations.append(
                    self._runtime_integrity_violation(
                        "Candle",
                        "Runtime candle history has no overlapping candles",
                        "previous end_time <= current start_time",
                        f"{previous.end_time.isoformat()} > {current.start_time.isoformat()}",
                        current.start_time,
                        producer="CandleEngine",
                        consumer="Runtime History",
                        recovery_action="Reject overlapping candle history and rebuild from canonical producer.",
                    )
                )
            if current.start_time - previous.start_time != expected_delta:
                violations.append(
                    self._runtime_integrity_violation(
                        "Candle",
                        "Runtime candle history is continuous",
                        f"next candle every {expected_delta}",
                        f"gap from {previous.start_time.isoformat()} to {current.start_time.isoformat()}",
                        current.start_time,
                        producer="CandleEngine",
                        consumer="Opening Range",
                        recovery_action="Wait for CandleEngine recovery before Vision Method evaluation.",
                    )
                )
        return tuple(violations)

    def _downstream_timestamp_integrity_violations(self, *, market_timestamp: datetime | None) -> tuple[RuntimeIntegrityViolation, ...]:
        violations: list[RuntimeIntegrityViolation] = []
        timestamped_children = (
            ("VisionMethodSnapshot", self._vision_method_snapshot, "Vision Method Calculator", "Vision Validation"),
            ("ValidationReport", self._vision_method_validation_report, "Vision Method Validation", "Runtime Adapter"),
            ("TradeCandidate", self._vision_trade_candidate, "Runtime Adapter", "Risk Management V2"),
            ("StrategyDecision", self._current_strategy_decision_v2_snapshot(), "StrategyDecisionV2", "Risk Management V2"),
            ("PaperPosition", self._canonical_paper_position(), "TradeLifecycleV1", "Dashboard Position"),
            ("Journal", self._journal_persistence_snapshot(), "TradeJournalV1", "Dashboard Journal"),
        )
        for object_name, snapshot, producer, consumer in timestamped_children:
            timestamp = self._snapshot_timestamp(snapshot)
            if (
                market_timestamp is not None
                and timestamp is not None
                and self._timestamps_are_comparable(timestamp, market_timestamp)
                and timestamp > market_timestamp
            ):
                violations.append(
                    self._runtime_integrity_violation(
                        object_name,
                        "Snapshot timestamp is not newer than RuntimeSnapshot timestamp",
                        f"<= {market_timestamp.isoformat()}",
                        timestamp.isoformat(),
                        timestamp,
                        producer=producer,
                        consumer=consumer,
                        recovery_action="Hold downstream publication until canonical runtime timestamp advances.",
                    )
                )

        candidate_timestamp = self._snapshot_timestamp(self._vision_trade_candidate)
        strategy_timestamp = self._snapshot_timestamp(self._current_strategy_decision_v2_snapshot())
        if (
            candidate_timestamp is not None
            and strategy_timestamp is not None
            and self._timestamps_are_comparable(strategy_timestamp, candidate_timestamp)
            and strategy_timestamp != candidate_timestamp
        ):
            violations.append(
                self._runtime_integrity_violation(
                    "StrategyDecision",
                    "Strategy timestamp matches TradeCandidate timestamp",
                    candidate_timestamp.isoformat(),
                    strategy_timestamp.isoformat(),
                    strategy_timestamp,
                    producer="StrategyDecisionV2",
                    consumer="Risk Management V2",
                    recovery_action="Reject stale strategy decision and rerun from canonical TradeCandidate.",
                )
            )

        position_timestamp = self._snapshot_timestamp(self._canonical_paper_position())
        if (
            strategy_timestamp is not None
            and position_timestamp is not None
            and self._timestamps_are_comparable(position_timestamp, strategy_timestamp)
            and position_timestamp < strategy_timestamp
        ):
            violations.append(
                self._runtime_integrity_violation(
                    "PaperPosition",
                    "Paper position timestamp is not before Strategy timestamp",
                    f">= {strategy_timestamp.isoformat()}",
                    position_timestamp.isoformat(),
                    position_timestamp,
                    producer="TradeLifecycleV1",
                    consumer="Dashboard Position",
                    recovery_action="Reject stale paper position snapshot.",
                )
            )

        journal_timestamp = self._snapshot_timestamp(self._journal_persistence_snapshot())
        if (
            position_timestamp is not None
            and journal_timestamp is not None
            and self._timestamps_are_comparable(journal_timestamp, position_timestamp)
            and journal_timestamp < position_timestamp
        ):
            violations.append(
                self._runtime_integrity_violation(
                    "Journal",
                    "Journal timestamp is not before PaperPosition timestamp",
                    f">= {position_timestamp.isoformat()}",
                    journal_timestamp.isoformat(),
                    journal_timestamp,
                    producer="TradeJournalV1",
                    consumer="Dashboard Journal",
                    recovery_action="Flush journal from canonical lifecycle position before publication.",
                )
            )
        return tuple(violations)

    def _active_session_candle_history(
        self,
        candle_history: tuple[Candle, ...],
        runtime_session: RuntimeTradingSession,
    ) -> tuple[Candle, ...]:
        trading_date = runtime_session.trading_date
        if trading_date is None:
            return tuple(sorted(candle_history, key=lambda item: item.start_time))
        return tuple(
            sorted(
                (
                    candle
                    for candle in candle_history
                    if candle.start_time.date() == trading_date and candle.timeframe == self._primary_timeframe.value
                ),
                key=lambda item: item.start_time,
            )
        )

    def _runtime_integrity_violation(
        self,
        object_name: str,
        invariant: str,
        expected: str,
        actual: str,
        timestamp: datetime | None,
        *,
        producer: str,
        consumer: str,
        recovery_action: str,
    ) -> RuntimeIntegrityViolation:
        return RuntimeIntegrityViolation(
            object_name=object_name,
            invariant=invariant,
            owner="SymbolRuntime",
            producer=producer,
            consumer=consumer,
            expected=expected,
            actual=actual,
            timestamp=timestamp,
            instrument=self._instrument.value,
            timeframe=self._primary_timeframe.value,
            recovery_action=recovery_action,
        )

    @staticmethod
    def _snapshot_timestamp(snapshot) -> datetime | None:
        if snapshot is None:
            return None
        for field_name in ("timestamp", "updated_at", "market_timestamp", "journal_write_timestamp", "entry_timestamp"):
            value = getattr(snapshot, field_name, None)
            if isinstance(value, datetime):
                return value
        return None

    @staticmethod
    def _timestamps_are_comparable(left: datetime, right: datetime) -> bool:
        left_aware = left.tzinfo is not None and left.utcoffset() is not None
        right_aware = right.tzinfo is not None and right.utcoffset() is not None
        return left_aware == right_aware

    def _operational_readiness_snapshot(
        self,
        market_timestamp: datetime | None,
        runtime_session: RuntimeTradingSession,
    ) -> OperationalReadinessSnapshot:
        adr_status = self._adr_runtime_status(runtime_session)
        vwap_source = self._vwap_source_snapshot()
        option_status = self._option_chain_runtime_status(market_timestamp, runtime_session)
        journal = self._journal_persistence_snapshot()
        mandatory_blockers = []
        optional_degradations = []
        disabled = ["Broker mutation disabled"]
        candle_ready = bool(self.candle_engine.get_history(self._core_instrument) or self.candle_engine.get_current(self._core_instrument))
        daily_ready = runtime_session.status == "READY"
        if not candle_ready:
            mandatory_blockers.append("Candle warmup unavailable")
        if not daily_ready:
            mandatory_blockers.append(runtime_session.blocking_reason)
        if adr_status.state != "READY":
            optional_degradations.append(f"ADR {adr_status.state}: {adr_status.blocking_reason}")
        if not vwap_source.ready:
            optional_degradations.append(f"VWAP {vwap_source.state}: {vwap_source.message}")
        if option_status.state != "READY":
            optional_degradations.append(f"Option Chain {option_status.state}: {option_status.blocking_reason}")
        journal_ready = journal.operational_state in {"READY_EMPTY", "READY_WITH_RECORDS"}
        if not journal_ready:
            mandatory_blockers.append(journal.operational_message)
        live_analysis_ready = candle_ready and daily_ready
        vision_ready = self._vision_method_snapshot is not None or live_analysis_ready
        paper_ready = journal_ready and self.trade_lifecycle_v1.snapshot().running
        broker_ready = False
        if mandatory_blockers:
            overall = "BLOCKED"
        elif runtime_session.trading_date is None:
            overall = "STARTING"
        elif optional_degradations:
            overall = "DEGRADED"
        elif self._vision_trade_candidate is not None:
            overall = "READY_FOR_PAPER"
        elif vision_ready:
            overall = "READY_FOR_VISION"
        else:
            overall = "READY_FOR_ANALYSIS"
        return OperationalReadinessSnapshot(
            overall_state=overall,
            live_analysis_ready=live_analysis_ready,
            vision_evaluation_ready=vision_ready,
            paper_trading_ready=paper_ready,
            journal_ready=journal_ready,
            broker_read_only_ready=broker_ready,
            mandatory_blockers=tuple(item for item in mandatory_blockers if item and item != "-"),
            optional_degradations=tuple(optional_degradations),
            intentional_disabled_features=tuple(disabled),
            timestamp=market_timestamp,
            session=runtime_session,
            primary_blocker=mandatory_blockers[0] if mandatory_blockers else "-",
        )

    def _runtime_verification_report(
        self,
        market_timestamp: datetime | None,
        runtime_session: RuntimeTradingSession,
    ) -> tuple[RuntimeVerificationStage, ...]:
        validation = self._vision_method_validation_report
        method_snapshot = self._vision_method_snapshot
        candidate = self._vision_trade_candidate
        audit = self._decision_audit
        risk = self.risk_management_v2_engine.snapshot
        lifecycle = self.trade_lifecycle_v1.snapshot()
        journal = self.trade_journal_v1_engine.snapshot()
        canonical_position = self._canonical_paper_position()
        daily_ready = runtime_session.status == "READY"
        option_status = self._option_chain_runtime_status(market_timestamp, runtime_session)
        option_snapshot_ready = option_status.snapshot_status == "READY"
        option_analytics_ready = option_status.analytics_status == "READY"
        option_reason = option_status.blocking_reason
        context_failures = {
            getattr(failure, "stage", "").casefold(): failure
            for failure in tuple(getattr(method_snapshot, "assembly_failures", ()) or ())
        }

        def context_ready(name: str, attr: str) -> bool:
            return method_snapshot is not None and getattr(method_snapshot, attr, None) is not None and name.casefold() not in context_failures

        def context_reason(name: str, default: str) -> str:
            failure = context_failures.get(name.casefold())
            if failure is None:
                return default
            return f"{failure.status.value}: {failure.failure_reason}"

        def status_for(stage: str, ready: bool, detail: str) -> str:
            if detail.startswith("NO_ACTIONABLE_CANDIDATE"):
                return "NO_ACTIONABLE_CANDIDATE"
            if detail.startswith("NOT_APPLICABLE"):
                return "NOT_APPLICABLE"
            if ready:
                return "READY"
            failure = context_failures.get(stage.casefold())
            if failure is not None and getattr(getattr(failure, "status", None), "value", "") == "failed":
                return "FAILED"
            if audit is not None and audit.rejected_at == stage:
                return "BLOCKED"
            if detail.startswith("Stale") or detail.startswith("Missing") or "rejected" in detail.lower():
                return "BLOCKED"
            return "WAITING"

        def latency_for(stage_timestamp: datetime | None) -> float | None:
            if market_timestamp is None or stage_timestamp is None:
                return None
            market_aware = market_timestamp.tzinfo is not None and market_timestamp.utcoffset() is not None
            stage_aware = stage_timestamp.tzinfo is not None and stage_timestamp.utcoffset() is not None
            if market_aware != stage_aware:
                return None
            return max(0.0, (market_timestamp - stage_timestamp).total_seconds() * 1000.0)

        def recovery_state() -> str:
            recovery = self._paper_recovery
            state = getattr(getattr(recovery, "status", None), "value", "NO_POSITION")
            if self.trade_journal_v1_engine.checkpoint_exists:
                return "CHECKPOINT_ACTIVE"
            return str(state).upper()

        def stage_contract(stage: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
            contracts = {
                "Application Startup": ((), ("Runtime status is RUNNING.",), ("Runtime not started.",)),
                "Market Data": (("Application Startup",), ("At least one accepted tick is available.",), ("No accepted tick.",)),
                "Reference Data": (("Application Startup",), ("Reference daily context is aligned to the active trading session.",), ("Missing or stale daily context.",)),
                "Candle Engine": (("Market Data",), ("At least one closed candle is available.",), ("No closed candle.",)),
                "Daily Context": (("Reference Data",), ("CPR, Camarilla, ADR and VWAP context are active-session aligned where available.",), ("Missing or stale daily context.",)),
                "Opening Range": (("Candle Engine",), ("Opening-range candles exist and are session/timezone aligned.",), ("Opening range unavailable or incomplete.",)),
                "Structure": (("Candle Engine",), ("Minimum closed candle history exists for structure assembly.",), ("Structure context unavailable.",)),
                "Liquidity": (("Candle Engine",), ("Closed candle history exists for liquidity assembly.",), ("Liquidity context unavailable.",)),
                "Structure Events": (("Structure", "Liquidity"), ("Structure context is usable for event classification.",), ("Structure events context unavailable.",)),
                "Setup Qualification": (("Daily Context", "Opening Range", "Structure", "Liquidity", "Structure Events"), ("All Vision Method prerequisite contexts are available.",), ("Setup qualification unavailable.",)),
                "Option Feed": (("Market Data",), ("Live option feed is active or deterministically unavailable.",), ("Option feed waiting or unavailable.",)),
                "Option Snapshot": (("Option Feed",), ("Canonical option-chain snapshot is fresh.",), ("Option snapshot waiting or stale.",)),
                "Option Analytics": (("Option Snapshot",), ("Canonical option-chain analytics snapshot is fresh.",), ("Option analytics waiting or stale.",)),
                "Option Confirmation": (("Setup Qualification", "Option Analytics"), ("Vision option confirmation context is available or deterministically unavailable.",), ("Option confirmation unavailable.",)),
                "Vision Method": (("Daily Context", "Opening Range", "Structure", "Liquidity", "Structure Events", "Setup Qualification", "Option Confirmation"), ("VisionMethodSnapshot has been assembled.",), ("Vision Method snapshot unavailable.",)),
                "Validation": (("Vision Method",), ("Vision Method validation report exists.",), ("Validation report unavailable.",)),
                "Runtime Adapter": (("Validation",), ("TradeCandidate has been evaluated.",), ("TradeCandidate not evaluated.",)),
                "TradeCandidate": (("Runtime Adapter",), ("TradeCandidate is actionable LONG or SHORT.",), ("No actionable candidate.",)),
                "Strategy": (("TradeCandidate",), ("Actionable Vision candidate has produced StrategyDecisionV2.",), ("No actionable candidate.",)),
                "Risk": (("Strategy",), ("RiskManagementV2 has evaluated the strategy decision.",), ("Risk waiting or not applicable.",)),
                "Lifecycle": (("Risk",), ("Approved risk has entered TradeLifecycleV1.",), ("Lifecycle waiting or not applicable.",)),
                "Paper Position": (("Lifecycle",), ("Canonical Vision paper position exists.",), ("No canonical Vision paper position.",)),
                "Paper Trade": (("Paper Position",), ("Paper trade is represented by canonical position state.",), ("No canonical Vision paper position.",)),
                "Journal": (("Lifecycle", "Paper Position"), ("TradeJournalV1 has at least one journal entry.",), ("No journal entry.",)),
                "AI Explanation": (("Runtime Adapter",), ("Vision AI explanation text exists for current candidate.",), ("Vision explanation unavailable.",)),
            }
            return contracts.get(stage, ((), ("Stage reports READY only when its producer output is available.",), ("Stage output unavailable.",)))

        daily_reason = runtime_session.blocking_reason if not daily_ready else "-"
        candidate_state = getattr(getattr(candidate, "candidate_state", None), "value", None)
        no_candidate_reason = getattr(candidate, "reason", None) or "No Vision trade candidate."
        actionable_candidate = candidate_state in {"long", "short"}
        trade_candidate_detail = "-" if actionable_candidate else f"NO_ACTIONABLE_CANDIDATE - {no_candidate_reason}"
        strategy_ready = actionable_candidate and self._vision_strategy_decision_v2 is not None
        risk_ready = actionable_candidate and risk is not None
        risk_detail = "Risk waiting for actionable candidate." if actionable_candidate else "NOT_APPLICABLE - No actionable candidate."
        lifecycle_detail = "Lifecycle waiting for approved risk." if risk_ready else "NOT_APPLICABLE - Risk was not invoked."
        method_timestamp = getattr(method_snapshot, "timestamp", None)
        validation_timestamp = getattr(validation, "timestamp", None)
        candidate_timestamp = getattr(candidate, "timestamp", None)
        journal_ready = getattr(journal, "latest_entry", None) is not None
        lifecycle_ready = getattr(lifecycle, "processing_count", 0) > 0
        paper_ready = canonical_position is not None

        rows = (
            ("Application Startup", "SymbolRuntime", "ApplicationLifecycle", "Reference Data", self._status is RuntimeStatus.RUNNING, market_timestamp, "Runtime not started."),
            ("Market Data", "SymbolRuntime", "MarketDataEngine", "CandleEngine", self._last_tick is not None, getattr(self._last_tick, "timestamp", None), "No accepted tick."),
            ("Reference Data", "SymbolRuntime", "Daily OHLC Warmup", "Daily Context", daily_ready, market_timestamp, daily_reason),
            ("Candle Engine", "SymbolRuntime", "CandleEngine", "Vision Method", self._latest_closed_candle_at is not None, self._latest_closed_candle_at, "No closed candle."),
            ("Daily Context", "SymbolRuntime", "CPR/Camarilla/ADR/VWAP", "Vision Level Context", daily_ready, market_timestamp, daily_reason),
            ("Opening Range", "SymbolRuntime", "Vision Opening Range", "Vision Method Calculator", context_ready("Opening Range", "opening_range_context"), method_timestamp, context_reason("Opening Range", "Opening Range context unavailable.")),
            ("Structure", "SymbolRuntime", "Vision Structure", "Vision Structure Events", context_ready("Structure", "structure_context"), method_timestamp, context_reason("Structure", "Structure context unavailable.")),
            ("Liquidity", "SymbolRuntime", "Vision Liquidity", "Vision Structure Events", context_ready("Liquidity", "liquidity_context"), method_timestamp, context_reason("Liquidity", "Liquidity context unavailable.")),
            ("Structure Events", "SymbolRuntime", "Vision Structure Events", "Setup Qualification", context_ready("Structure Events", "structure_event_context"), method_timestamp, context_reason("Structure Events", "Structure Events context unavailable.")),
            ("Setup Qualification", "SymbolRuntime", "Vision Setup Qualification", "Option Confirmation", context_ready("Setup Qualification", "setup_qualification_context"), method_timestamp, context_reason("Setup Qualification", "Setup Qualification context unavailable.")),
            ("Option Feed", "SymbolRuntime", "Live Option Chain Feed", "OptionChainSnapshot", option_status.feed_status == "READY", option_status.last_update, option_reason),
            ("Option Snapshot", "SymbolRuntime", "OptionChainEngine", "OptionChainAnalytics", option_snapshot_ready, option_status.last_update, option_reason),
            ("Option Analytics", "SymbolRuntime", "OptionChainAnalyticsEngine", "Vision Option Confirmation", option_analytics_ready, option_status.last_update, option_reason),
            ("Option Confirmation", "SymbolRuntime", "Vision Option Confirmation", "Vision Method Calculator", context_ready("Option Confirmation", "option_confirmation_context"), method_timestamp, context_reason("Option Confirmation", "Vision option confirmation unavailable.")),
            ("Vision Method", "SymbolRuntime", "Vision Method Calculator", "Vision Validation", method_snapshot is not None, method_timestamp, "Vision Method snapshot unavailable."),
            ("Validation", "SymbolRuntime", "Vision Method Validation", "Runtime Adapter", validation is not None, validation_timestamp, "Validation report unavailable."),
            ("Runtime Adapter", "SymbolRuntime", "VisionRuntimeAdapter", "TradeCandidate", candidate is not None, candidate_timestamp, "TradeCandidate not evaluated."),
            ("TradeCandidate", "SymbolRuntime", "TradeCandidate", "RiskManagementV2", candidate is not None and actionable_candidate, candidate_timestamp, trade_candidate_detail),
            ("Strategy", "SymbolRuntime", "Vision Runtime Adapter", "RiskManagementV2", strategy_ready, getattr(self._vision_strategy_decision_v2, "timestamp", None), "NOT_APPLICABLE - No actionable candidate." if not actionable_candidate else "Strategy waiting for Vision trade candidate."),
            ("Risk", "SymbolRuntime", "RiskManagementV2", "TradeLifecycleV1", risk_ready, getattr(risk, "timestamp", None), risk_detail),
            ("Lifecycle", "SymbolRuntime", "TradeLifecycleV1", "PositionManagementV1", lifecycle_ready, getattr(lifecycle, "timestamp", None), lifecycle_detail),
            ("Paper Position", "SymbolRuntime", "PositionManagementV1", "TradeJournalV1", paper_ready, getattr(canonical_position, "updated_at", None), "No canonical Vision paper position."),
            ("Paper Trade", "SymbolRuntime", "PositionManagementV1", "TradeJournalV1", paper_ready, getattr(canonical_position, "updated_at", None), "No canonical Vision paper position."),
            ("Journal", "SymbolRuntime", "TradeJournalV1", "Dashboard", journal_ready, getattr(journal, "timestamp", None), "No journal entry."),
            ("AI Explanation", "SymbolRuntime", "Vision Method Explanation", "Dashboard AI", bool(self._vision_ai_explanation), candidate_timestamp, "Vision explanation unavailable."),
        )
        state = recovery_state()
        return tuple(
            RuntimeVerificationStage(
                stage=stage,
                owner=owner,
                producer=producer,
                consumer=consumer,
                timestamp=stage_timestamp,
                session=runtime_session,
                status=status_for(stage, ready, detail),
                blocking_reason="-" if ready else detail,
                latency_ms=latency_for(stage_timestamp),
                recovery_state=state,
                prerequisites=stage_contract(stage)[0],
                readiness_conditions=stage_contract(stage)[1],
                blocking_conditions=stage_contract(stage)[2],
            )
            for stage, owner, producer, consumer, ready, stage_timestamp, detail in rows
        )

    def _runtime_diagnostics(self, market_timestamp: datetime | None, runtime_session: RuntimeTradingSession) -> RuntimeDiagnostics:
        audit = self._decision_audit
        candidate = self._vision_trade_candidate
        lifecycle = self.trade_lifecycle_v1.snapshot()
        journal = self.trade_journal_v1_engine.snapshot()
        canonical_position = self._canonical_paper_position()
        validation = self._vision_method_validation_report
        method_snapshot = self._vision_method_snapshot
        if audit is not None and audit.rejected:
            current_stage = f"Blocked: {audit.rejected_at}"
            blocking_stage = audit.rejected_at
        elif candidate is not None:
            current_stage = "Trade Candidate"
            blocking_stage = "NONE"
        elif method_snapshot is not None:
            current_stage = "Vision Method"
            blocking_stage = "NONE"
        else:
            current_stage = "Market Data"
            blocking_stage = "NONE"
        return RuntimeDiagnostics(
            current_stage=current_stage,
            blocking_stage=blocking_stage,
            current_candidate=getattr(getattr(candidate, "candidate_state", None), "value", "not_evaluated"),
            paper_trade_state=_canonical_paper_trade_state(self._canonical_paper_position(), self.paper_trading_engine.snapshot()),
            journal_state=_journal_state(journal),
            last_successful_snapshot=method_snapshot.timestamp.isoformat() if method_snapshot is not None else "-",
            last_validation=getattr(getattr(validation, "validation_result", None), "value", "-"),
            market_timestamp=market_timestamp,
            trading_date=runtime_session.trading_date,
        )

    def _build_risk_management_v2_input(self, strategy) -> RiskManagementV2Input:
        entry = _positive_price(getattr(strategy, "current_price", None))
        if entry is None and self._last_tick is not None:
            entry = _positive_price(self._last_tick.last_price)
        if entry is None:
            raise ValueError("entry price is unavailable")

        invalidation = self._risk_invalidation_price(strategy, entry)
        objective = self._risk_objective_price(strategy, entry, invalidation)
        account_equity = self._runtime_account_equity()
        account = AccountRiskStateV2(
            strategy.timestamp,
            account_equity,
            account_equity,
            account_equity,
            account_equity,
            0.0,
            0.0,
            self._current_notional_exposure(entry),
        )
        previous_risk = self.risk_management_v2_engine.snapshot
        if previous_risk is not None and previous_risk.session.trading_date == strategy.timestamp.date():
            session = previous_risk.session
        else:
            session = SessionRiskState(strategy.timestamp.date(), 0, 0, 0, 0, 0.0)
        exposure = InstrumentExposureState(
            self._core_instrument,
            self._current_position_quantity(),
            self._current_notional_exposure(entry),
            self._current_open_risk(entry),
        )
        return RiskManagementV2Input(
            strategy=strategy,
            account=account,
            session=session,
            instrument_exposure=exposure,
            proposed_entry_price=entry,
            proposed_invalidation_price=invalidation,
            proposed_objective_price=objective,
        )

    def _risk_invalidation_price(self, strategy, entry: float) -> float:
        reference = getattr(getattr(strategy, "invalidation_reference", None), "price", None)
        candidate = _positive_price(reference)
        if _valid_invalidation(strategy.direction, entry, candidate):
            return candidate
        closed = self._latest_closed_primary_candle()
        if closed is not None:
            candidate = closed.low if strategy.direction is StrategyDirection.LONG else closed.high
            if _valid_invalidation(strategy.direction, entry, candidate):
                return float(candidate)
        offset = max(entry * 0.005, 0.05)
        return round(entry - offset, 4) if strategy.direction is StrategyDirection.LONG else round(entry + offset, 4)

    def _risk_objective_price(self, strategy, entry: float, invalidation: float) -> float:
        for objective in getattr(strategy, "objectives", ()) or ():
            candidate = _positive_price(getattr(getattr(objective, "reference", None), "price", None))
            if _valid_objective(strategy.direction, entry, candidate):
                return candidate
        risk_distance = abs(entry - invalidation)
        ratio = getattr(getattr(self.risk_management_v2_engine, "_configuration", None), "minimum_reward_risk_ratio", 1.5)
        reward_distance = risk_distance * ratio
        if strategy.direction is StrategyDirection.LONG:
            return round(entry + reward_distance, 4)
        return round(entry - reward_distance, 4)

    def _latest_closed_primary_candle(self):
        history = self.candle_engine.get_history(self._core_instrument)
        return history[-1] if history else None

    def _runtime_account_equity(self) -> float:
        risk_configuration = self._configuration.risk_configuration
        capital = getattr(risk_configuration, "capital", None)
        return float(capital) if capital is not None else 100000.0

    def _current_position_quantity(self) -> int:
        position = self.position_management_v1_engine.snapshot().active_position
        return position.open_quantity if position is not None else 0

    def _current_notional_exposure(self, price: float) -> float:
        position = self.position_management_v1_engine.snapshot().active_position
        if position is None:
            return 0.0
        return round(position.open_quantity * price, 4)

    def _current_open_risk(self, price: float) -> float:
        position = self.position_management_v1_engine.snapshot().active_position
        if position is None:
            return 0.0
        return round(position.open_quantity * abs(price - position.invalidation_price), 4)

    def _process_trade_lifecycle_price(self, tick: Tick) -> None:
        if not self.trade_lifecycle_v1.snapshot().position_snapshot.has_open_position:
            return
        try:
            lifecycle = self.trade_lifecycle_v1.update_position_price(
                PositionPriceUpdate(self._core_instrument, tick.timestamp, tick.last_price)
            )
        except Exception as exc:
            self._record_decision_audit("Lifecycle", f"Trade Lifecycle V1 price update failed: {_safe_error(exc)}")
            return
        if lifecycle.stage.value == "position_closed":
            try:
                result = self.trade_journal_v1_engine.record(lifecycle)
                if getattr(result, "entry", None) is not None:
                    self._last_journal_write_timestamp = result.entry.closed_at
                self.trade_journal_v1_engine.clear_checkpoint()
                self._paper_recovery = self.trade_journal_v1_engine.load_checkpoint(expected_instrument=self._core_instrument, trading_date=tick.timestamp.date())
            except Exception as exc:
                self._record_decision_audit(
                    "Journal",
                    f"Trade Journal V1 rejected the closed lifecycle: {_safe_error(exc)}",
                    trade_lifecycle_v1=lifecycle,
                )
        else:
            self._sync_paper_checkpoint()

    def _record_decision_audit(
        self,
        rejected_at: str,
        reason: str,
        *,
        rejected: bool = True,
        ai_reasoning_v2=None,
        strategy_decision_v2=None,
        risk_management_v2=None,
        trade_lifecycle_v1=None,
        vision_trade_candidate=None,
    ) -> None:
        timestamp = (
            getattr(trade_lifecycle_v1, "timestamp", None)
            or getattr(risk_management_v2, "timestamp", None)
            or getattr(strategy_decision_v2, "timestamp", None)
            or getattr(ai_reasoning_v2, "timestamp", None)
            or getattr(vision_trade_candidate, "timestamp", None)
            or getattr(self._last_tick, "timestamp", None)
        )
        if timestamp is None:
            return
        self._decision_audit = RuntimeDecisionAudit(
            instrument=self._instrument,
            timestamp=timestamp,
            rejected=rejected,
            rejected_at=str(rejected_at).strip() or "UNKNOWN",
            reason=str(reason).strip() or "No decision reason supplied.",
            ai_reasoning_v2=ai_reasoning_v2 or self.ai_reasoning_v2_engine.snapshot,
            strategy_decision_v2=strategy_decision_v2 or self.strategy_decision_v2_engine.snapshot,
            risk_management_v2=risk_management_v2 or self.risk_management_v2_engine.snapshot,
            trade_lifecycle_v1=trade_lifecycle_v1 or self.trade_lifecycle_v1.snapshot(),
            vision_trade_candidate=vision_trade_candidate or self._vision_trade_candidate,
        )

    def _append_daily_ohlc(self, daily_ohlc: DailyOHLC) -> None:
        existing = {item.trading_date: item for item in self._daily_ohlc_history}
        existing[daily_ohlc.trading_date] = daily_ohlc
        self._daily_ohlc_history = tuple(existing[key] for key in sorted(existing))

    def _ensure_daily_context_for_session(self, timestamp: datetime) -> None:
        active_date = timestamp.date()
        if (
            self.cpr is not None
            and self.camarilla is not None
            and self.cpr.trading_date == active_date
            and self.camarilla.trading_date == active_date
        ):
            return
        previous_sessions = tuple(item for item in self._daily_ohlc_history if item.trading_date < active_date)
        if not previous_sessions:
            return
        self.process_daily_ohlc(previous_sessions[-1], levels_trading_date=active_date)

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


def _positive_price(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number > 0.0 else None


def _valid_invalidation(direction, entry: float, candidate: float | None) -> bool:
    if candidate is None:
        return False
    if direction is StrategyDirection.LONG:
        return candidate < entry
    if direction is StrategyDirection.SHORT:
        return candidate > entry
    return False


def _valid_objective(direction, entry: float, candidate: float | None) -> bool:
    if candidate is None:
        return False
    if direction is StrategyDirection.LONG:
        return candidate > entry
    if direction is StrategyDirection.SHORT:
        return candidate < entry
    return False


def _is_actionable_vision_candidate(candidate: TradeCandidate) -> bool:
    return (
        candidate.direction in {TradeCandidateDirection.LONG, TradeCandidateDirection.SHORT}
        and candidate.candidate_state in {TradeCandidateState.LONG, TradeCandidateState.SHORT}
    )


def _vision_trade_identity(candidate: TradeCandidate) -> str:
    return ":".join(
        (
            "vision_trade_candidate",
            candidate.instrument.value,
            candidate.timeframe.value,
            candidate.timestamp.isoformat(),
            candidate.candidate_state.value,
            candidate.direction.value,
            candidate.snapshot_reference,
            candidate.validation_reference,
        )
    )


def _daily_ohlc_for_levels(daily_ohlc: DailyOHLC, trading_date: date | None) -> DailyOHLC:
    if trading_date is None or trading_date == daily_ohlc.trading_date:
        return daily_ohlc
    return replace(daily_ohlc, trading_date=trading_date)


def _strategy_quality_from_vision(quality: str) -> StrategyDecisionQuality:
    normalized = str(quality).strip().lower()
    if normalized == "high":
        return StrategyDecisionQuality.HIGH
    if normalized == "medium":
        return StrategyDecisionQuality.MODERATE
    if normalized == "low":
        return StrategyDecisionQuality.LOW
    return StrategyDecisionQuality.UNAVAILABLE


def _confidence_from_vision(quality: str) -> float:
    normalized = str(quality).strip().lower()
    if normalized == "high":
        return 0.85
    if normalized == "medium":
        return 0.65
    if normalized == "low":
        return 0.4
    return 0.0


def _vision_method_explanation(candidate: TradeCandidate, validation_report: VisionMethodValidationReport) -> str:
    status = getattr(validation_report.validation_result, "value", "unknown")
    if candidate.direction is TradeCandidateDirection.NONE:
        return f"Vision Method is observing only: {candidate.reason} Validation result: {status}."
    return (
        f"Vision Method produced a {candidate.direction.value} candidate from {candidate.candidate_state.value}. "
        f"Entry reference: {candidate.entry_zone}. "
        f"Invalidation reference: {candidate.stop_loss_zone}. "
        f"Target reference: {candidate.target_zone}. "
        f"Validation result: {status}."
    )



def _vision_journal_path(instrument: RuntimeInstrument) -> Path:
    return Path("data") / "trade_journal_v1" / f"{instrument.value.lower()}_vision_journal.jsonl"


def _vision_checkpoint_path(instrument: RuntimeInstrument) -> Path:
    return Path("data") / "trade_journal_v1" / f"{instrument.value.lower()}_active_checkpoint.json"
def _canonical_paper_trade_state(canonical: RuntimePaperPositionSnapshot | None, legacy_snapshot) -> str:
    if canonical is not None:
        return f"VISION_METHOD:{canonical.status}"
    return _paper_trade_state(legacy_snapshot)

def _paper_trade_state(snapshot) -> str:
    if snapshot is None:
        return "not_available"
    if getattr(snapshot, "position", None) is not None:
        return getattr(snapshot.position.state, "value", "position")
    if getattr(snapshot, "order", None) is not None:
        return getattr(snapshot.order.state, "value", "order")
    event = getattr(snapshot, "last_event", None)
    return str(event).strip() if event else "idle"


def _journal_state(snapshot) -> str:
    if snapshot is None:
        return "not_available"
    status = getattr(getattr(snapshot, "status", None), "value", None)
    count = getattr(snapshot, "trade_count", 0)
    return f"{status or 'unknown'}:{count}"


def _strategy_rejection_reason(strategy) -> str:
    notes = tuple(getattr(strategy, "rationale", ()) or ())
    warnings = tuple(getattr(strategy, "warnings", ()) or ())
    detail = next((item for item in (*notes, *warnings) if str(item).strip()), None)
    if detail:
        return str(detail)
    return f"Strategy Decision V2 rejected at {strategy.setup_status.value}."


def _risk_rejection_reason(risk) -> str:
    failed = next((item for item in risk.rule_evaluations if item.result.value == "failed"), None)
    if failed is not None:
        return failed.message
    return f"Risk Management V2 rejected at {risk.status.value}."


def _lifecycle_rejection_reason(lifecycle) -> str:
    if lifecycle.stage_records:
        return lifecycle.stage_records[-1].message
    return f"Trade Lifecycle V1 stopped at {lifecycle.stage.value}."


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("token", "[redacted]").replace("credential", "[redacted]")
