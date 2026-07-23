"""
Immutable Application Orchestrator V1 models.
"""

from dataclasses import dataclass
from datetime import date, datetime

from application.enums import ExecutionSafetyMode, RuntimeInstrument, RuntimeStatus
from adapters.zerodha.models import ZerodhaConnectionSnapshot
from brokers.zerodha.enums import BrokerExecutionMode
from core.enums.timeframe import TimeFrame
from core.models.building_candle import BuildingCandle
from core.models.candle import Candle
from core.models.tick import Tick
from engines.ai_reasoning.models import AIReasoningState
from engines.ai_confidence_calibration.models import ConfidenceCalibrationSnapshot
from engines.adr.models import ADRDiagnosticSnapshot, ADRSnapshot
from engines.camarilla.levels import CamarillaLevels
from engines.chart_explanation.models import ChartExplanationEngineSnapshot
from engines.cpr.levels import CPRLevels
from engines.market_context.models import MarketContextState
from engines.moving_average_context.models import (
    MovingAverageContextDiagnosticSnapshot,
    MovingAverageContextProfile,
    MovingAverageContextSnapshot,
)
from engines.momentum_context.models import (
    MomentumContextDiagnosticSnapshot,
    MomentumContextProfile,
    MomentumContextSnapshot,
)
from engines.expert_setup_classification.models import ExpertSetupClassificationEngineSnapshot
from engines.market_state.models import MarketStateEngineSnapshot
from engines.multi_timeframe_evidence_fusion.models import MultiTimeframeEvidenceFusionSnapshot
from engines.volume_context.models import (
    VolumeContextDiagnosticSnapshot,
    VolumeContextProfile,
    VolumeContextSnapshot,
)
from engines.option_chain.models import OptionChainState
from engines.order_management.models import OrderState
from engines.paper_trading.configuration import PaperTradingConfiguration
from engines.paper_trading.models import PaperTradingSnapshot
from engines.paper_execution_coordinator.models import PaperExecutionCoordinatorSnapshot
from engines.performance_analytics.configuration import PerformanceAnalyticsConfiguration
from engines.performance_analytics.models import AnalyticsSnapshot
from engines.historical_market_replay.models import ReplayConfiguration, ReplaySessionSnapshot
from engines.deterministic_backtest.models import BacktestConfiguration, BacktestSnapshot
from engines.live_market_validation.models import LiveMarketValidationConfiguration, ValidationSessionSnapshot
from application.live_shadow_session.models import LiveShadowSessionSnapshot
from application.authorized_paper_execution.models import AuthorizedPaperHandoffSnapshot
from engines.position.models import PositionState
from engines.price_action.models import PriceActionState
from engines.risk.models import RiskConfiguration, RiskDecisionState
from engines.strategy.models import StrategyDecisionState
from engines.trade_decision_authorization.models import TradeAuthorizationSnapshot
from engines.trade_journal.models import TradeJournalRecord
from engines.trade_execution_policy.models import ExecutionEngineSnapshot
from engines.execution_reconciliation.models import ExecutionReconciliationSnapshot
from engines.shadow_trading_session.models import ShadowTradingSessionSnapshot
from engines.vwap.levels import VWAPLevels
from engines.tradingview_evidence.models import TradingViewEvidenceEngineSnapshot


