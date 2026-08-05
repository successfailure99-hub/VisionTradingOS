"""
Immutable Application Orchestrator V1 models.
"""

from __future__ import annotations

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
from engines.ai_reasoning_v2.models import AIReasoningV2Snapshot
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
from engines.option_chain.models import OptionChainSnapshot, OptionChainState
from engines.option_chain_analytics.models import OptionChainAnalyticsSnapshot
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
from application.broker_account_sync.models import BrokerAccountSnapshot, BrokerRuntimeVerificationStage
from application.broker_session_persistence import BrokerSessionPersistenceSnapshot
from application.runtime_contract import RuntimeContractReport
from engines.position.models import PositionState
from engines.price_action.models import PriceActionState
from engines.risk.models import RiskConfiguration, RiskDecisionState
from engines.risk_management_v2.models import RiskManagementV2Snapshot
from engines.runtime_adapter.models import TradeCandidate
from engines.strategy.models import StrategyDecisionState
from engines.strategy_decision_v2.models import StrategyDecisionV2Snapshot
from application.trade_lifecycle_v1.models import TradeLifecycleV1Snapshot
from engines.trade_journal_v1.models import TradeJournalV1Snapshot
from engines.trade_decision_authorization.models import TradeAuthorizationSnapshot
from engines.trade_journal.models import TradeJournalRecord
from engines.trade_execution_policy.models import ExecutionEngineSnapshot
from engines.execution_reconciliation.models import ExecutionReconciliationSnapshot
from engines.shadow_trading_session.models import ShadowTradingSessionSnapshot
from engines.vwap.levels import VWAPLevels
from engines.tradingview_evidence.models import TradingViewEvidenceEngineSnapshot
from engines.vision_method import VisionMethodSnapshot, VisionMethodValidationReport


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
class RuntimeDiagnostics:
    current_stage: str
    blocking_stage: str
    current_candidate: str
    paper_trade_state: str
    journal_state: str
    last_successful_snapshot: str
    last_validation: str
    market_timestamp: datetime | None = None
    trading_date: date | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "current_stage",
            "blocking_stage",
            "current_candidate",
            "paper_trade_state",
            "journal_state",
            "last_successful_snapshot",
            "last_validation",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be str")
            object.__setattr__(self, field_name, value.strip() or "-")
        if self.market_timestamp is not None and not isinstance(self.market_timestamp, datetime):
            raise TypeError("market_timestamp must be datetime or None")
        if self.trading_date is not None and (isinstance(self.trading_date, datetime) or not isinstance(self.trading_date, date)):
            raise TypeError("trading_date must be date or None")


