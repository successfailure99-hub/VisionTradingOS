"""
Immutable Trade Lifecycle Coordinator V1 models.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real

from application.execution_runtime_v1.models import ExecutionResult, ExecutionRuntimeV1Snapshot
from application.trade_lifecycle_v1.enums import (
    TradeLifecycleBlockSource,
    TradeLifecycleChange,
    TradeLifecycleOutcome,
    TradeLifecycleStage,
    TradeLifecycleStatus,
)
from core.enums.instrument import Instrument
from engines.ai_reasoning_v2.models import AIReasoningV2Snapshot
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context_v2.models import SUPPORTED_INSTRUMENTS, MarketContextV2Snapshot
from engines.position_management_v1.models import PositionManagementResult, PositionManagementV1Snapshot
from engines.risk_management_v2.models import AccountRiskState, InstrumentExposureState, RiskManagementV2Snapshot, SessionRiskState
from engines.strategy_decision_v2.models import StrategyDecisionV2Snapshot
from engines.vwap.levels import VWAPLevels


@dataclass(frozen=True, slots=True)
class TradeLifecycleV1Request:
    market_context: MarketContextV2Snapshot
    current_price: float
    account_risk_state: AccountRiskState
    session_risk_state: SessionRiskState
    instrument_exposure_state: InstrumentExposureState
    proposed_entry_price: float
    proposed_invalidation_price: float
    proposed_objective_price: float | None
    quantity_step: int = 1
    contract_multiplier: float = 1.0
    camarilla: CamarillaLevels | None = None
    cpr: CPRLevels | None = None
    vwap: VWAPLevels | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.market_context, MarketContextV2Snapshot):
            raise TypeError("market_context must be MarketContextV2Snapshot")
        if self.market_context.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        instrument = self.market_context.instrument
        if not isinstance(self.account_risk_state, AccountRiskState):
            raise TypeError("account_risk_state must be AccountRiskState")
        if not isinstance(self.session_risk_state, SessionRiskState):
            raise TypeError("session_risk_state must be SessionRiskState")
        if not isinstance(self.instrument_exposure_state, InstrumentExposureState):
            raise TypeError("instrument_exposure_state must be InstrumentExposureState")
        if self.instrument_exposure_state.instrument is not instrument:
            raise ValueError("instrument exposure must match market context")
        for name in ("current_price", "proposed_entry_price", "proposed_invalidation_price"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        if self.proposed_objective_price is not None:
            object.__setattr__(self, "proposed_objective_price", _positive_real(self.proposed_objective_price, "proposed_objective_price"))
        _positive_int(self.quantity_step, "quantity_step")
        object.__setattr__(self, "contract_multiplier", _positive_real(self.contract_multiplier, "contract_multiplier"))
        if self.camarilla is not None and not isinstance(self.camarilla, CamarillaLevels):
            raise TypeError("camarilla must be CamarillaLevels or None")
        if self.cpr is not None and not isinstance(self.cpr, CPRLevels):
            raise TypeError("cpr must be CPRLevels or None")
        if self.vwap is not None:
            if not isinstance(self.vwap, VWAPLevels):
                raise TypeError("vwap must be VWAPLevels or None")
            if self.vwap.symbol is not instrument:
                raise ValueError("vwap instrument mismatch")


@dataclass(frozen=True, slots=True)
class TradeLifecycleStageRecord:
    sequence: int
    timestamp: datetime
    stage: TradeLifecycleStage
    outcome: TradeLifecycleOutcome
    message: str

    def __post_init__(self) -> None:
        _positive_int(self.sequence, "sequence")
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.stage, TradeLifecycleStage):
            raise TypeError("stage must be TradeLifecycleStage")
        if not isinstance(self.outcome, TradeLifecycleOutcome):
            raise TypeError("outcome must be TradeLifecycleOutcome")
        _non_empty(self.message, "message")


@dataclass(frozen=True, slots=True)
class TradeLifecycleV1Snapshot:
    instrument: Instrument
    timestamp: datetime
    lifecycle_status: TradeLifecycleStatus
    stage: TradeLifecycleStage
    outcome: TradeLifecycleOutcome
    change: TradeLifecycleChange
    block_source: TradeLifecycleBlockSource
    market_context: MarketContextV2Snapshot | None
    ai_reasoning: AIReasoningV2Snapshot | None
    strategy_decision: StrategyDecisionV2Snapshot | None
    risk_decision: RiskManagementV2Snapshot | None
    execution_result: ExecutionResult | None
    position_result: PositionManagementResult | None
    execution_snapshot: ExecutionRuntimeV1Snapshot
    position_snapshot: PositionManagementV1Snapshot
    stage_records: tuple[TradeLifecycleStageRecord, ...]
    processing_count: int
    waiting_count: int
    blocked_count: int
    rejected_count: int
    execution_count: int
    position_open_count: int
    position_close_count: int
    running: bool
    ready: bool
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    last_processed_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.timestamp, "timestamp")
        for name, enum_type in (
            ("lifecycle_status", TradeLifecycleStatus),
            ("stage", TradeLifecycleStage),
            ("outcome", TradeLifecycleOutcome),
            ("change", TradeLifecycleChange),
            ("block_source", TradeLifecycleBlockSource),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be {enum_type.__name__}")
        for name in ("market_context", "ai_reasoning", "strategy_decision", "risk_decision"):
            value = getattr(self, name)
            if value is not None and value.instrument is not self.instrument:
                raise ValueError(f"{name} instrument mismatch")
        if self.execution_result is not None and not isinstance(self.execution_result, ExecutionResult):
            raise TypeError("execution_result must be ExecutionResult or None")
        if self.position_result is not None and not isinstance(self.position_result, PositionManagementResult):
            raise TypeError("position_result must be PositionManagementResult or None")
        if not isinstance(self.execution_snapshot, ExecutionRuntimeV1Snapshot):
            raise TypeError("execution_snapshot must be ExecutionRuntimeV1Snapshot")
        if not isinstance(self.position_snapshot, PositionManagementV1Snapshot):
            raise TypeError("position_snapshot must be PositionManagementV1Snapshot")
        object.__setattr__(self, "stage_records", _tuple_of(self.stage_records, TradeLifecycleStageRecord, "stage_records"))
        for name in ("processing_count", "waiting_count", "blocked_count", "rejected_count", "execution_count", "position_open_count", "position_close_count"):
            _non_negative_int(getattr(self, name), name)
        if type(self.running) is not bool or type(self.ready) is not bool:
            raise TypeError("running and ready must be bool")
        if self.running and self.lifecycle_status is not TradeLifecycleStatus.RUNNING:
            raise ValueError("running=True requires RUNNING lifecycle status")
        for name in ("last_started_at", "last_stopped_at", "last_processed_at"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
        if self.last_error is not None:
            _non_empty(self.last_error, "last_error")


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _positive_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be positive")
    return number


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")


def _non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty string")


def _tuple_of(values, item_type, name: str):
    items = tuple(values)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain {item_type.__name__}")
    return items