@dataclass(frozen=True, slots=True)
class RuntimeVWAPSource:
    instrument: RuntimeInstrument
    source_type: str
    source_exchange: str
    trading_symbol: str
    instrument_token: int
    expiry: date | None
    cumulative_volume: int
    last_source_price: float | None
    updated_at: datetime | None
    ready: bool
    unavailable_reason: str | None = None
    state: str = "-"
    message: str = "-"
    subscription_active: bool = False
    historical_candles_loaded: int = 0
    historical_volume: int = 0
    historical_seed_complete: bool = False
    bootstrap_time: datetime | None = None
    live_tick_count: int = 0
    last_live_volume: int = 0
    last_delta_volume: int = 0
    last_live_tick: datetime | None = None
    current_accumulated_volume: int = 0
    last_error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        for field_name in ("source_type", "source_exchange", "trading_symbol"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty text")
            object.__setattr__(self, field_name, value.strip())
        if isinstance(self.instrument_token, bool) or not isinstance(self.instrument_token, int) or self.instrument_token <= 0:
            raise ValueError("instrument_token must be a positive integer")
        if self.expiry is not None and (isinstance(self.expiry, datetime) or not isinstance(self.expiry, date)):
            raise TypeError("expiry must be a date or None")
        if isinstance(self.cumulative_volume, bool) or not isinstance(self.cumulative_volume, int) or self.cumulative_volume < 0:
            raise ValueError("cumulative_volume must be a non-negative integer")
        if self.last_source_price is not None:
            if isinstance(self.last_source_price, bool) or not isinstance(self.last_source_price, (int, float)):
                raise TypeError("last_source_price must be numeric or None")
            object.__setattr__(self, "last_source_price", float(self.last_source_price))
        if self.updated_at is not None:
            if not isinstance(self.updated_at, datetime):
                raise TypeError("updated_at must be datetime or None")
        if not isinstance(self.ready, bool):
            raise TypeError("ready must be bool")
        if not isinstance(self.subscription_active, bool):
            raise TypeError("subscription_active must be bool")
        if not isinstance(self.historical_seed_complete, bool):
            raise TypeError("historical_seed_complete must be bool")
        for field_name in (
            "historical_candles_loaded",
            "historical_volume",
            "live_tick_count",
            "last_live_volume",
            "last_delta_volume",
            "current_accumulated_volume",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.bootstrap_time is not None and not isinstance(self.bootstrap_time, datetime):
            raise TypeError("bootstrap_time must be datetime or None")
        if self.last_live_tick is not None and not isinstance(self.last_live_tick, datetime):
            raise TypeError("last_live_tick must be datetime or None")
        for field_name in ("state", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")
        if self.unavailable_reason is not None:
            if not isinstance(self.unavailable_reason, str):
                raise TypeError("unavailable_reason must be text or None")
            object.__setattr__(self, "unavailable_reason", self.unavailable_reason.strip() or None)
        if self.last_error is not None:
            if not isinstance(self.last_error, str):
                raise TypeError("last_error must be text or None")
            object.__setattr__(self, "last_error", self.last_error.strip() or None)


@dataclass(frozen=True, slots=True)
class RuntimeConfiguration:
    instruments: tuple[RuntimeInstrument, ...] = (RuntimeInstrument.NIFTY,)
    exchange: str = "NSE"
    timeframe: str = "1m"
    timeframes: tuple[str, ...] | None = None
    option_expiry_date: date = date(1970, 1, 1)
    safety_mode: ExecutionSafetyMode = ExecutionSafetyMode.ANALYSIS_ONLY
    risk_configuration: RiskConfiguration | None = None
    paper_trading_configuration: PaperTradingConfiguration | None = None
    performance_analytics_configuration: PerformanceAnalyticsConfiguration | None = None
    live_validation_configuration: LiveMarketValidationConfiguration | None = None
    historical_replay_configuration: ReplayConfiguration | None = None
    deterministic_backtest_configuration: BacktestConfiguration | None = None
    adr_period: int = 20
    moving_average_periods: tuple[int, ...] = (20, 50, 200)
    momentum_period: int = 14
    volume_lookback: int = 20

    def __post_init__(self) -> None:
        if not isinstance(self.instruments, tuple) or not self.instruments:
            raise ValueError("RuntimeConfiguration instruments must be a non-empty tuple.")
        normalized = []
        for instrument in self.instruments:
            if not isinstance(instrument, RuntimeInstrument):
                raise ValueError("RuntimeConfiguration supports only RuntimeInstrument values.")
            if instrument in normalized:
                raise ValueError("RuntimeConfiguration instruments must be unique.")
            normalized.append(instrument)
        if not isinstance(self.exchange, str) or not self.exchange.strip():
            raise ValueError("RuntimeConfiguration exchange cannot be empty.")
        timeframes = _normalize_runtime_timeframes(self.timeframe, self.timeframes)
        timeframe = timeframes[0]
        if not isinstance(self.option_expiry_date, date) or isinstance(self.option_expiry_date, datetime):
            raise ValueError("RuntimeConfiguration option_expiry_date must be a date.")
        if not isinstance(self.safety_mode, ExecutionSafetyMode):
            raise ValueError("RuntimeConfiguration safety_mode must be an ExecutionSafetyMode.")
        if self.risk_configuration is not None and not isinstance(self.risk_configuration, RiskConfiguration):
            raise TypeError("RuntimeConfiguration risk_configuration must be RiskConfiguration or None.")
        if self.paper_trading_configuration is not None and not isinstance(self.paper_trading_configuration, PaperTradingConfiguration):
            raise TypeError("RuntimeConfiguration paper_trading_configuration must be PaperTradingConfiguration or None.")
        if self.performance_analytics_configuration is not None and not isinstance(self.performance_analytics_configuration, PerformanceAnalyticsConfiguration):
            raise TypeError("RuntimeConfiguration performance_analytics_configuration must be PerformanceAnalyticsConfiguration or None.")
        if self.live_validation_configuration is not None and not isinstance(self.live_validation_configuration, LiveMarketValidationConfiguration):
            raise TypeError("RuntimeConfiguration live_validation_configuration must be LiveMarketValidationConfiguration or None.")
        if self.historical_replay_configuration is not None and not isinstance(self.historical_replay_configuration, ReplayConfiguration):
            raise TypeError("RuntimeConfiguration historical_replay_configuration must be ReplayConfiguration or None.")
        if self.deterministic_backtest_configuration is not None and not isinstance(self.deterministic_backtest_configuration, BacktestConfiguration):
            raise TypeError("RuntimeConfiguration deterministic_backtest_configuration must be BacktestConfiguration or None.")
        if isinstance(self.adr_period, bool) or not isinstance(self.adr_period, int) or self.adr_period not in {5, 10, 20, 50}:
            raise ValueError("RuntimeConfiguration adr_period must be one of 5, 10, 20 or 50.")
        moving_average_profile = MovingAverageContextProfile(self.moving_average_periods)
        momentum_profile = MomentumContextProfile(self.momentum_period)
        volume_profile = VolumeContextProfile(self.volume_lookback)
        object.__setattr__(self, "instruments", tuple(normalized))
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "timeframes", timeframes)
        object.__setattr__(self, "moving_average_periods", moving_average_profile.periods)
        object.__setattr__(self, "momentum_period", momentum_profile.period)
        object.__setattr__(self, "volume_lookback", volume_profile.lookback)


def _normalize_runtime_timeframes(
    timeframe: str,
    timeframes: tuple[str, ...] | None,
) -> tuple[str, ...]:
    allowed = {
        TimeFrame.ONE_MINUTE,
        TimeFrame.THREE_MINUTES,
        TimeFrame.FIVE_MINUTES,
        TimeFrame.FIFTEEN_MINUTES,
        TimeFrame.THIRTY_MINUTES,
    }
    if timeframes is None:
        candidates = (timeframe,)
    else:
        if not isinstance(timeframes, tuple) or not timeframes:
            raise ValueError("RuntimeConfiguration timeframes must be a non-empty tuple when provided.")
        candidates = timeframes

    normalized: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            raise ValueError("RuntimeConfiguration timeframe values cannot be empty.")
        parsed = TimeFrame.from_value(candidate.strip())
        if parsed not in allowed:
            raise ValueError("RuntimeConfiguration supports only 1m, 3m, 5m, 15m and 30m runtime lanes.")
        if parsed.value in normalized:
            raise ValueError("RuntimeConfiguration timeframes must be unique.")
        normalized.append(parsed.value)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    symbol: RuntimeInstrument
    timeframe: str
    status: RuntimeStatus
    latest_tick: Tick | None
    latest_candle: BuildingCandle | Candle | None
    vwap: VWAPLevels | None
    cpr: CPRLevels | None
    camarilla: CamarillaLevels | None
    price_action: PriceActionState | None
    option_chain: OptionChainState | None
    market_context: MarketContextState | None
    ai_reasoning: AIReasoningState | None
    strategy: StrategyDecisionState | None
    risk: RiskDecisionState | None
    latest_order: OrderState | None
    position: PositionState | None
    latest_journal_record: TradeJournalRecord | None
    updated_at: datetime | None
    vwap_source: RuntimeVWAPSource | None = None
    paper_trading: PaperTradingSnapshot | None = None
    performance_analytics: AnalyticsSnapshot | None = None
    execution_policy: ExecutionEngineSnapshot | None = None
    paper_execution: PaperExecutionCoordinatorSnapshot | None = None
    execution_reconciliation: ExecutionReconciliationSnapshot | None = None
    shadow_trading_session: ShadowTradingSessionSnapshot | None = None
    confidence_calibration: ConfidenceCalibrationSnapshot | None = None
    trade_authorization: TradeAuthorizationSnapshot | None = None
    tradingview_evidence: TradingViewEvidenceEngineSnapshot | None = None
    adr: ADRSnapshot | None = None
    adr_diagnostics: ADRDiagnosticSnapshot | None = None
    moving_average_context: MovingAverageContextSnapshot | None = None
    moving_average_context_diagnostics: MovingAverageContextDiagnosticSnapshot | None = None
    momentum_context: MomentumContextSnapshot | None = None
    momentum_context_diagnostics: MomentumContextDiagnosticSnapshot | None = None
    volume_context: VolumeContextSnapshot | None = None
    volume_context_diagnostics: VolumeContextDiagnosticSnapshot | None = None
    multi_timeframe_evidence: MultiTimeframeEvidenceFusionSnapshot | None = None
    market_state: MarketStateEngineSnapshot | None = None
    setup_classification: ExpertSetupClassificationEngineSnapshot | None = None
    chart_explanation: ChartExplanationEngineSnapshot | None = None


@dataclass(frozen=True, slots=True)
class OrchestratorSnapshot:
    status: RuntimeStatus
    safety_mode: ExecutionSafetyMode
    broker_mode: BrokerExecutionMode
    configured_instruments: tuple[RuntimeInstrument, ...]
    shared_market_data_ready: bool
    shared_trade_journal_ready: bool
    runtime_snapshots: tuple[RuntimeSnapshot, ...]
    performance_analytics: AnalyticsSnapshot | None = None
    live_validation: ValidationSessionSnapshot | None = None
    historical_replay: ReplaySessionSnapshot | None = None
    deterministic_backtest: BacktestSnapshot | None = None
    zerodha_connection: ZerodhaConnectionSnapshot | None = None
    live_shadow_session: LiveShadowSessionSnapshot | None = None
    authorized_paper_handoff: AuthorizedPaperHandoffSnapshot | None = None
