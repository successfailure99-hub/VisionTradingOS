"""
Immutable Risk Management Engine V2 models.
"""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from core.enums.instrument import Instrument
from engines.risk_management_v2.enums import (
    RiskDecision,
    RiskDecisionChange,
    RiskRuleResult,
    RiskRuleType,
    RiskSeverity,
    RiskStatus,
)
from engines.strategy_decision_v2.enums import StrategyDirection
from engines.strategy_decision_v2.models import StrategyDecisionV2Snapshot


SUPPORTED_INSTRUMENTS = {Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX}


@dataclass(frozen=True, slots=True)
class AccountRiskState:
    timestamp: datetime
    account_equity: float
    available_capital: float
    day_start_equity: float
    peak_equity: float
    realized_pnl_today: float
    unrealized_pnl: float
    current_total_exposure: float

    def __post_init__(self) -> None:
        _aware(self.timestamp, "timestamp")
        for name in ("account_equity", "available_capital", "current_total_exposure"):
            object.__setattr__(self, name, _non_negative_real(getattr(self, name), name))
        for name in ("day_start_equity", "peak_equity"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        for name in ("realized_pnl_today", "unrealized_pnl"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))
        if self.peak_equity < self.account_equity:
            raise ValueError("peak_equity cannot be below account_equity")
        if self.current_equity < 0.0:
            raise ValueError("current equity cannot be negative")

    @property
    def current_equity(self) -> float:
        return self.account_equity + self.unrealized_pnl

    @property
    def daily_pnl(self) -> float:
        return self.realized_pnl_today + self.unrealized_pnl

    @property
    def daily_loss_fraction(self) -> float:
        return max(0.0, -self.daily_pnl) / self.day_start_equity

    @property
    def drawdown_fraction(self) -> float:
        return max(0.0, self.peak_equity - self.current_equity) / self.peak_equity

    @property
    def total_exposure_fraction(self) -> float:
        if self.current_equity == 0.0:
            return 0.0
        return self.current_total_exposure / self.current_equity


@dataclass(frozen=True, slots=True)
class SessionRiskState:
    trading_date: date
    trades_taken: int
    winning_trades: int
    losing_trades: int
    consecutive_losses: int
    realized_risk_used: float

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date")
        for name in ("trades_taken", "winning_trades", "losing_trades", "consecutive_losses"):
            _non_negative_int(getattr(self, name), name)
        if self.winning_trades + self.losing_trades > self.trades_taken:
            raise ValueError("wins and losses cannot exceed trades")
        if self.consecutive_losses > self.losing_trades:
            raise ValueError("consecutive losses cannot exceed losses")
        object.__setattr__(
            self,
            "realized_risk_used",
            _non_negative_real(self.realized_risk_used, "realized_risk_used"),
        )


@dataclass(frozen=True, slots=True)
class InstrumentExposureState:
    instrument: Instrument
    current_quantity: int
    current_notional_exposure: float
    open_risk_amount: float

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _non_negative_int(self.current_quantity, "current_quantity")
        for name in ("current_notional_exposure", "open_risk_amount"):
            object.__setattr__(self, name, _non_negative_real(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class RiskManagementV2Input:
    strategy: StrategyDecisionV2Snapshot
    account: AccountRiskState
    session: SessionRiskState
    instrument_exposure: InstrumentExposureState
    proposed_entry_price: float
    proposed_invalidation_price: float
    proposed_objective_price: float | None
    quantity_step: int = 1
    contract_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, StrategyDecisionV2Snapshot):
            raise TypeError("strategy must be StrategyDecisionV2Snapshot")
        if not isinstance(self.account, AccountRiskState):
            raise TypeError("account must be AccountRiskState")
        if not isinstance(self.session, SessionRiskState):
            raise TypeError("session must be SessionRiskState")
        if not isinstance(self.instrument_exposure, InstrumentExposureState):
            raise TypeError("instrument_exposure must be InstrumentExposureState")
        if self.instrument_exposure.instrument is not self.strategy.instrument:
            raise ValueError("instrument exposure must match strategy instrument")
        if self.account.timestamp > self.strategy.timestamp:
            raise ValueError("account timestamp cannot be in the future")
        object.__setattr__(self, "proposed_entry_price", _positive_real(self.proposed_entry_price, "proposed_entry_price"))
        object.__setattr__(self, "proposed_invalidation_price", _positive_real(self.proposed_invalidation_price, "proposed_invalidation_price"))
        if self.proposed_objective_price is not None:
            object.__setattr__(self, "proposed_objective_price", _positive_real(self.proposed_objective_price, "proposed_objective_price"))
        _positive_int(self.quantity_step, "quantity_step")
        object.__setattr__(self, "contract_multiplier", _positive_real(self.contract_multiplier, "contract_multiplier"))
        if self.strategy.direction is StrategyDirection.LONG:
            if self.proposed_invalidation_price >= self.proposed_entry_price:
                raise ValueError("LONG invalidation must be below entry")
            if self.proposed_objective_price is not None and self.proposed_objective_price <= self.proposed_entry_price:
                raise ValueError("LONG objective must be above entry")
        if self.strategy.direction is StrategyDirection.SHORT:
            if self.proposed_invalidation_price <= self.proposed_entry_price:
                raise ValueError("SHORT invalidation must be above entry")
            if self.proposed_objective_price is not None and self.proposed_objective_price >= self.proposed_entry_price:
                raise ValueError("SHORT objective must be below entry")


@dataclass(frozen=True, slots=True)
class RiskRuleEvaluation:
    rule: RiskRuleType
    result: RiskRuleResult
    severity: RiskSeverity
    message: str
    observed_value: float | int | None
    limit_value: float | int | None

    def __post_init__(self) -> None:
        if not isinstance(self.rule, RiskRuleType):
            raise TypeError("rule must be RiskRuleType")
        if not isinstance(self.result, RiskRuleResult):
            raise TypeError("result must be RiskRuleResult")
        if not isinstance(self.severity, RiskSeverity):
            raise TypeError("severity must be RiskSeverity")
        _non_empty(self.message, "message")
        for name in ("observed_value", "limit_value"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value))):
                raise TypeError(f"{name} must be finite number or None")