@dataclass(frozen=True, slots=True)
class RuntimePaperPositionSnapshot:
    trade_id: str
    instrument: RuntimeInstrument
    source: str
    candidate_state: str
    direction: str
    status: str
    lifecycle_state: str
    risk_state: str
    candidate_reference: str
    vision_method_snapshot_reference: str
    validation_report_reference: str
    risk_reference: str
    entry_timestamp: datetime | None
    entry_price: float | None
    current_price: float | None
    quantity: int
    stop_reference: str
    target_reference: str
    stop_price: float | None
    target_price: float | None
    gross_pnl: float
    fees: float
    slippage: float
    net_pnl: float
    unrealized_pnl: float
    realized_pnl: float
    blocking_reason: str
    recovery_status: str
    updated_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        for field_name in (
            "trade_id",
            "source",
            "candidate_state",
            "direction",
            "status",
            "lifecycle_state",
            "risk_state",
            "candidate_reference",
            "vision_method_snapshot_reference",
            "validation_report_reference",
            "risk_reference",
            "stop_reference",
            "target_reference",
            "blocking_reason",
            "recovery_status",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be str")
            object.__setattr__(self, field_name, value.strip() or "-")
        for field_name in ("entry_timestamp", "updated_at"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be datetime or None")
        for field_name in ("entry_price", "current_price", "stop_price", "target_price"):
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError(f"{field_name} must be numeric or None")
                object.__setattr__(self, field_name, float(value))
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity < 0:
            raise ValueError("quantity must be a non-negative integer")
        for field_name in ("gross_pnl", "fees", "slippage", "net_pnl", "unrealized_pnl", "realized_pnl"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{field_name} must be numeric")
            object.__setattr__(self, field_name, float(value))

@dataclass(frozen=True, slots=True)
class RuntimeTradingSession:
    instrument: RuntimeInstrument
    exchange: str
    market_timestamp: datetime | None
    trading_date: date | None
    previous_completed_trading_date: date | None
    cpr_trading_date: date | None
    camarilla_trading_date: date | None
    adr_trading_date: date | None
    vwap_trading_date: date | None
    status: str
    blocking_reason: str = "-"

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        if not isinstance(self.exchange, str) or not self.exchange.strip():
            raise ValueError("exchange must be non-empty text")
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        if self.market_timestamp is not None and not isinstance(self.market_timestamp, datetime):
            raise TypeError("market_timestamp must be datetime or None")
        for field_name in (
            "trading_date",
            "previous_completed_trading_date",
            "cpr_trading_date",
            "camarilla_trading_date",
            "adr_trading_date",
            "vwap_trading_date",
        ):
            value = getattr(self, field_name)
            if value is not None and (isinstance(value, datetime) or not isinstance(value, date)):
                raise TypeError(f"{field_name} must be date or None")
        for field_name in ("status", "blocking_reason"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")


@dataclass(frozen=True, slots=True)
class RuntimeVerificationStage:
    stage: str
    owner: str
    producer: str
    consumer: str
    timestamp: datetime | None
    session: RuntimeTradingSession | None
    status: str
    blocking_reason: str = "-"
    latency_ms: float | None = None
    recovery_state: str = "-"
    prerequisites: tuple[str, ...] = ()
    readiness_conditions: tuple[str, ...] = ()
    blocking_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("stage", "owner", "producer", "consumer", "status", "blocking_reason", "recovery_state"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")
        if self.timestamp is not None and not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be datetime or None")
        if self.session is not None and not isinstance(self.session, RuntimeTradingSession):
            raise TypeError("session must be RuntimeTradingSession or None")
        if self.latency_ms is not None:
            value = self.latency_ms
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError("latency_ms must be a non-negative number or None")
            object.__setattr__(self, "latency_ms", float(value))
        for field_name in ("prerequisites", "readiness_conditions", "blocking_conditions"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise TypeError(f"{field_name} must be a tuple")
            normalized = []
            for item in value:
                if not isinstance(item, str):
                    raise TypeError(f"{field_name} must contain text")
                text = item.strip()
                if text:
                    normalized.append(text)
            object.__setattr__(self, field_name, tuple(normalized))


@dataclass(frozen=True, slots=True)
class RuntimeOptionChainStatus:
    instrument: RuntimeInstrument
    market_timestamp: datetime | None
    trading_date: date | None
    feed_status: str
    snapshot_status: str
    analytics_status: str
    last_update: datetime | None
    age_seconds: float | None
    expiry: date | None
    atm_strike: float | None
    total_strikes: int
    blocking_reason: str = "-"
    state: str = "WAITING_FOR_DATA"
    recovery_condition: str = "-"
    latency_ms: float | None = None
    synchronization_status: str = "-"

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        if self.market_timestamp is not None and not isinstance(self.market_timestamp, datetime):
            raise TypeError("market_timestamp must be datetime or None")
        if self.trading_date is not None and (isinstance(self.trading_date, datetime) or not isinstance(self.trading_date, date)):
            raise TypeError("trading_date must be date or None")
        for field_name in ("feed_status", "snapshot_status", "analytics_status", "blocking_reason", "state", "recovery_condition", "synchronization_status"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")
        if self.last_update is not None and not isinstance(self.last_update, datetime):
            raise TypeError("last_update must be datetime or None")
        if self.age_seconds is not None:
            if isinstance(self.age_seconds, bool) or not isinstance(self.age_seconds, (int, float)) or self.age_seconds < 0:
                raise ValueError("age_seconds must be a non-negative number or None")
            object.__setattr__(self, "age_seconds", float(self.age_seconds))
        if self.latency_ms is not None:
            if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, (int, float)) or self.latency_ms < 0:
                raise ValueError("latency_ms must be a non-negative number or None")
            object.__setattr__(self, "latency_ms", float(self.latency_ms))
        if self.expiry is not None and (isinstance(self.expiry, datetime) or not isinstance(self.expiry, date)):
            raise TypeError("expiry must be date or None")
        if self.atm_strike is not None:
            if isinstance(self.atm_strike, bool) or not isinstance(self.atm_strike, (int, float)):
                raise TypeError("atm_strike must be numeric or None")
            object.__setattr__(self, "atm_strike", float(self.atm_strike))
        if isinstance(self.total_strikes, bool) or not isinstance(self.total_strikes, int) or self.total_strikes < 0:
            raise ValueError("total_strikes must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class RuntimeADRStatus:
    state: str
    period: int
    required_sessions: int
    loaded_sessions: int
    valid_sessions: int
    latest_history_date: date | None
    adr_trading_date: date | None
    blocking_reason: str
    recovery_condition: str
    owner: str = "SymbolRuntime"
    producer: str = "ADREngine"
    consumer: str = "Vision Level Context"

    def __post_init__(self) -> None:
        for field_name in ("state", "blocking_reason", "recovery_condition", "owner", "producer", "consumer"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")
        for field_name in ("period", "required_sessions", "loaded_sessions", "valid_sessions"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name in ("latest_history_date", "adr_trading_date"):
            value = getattr(self, field_name)
            if value is not None and (isinstance(value, datetime) or not isinstance(value, date)):
                raise TypeError(f"{field_name} must be date or None")
@dataclass(frozen=True, slots=True)
class RuntimeJournalPersistenceSnapshot:
    persistence_status: str
    active_checkpoint_status: str
    recovery_status: str
    latest_journal_record_id: str | None
    journal_write_timestamp: datetime | None
    journal_blocking_reason: str
    journal_record_count: int | None
    checkpoint_trade_id: str | None = None
    recovery_reason: str = "-"
    operational_state: str = "READY_EMPTY"
    operational_message: str = "Ready - No completed Vision paper trades"

    def __post_init__(self) -> None:
        for field_name in (
            "persistence_status",
            "active_checkpoint_status",
            "recovery_status",
            "journal_blocking_reason",
            "recovery_reason",
            "operational_state",
            "operational_message",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")
        for field_name in ("latest_journal_record_id", "checkpoint_trade_id"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be text or None")
        if self.journal_write_timestamp is not None and not isinstance(self.journal_write_timestamp, datetime):
            raise TypeError("journal_write_timestamp must be datetime or None")
        if self.journal_record_count is not None:
            if isinstance(self.journal_record_count, bool) or not isinstance(self.journal_record_count, int) or self.journal_record_count < 0:
                raise ValueError("journal_record_count must be a non-negative integer or None")

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
    latest_tick_at: datetime | None = None
    latest_closed_candle_at: datetime | None = None
    latest_analysis_at: datetime | None = None
    snapshot_created_at: datetime | None = None
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
    ai_reasoning_v2: AIReasoningV2Snapshot | None = None
    strategy_decision_v2: StrategyDecisionV2Snapshot | None = None
    risk_management_v2: RiskManagementV2Snapshot | None = None
    trade_lifecycle_v1: TradeLifecycleV1Snapshot | None = None
    trade_journal_v1: TradeJournalV1Snapshot | None = None
    vision_method_snapshot: VisionMethodSnapshot | None = None
    vision_method_validation_report: VisionMethodValidationReport | None = None
    vision_trade_candidate: TradeCandidate | None = None
    canonical_paper_position: RuntimePaperPositionSnapshot | None = None
    journal_persistence: RuntimeJournalPersistenceSnapshot | None = None
    decision_audit: "RuntimeDecisionAudit" | None = None
    runtime_diagnostics: RuntimeDiagnostics | None = None
    vision_ai_explanation: str | None = None
    runtime_session: RuntimeTradingSession | None = None
    runtime_verification_report: tuple[RuntimeVerificationStage, ...] = ()
    option_chain_snapshot: OptionChainSnapshot | None = None
    option_chain_analytics: OptionChainAnalyticsSnapshot | None = None
    option_chain_runtime: RuntimeOptionChainStatus | None = None
    adr_runtime: RuntimeADRStatus | None = None
    operational_readiness: OperationalReadinessSnapshot | None = None
    runtime_contract_report: RuntimeContractReport | None = None
    candle_history_count: int = 0

    def __post_init__(self) -> None:
        if self.runtime_session is not None and not isinstance(self.runtime_session, RuntimeTradingSession):
            raise TypeError("runtime_session must be RuntimeTradingSession or None")
        report = tuple(self.runtime_verification_report)
        for item in report:
            if not isinstance(item, RuntimeVerificationStage):
                raise TypeError("runtime_verification_report must contain RuntimeVerificationStage values")
        object.__setattr__(self, "runtime_verification_report", report)
        if self.option_chain_snapshot is not None and not isinstance(self.option_chain_snapshot, OptionChainSnapshot):
            raise TypeError("option_chain_snapshot must be OptionChainSnapshot or None")
        if self.option_chain_analytics is not None and not isinstance(self.option_chain_analytics, OptionChainAnalyticsSnapshot):
            raise TypeError("option_chain_analytics must be OptionChainAnalyticsSnapshot or None")
        if self.option_chain_runtime is not None and not isinstance(self.option_chain_runtime, RuntimeOptionChainStatus):
            raise TypeError("option_chain_runtime must be RuntimeOptionChainStatus or None")
        if self.adr_runtime is not None and not isinstance(self.adr_runtime, RuntimeADRStatus):
            raise TypeError("adr_runtime must be RuntimeADRStatus or None")
        if self.operational_readiness is not None and not isinstance(self.operational_readiness, OperationalReadinessSnapshot):
            raise TypeError("operational_readiness must be OperationalReadinessSnapshot or None")
        if self.runtime_contract_report is not None and not isinstance(self.runtime_contract_report, RuntimeContractReport):
            raise TypeError("runtime_contract_report must be RuntimeContractReport or None")
        if isinstance(self.candle_history_count, bool) or not isinstance(self.candle_history_count, int) or self.candle_history_count < 0:
            raise ValueError("candle_history_count must be a non-negative integer")
        if self.vision_method_snapshot is not None and not isinstance(self.vision_method_snapshot, VisionMethodSnapshot):
            raise TypeError("vision_method_snapshot must be VisionMethodSnapshot or None")
        if self.vision_method_validation_report is not None and not isinstance(self.vision_method_validation_report, VisionMethodValidationReport):
            raise TypeError("vision_method_validation_report must be VisionMethodValidationReport or None")
        if self.canonical_paper_position is not None and not isinstance(self.canonical_paper_position, RuntimePaperPositionSnapshot):
            raise TypeError("canonical_paper_position must be RuntimePaperPositionSnapshot or None")
        if self.journal_persistence is not None and not isinstance(self.journal_persistence, RuntimeJournalPersistenceSnapshot):
            raise TypeError("journal_persistence must be RuntimeJournalPersistenceSnapshot or None")


@dataclass(frozen=True, slots=True)
class RuntimeDecisionAudit:
    instrument: RuntimeInstrument
    timestamp: datetime
    rejected: bool
    rejected_at: str
    reason: str
    ai_reasoning_v2: AIReasoningV2Snapshot | None = None
    strategy_decision_v2: StrategyDecisionV2Snapshot | None = None
    risk_management_v2: RiskManagementV2Snapshot | None = None
    trade_lifecycle_v1: TradeLifecycleV1Snapshot | None = None
    vision_trade_candidate: TradeCandidate | None = None


@dataclass(frozen=True, slots=True)
class OperationalReadinessSnapshot:
    overall_state: str
    live_analysis_ready: bool
    vision_evaluation_ready: bool
    paper_trading_ready: bool
    journal_ready: bool
    broker_read_only_ready: bool
    mandatory_blockers: tuple[str, ...]
    optional_degradations: tuple[str, ...]
    intentional_disabled_features: tuple[str, ...]
    timestamp: datetime | None
    session: RuntimeTradingSession | None
    primary_blocker: str = "-"

    def __post_init__(self) -> None:
        if not isinstance(self.overall_state, str) or not self.overall_state.strip():
            raise ValueError("overall_state must be non-empty text")
        object.__setattr__(self, "overall_state", self.overall_state.strip())
        for field_name in (
            "live_analysis_ready",
            "vision_evaluation_ready",
            "paper_trading_ready",
            "journal_ready",
            "broker_read_only_ready",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be bool")
        for field_name in ("mandatory_blockers", "optional_degradations", "intentional_disabled_features"):
            values = tuple(getattr(self, field_name))
            for value in values:
                if not isinstance(value, str):
                    raise TypeError(f"{field_name} must contain text")
            object.__setattr__(self, field_name, values)
        if self.timestamp is not None and not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be datetime or None")
        if self.session is not None and not isinstance(self.session, RuntimeTradingSession):
            raise TypeError("session must be RuntimeTradingSession or None")
        if not isinstance(self.primary_blocker, str):
            raise TypeError("primary_blocker must be text")
        object.__setattr__(self, "primary_blocker", self.primary_blocker.strip() or "-")


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
    broker_account: BrokerAccountSnapshot | None = None
    broker_account_verification_report: tuple[BrokerRuntimeVerificationStage, ...] = ()
    broker_session: BrokerSessionPersistenceSnapshot | None = None