@dataclass(frozen=True, slots=True)
class PositionSizeRecommendation:
    requested_risk_amount: float
    approved_risk_amount: float
    risk_per_unit: float
    raw_quantity: float
    rounded_quantity: int
    capped_quantity: int
    final_quantity: int
    quantity_step: int
    contract_multiplier: float
    reduced: bool

    def __post_init__(self) -> None:
        for name in ("requested_risk_amount", "approved_risk_amount", "raw_quantity"):
            object.__setattr__(self, name, _non_negative_real(getattr(self, name), name))
        object.__setattr__(self, "risk_per_unit", _positive_real(self.risk_per_unit, "risk_per_unit"))
        object.__setattr__(self, "contract_multiplier", _positive_real(self.contract_multiplier, "contract_multiplier"))
        for name in ("rounded_quantity", "capped_quantity", "final_quantity"):
            _non_negative_int(getattr(self, name), name)
        _positive_int(self.quantity_step, "quantity_step")
        if self.final_quantity % self.quantity_step != 0:
            raise ValueError("final quantity must be a multiple of quantity step")
        if self.final_quantity > self.capped_quantity:
            raise ValueError("final quantity cannot exceed capped quantity")
        if type(self.reduced) is not bool:
            raise TypeError("reduced must be bool")
        if self.reduced and self.final_quantity >= self.rounded_quantity:
            raise ValueError("reduced requires final quantity below rounded quantity")


@dataclass(frozen=True, slots=True)
class RiskManagementV2Snapshot:
    instrument: Instrument
    timestamp: datetime
    decision: RiskDecision
    status: RiskStatus
    severity: RiskSeverity
    change: RiskDecisionChange
    strategy: StrategyDecisionV2Snapshot
    account: AccountRiskState
    session: SessionRiskState
    instrument_exposure: InstrumentExposureState
    position_size: PositionSizeRecommendation | None
    rule_evaluations: tuple[RiskRuleEvaluation, ...]
    entry_price: float
    invalidation_price: float
    objective_price: float | None
    risk_distance: float
    reward_distance: float | None
    reward_risk_ratio: float | None
    account_risk_amount: float
    approved_risk_amount: float
    projected_notional_exposure: float
    approved_quantity: int
    execution_eligible: bool
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.instrument not in SUPPORTED_INSTRUMENTS:
            raise ValueError("instrument must be NIFTY, BANKNIFTY or SENSEX")
        _aware(self.timestamp, "timestamp")
        for name, enum_type in (
            ("decision", RiskDecision),
            ("status", RiskStatus),
            ("severity", RiskSeverity),
            ("change", RiskDecisionChange),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be {enum_type.__name__}")
        if self.strategy.instrument is not self.instrument or self.strategy.timestamp != self.timestamp:
            raise ValueError("strategy instrument and timestamp must match snapshot")
        if self.instrument_exposure.instrument is not self.instrument:
            raise ValueError("instrument exposure must match snapshot")
        if self.position_size is not None and not isinstance(self.position_size, PositionSizeRecommendation):
            raise TypeError("position_size must be PositionSizeRecommendation or None")
        object.__setattr__(self, "rule_evaluations", _tuple_of(self.rule_evaluations, RiskRuleEvaluation, "rule_evaluations"))
        for name in ("entry_price", "invalidation_price", "risk_distance"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        if self.objective_price is not None:
            object.__setattr__(self, "objective_price", _positive_real(self.objective_price, "objective_price"))
        if self.reward_distance is not None:
            object.__setattr__(self, "reward_distance", _positive_real(self.reward_distance, "reward_distance"))
        if self.reward_risk_ratio is not None:
            object.__setattr__(self, "reward_risk_ratio", _positive_real(self.reward_risk_ratio, "reward_risk_ratio"))
        for name in ("account_risk_amount", "approved_risk_amount", "projected_notional_exposure"):
            object.__setattr__(self, name, _non_negative_real(getattr(self, name), name))
        _non_negative_int(self.approved_quantity, "approved_quantity")
        if type(self.execution_eligible) is not bool:
            raise TypeError("execution_eligible must be bool")
        if self.execution_eligible and self.decision not in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED}:
            raise ValueError("execution eligibility requires approved decision")
        if self.decision in {RiskDecision.APPROVED, RiskDecision.APPROVED_REDUCED}:
            if self.approved_quantity <= 0 or self.position_size is None:
                raise ValueError("approved decisions require quantity and position size")
        elif self.approved_quantity != 0:
            raise ValueError("non-approved decisions require zero quantity")
        object.__setattr__(self, "rationale", _strings(self.rationale, "rationale"))
        object.__setattr__(self, "warnings", _strings(self.warnings, "warnings"))


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware datetime")


def _finite_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _positive_real(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number <= 0.0:
        raise ValueError(f"{name} must be positive")
    return number


def _non_negative_real(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be positive integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be non-negative integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty string")


def _strings(value, name: str) -> tuple[str, ...]:
    items = tuple(value)
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError(f"{name} must contain non-empty strings")
    return items


def _tuple_of(value, item_type, name: str):
    items = tuple(value)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain {item_type.__name__}")
    return items
