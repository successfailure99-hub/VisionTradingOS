"""
Immutable models for OSE-1 directional option-selling paper execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real

from application.enums import RuntimeInstrument
from core.enums.exchange import Exchange
from core.enums.timeframe import TimeFrame
from engines.option_chain.enums import OptionType

from .enums import (
    OptionContractRejectionReason,
    OptionContractSelectionStatus,
    OptionPaperExecutionStyle,
    OptionPaperMoneyness,
    OptionPaperPositionStatus,
    OptionPaperRiskDecision,
    OptionPaperSelectionPolicy,
    OptionPaperTransactionType,
    OptionPaperUnderlyingDirection,
)


@dataclass(frozen=True, slots=True)
class OptionContractSelectionDiagnostic:
    strike: float | None
    option_type: OptionType
    itm_steps: int
    premium: float | None
    bid: float | None
    ask: float | None
    spread: float | None
    spread_fraction: float | None
    open_interest: int | None
    volume: int | None
    status: OptionContractSelectionStatus
    rejection_reasons: tuple[OptionContractRejectionReason, ...] = ()

    def __post_init__(self) -> None:
        if self.strike is not None:
            object.__setattr__(self, "strike", _positive_real(self.strike, "strike"))
        if not isinstance(self.option_type, OptionType):
            raise TypeError("option_type must be OptionType")
        _non_negative_int(self.itm_steps, "itm_steps")
        for name in ("premium", "bid", "ask", "spread", "spread_fraction"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite_real(value, name))
        if self.premium is not None and self.premium < 0:
            raise ValueError("premium must be non-negative when supplied")
        if self.bid is not None and self.bid < 0:
            raise ValueError("bid must be non-negative when supplied")
        if self.ask is not None and self.ask < 0:
            raise ValueError("ask must be non-negative when supplied")
        if self.spread is not None and self.spread < 0:
            raise ValueError("spread must be non-negative when supplied")
        if self.spread_fraction is not None and self.spread_fraction < 0:
            raise ValueError("spread_fraction must be non-negative when supplied")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("diagnostic bid cannot exceed ask")
        for name in ("open_interest", "volume"):
            value = getattr(self, name)
            if value is not None:
                _non_negative_int(value, name)
        if not isinstance(self.status, OptionContractSelectionStatus):
            raise TypeError("status must be OptionContractSelectionStatus")
        reasons = tuple(self.rejection_reasons)
        if any(not isinstance(reason, OptionContractRejectionReason) for reason in reasons):
            raise TypeError("rejection_reasons must contain OptionContractRejectionReason values")
        if len(set(reasons)) != len(reasons):
            raise ValueError("rejection_reasons cannot contain duplicates")
        if self.status is OptionContractSelectionStatus.VALID:
            reasons = (OptionContractRejectionReason.VALID,)
        elif not reasons:
            raise ValueError("rejected diagnostic requires at least one rejection reason")
        object.__setattr__(self, "rejection_reasons", reasons)


@dataclass(frozen=True, slots=True)
class DirectionalOptionSellingConfiguration:
    execution_style: OptionPaperExecutionStyle = OptionPaperExecutionStyle.UNDERLYING_PAPER
    paper_capital: float = 750000.0
    max_nifty_lots: int = 3
    max_banknifty_lots: int = 1
    max_sensex_lots: int = 1
    risk_fraction_per_trade: float = 0.01
    stop_premium_multiplier: float = 1.5
    target_premium_multiplier: float = 0.5
    maximum_spread_fraction: float = 0.15
    minimum_open_interest: int = 1
    minimum_volume: int = 1
    maximum_quote_age_seconds: float = 15.0
    selectable_itm_steps: tuple[int, ...] = (0, 1, 2, 3)
    selection_policy: OptionPaperSelectionPolicy = OptionPaperSelectionPolicy.ATM_FIRST
    preferred_itm_step: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.execution_style, OptionPaperExecutionStyle):
            raise TypeError("execution_style must be OptionPaperExecutionStyle")
        if not isinstance(self.selection_policy, OptionPaperSelectionPolicy):
            raise TypeError("selection_policy must be OptionPaperSelectionPolicy")
        object.__setattr__(self, "paper_capital", _positive_real(self.paper_capital, "paper_capital"))
        for name in ("max_nifty_lots", "max_banknifty_lots", "max_sensex_lots"):
            _positive_int(getattr(self, name), name)
        for name in (
            "risk_fraction_per_trade",
            "stop_premium_multiplier",
            "target_premium_multiplier",
            "maximum_spread_fraction",
            "maximum_quote_age_seconds",
        ):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        if self.stop_premium_multiplier <= 1.0:
            raise ValueError("stop_premium_multiplier must be above 1.0 for short options")
        if self.target_premium_multiplier >= 1.0:
            raise ValueError("target_premium_multiplier must be below 1.0 for short options")
        _non_negative_int(self.minimum_open_interest, "minimum_open_interest")
        _non_negative_int(self.minimum_volume, "minimum_volume")
        steps = tuple(self.selectable_itm_steps)
        if not steps or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in steps):
            raise ValueError("selectable_itm_steps must contain non-negative integers")
        if tuple(sorted(set(steps))) != steps:
            raise ValueError("selectable_itm_steps must be sorted and unique")
        object.__setattr__(self, "selectable_itm_steps", steps)
        _non_negative_int(self.preferred_itm_step, "preferred_itm_step")
        if self.selection_policy is OptionPaperSelectionPolicy.PREFERRED_ITM_DEPTH and self.preferred_itm_step not in steps:
            raise ValueError("preferred_itm_step must be included in selectable_itm_steps")

    def maximum_lots_for(self, instrument: RuntimeInstrument) -> int:
        if instrument is RuntimeInstrument.NIFTY:
            return self.max_nifty_lots
        if instrument is RuntimeInstrument.BANKNIFTY:
            return self.max_banknifty_lots
        if instrument is RuntimeInstrument.SENSEX:
            return self.max_sensex_lots
        raise ValueError("unsupported runtime instrument")


@dataclass(frozen=True, slots=True)
class OptionTradeCandidate:
    candidate_id: str
    runtime_session_id: str
    trading_date: date
    created_at: datetime
    underlying: RuntimeInstrument
    underlying_direction: OptionPaperUnderlyingDirection
    underlying_spot: float
    decision_timeframe: TimeFrame
    source_vision_reference: str
    source_trade_candidate_reference: str
    expiry: date
    strike: float
    option_type: OptionType
    transaction_type: OptionPaperTransactionType
    moneyness: OptionPaperMoneyness
    itm_steps: int
    trading_symbol: str
    instrument_token: int
    exchange: Exchange
    premium_reference: float
    bid: float | None
    ask: float | None
    spread: float | None
    open_interest: int
    volume: int
    implied_volatility: float | None
    delta: float | None
    lot_size: int
    underlying_invalidation: str
    underlying_target_context: str
    selection_score: float
    selection_reasoning: tuple[str, ...]
    status: str
    selection_policy: OptionPaperSelectionPolicy = OptionPaperSelectionPolicy.ATM_FIRST
    selection_diagnostics: tuple[OptionContractSelectionDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "runtime_session_id", _text(self.runtime_session_id, "runtime_session_id"))
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be date")
        _aware(self.created_at, "created_at")
        if not isinstance(self.underlying, RuntimeInstrument):
            raise TypeError("underlying must be RuntimeInstrument")
        if not isinstance(self.underlying_direction, OptionPaperUnderlyingDirection):
            raise TypeError("underlying_direction must be OptionPaperUnderlyingDirection")
        object.__setattr__(self, "underlying_spot", _positive_real(self.underlying_spot, "underlying_spot"))
        if not isinstance(self.decision_timeframe, TimeFrame):
            raise TypeError("decision_timeframe must be TimeFrame")
        for name in ("source_vision_reference", "source_trade_candidate_reference", "trading_symbol", "underlying_invalidation", "underlying_target_context", "status"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.expiry, date) or isinstance(self.expiry, datetime):
            raise TypeError("expiry must be date")
        object.__setattr__(self, "strike", _positive_real(self.strike, "strike"))
        if not isinstance(self.option_type, OptionType):
            raise TypeError("option_type must be OptionType")
        if not isinstance(self.transaction_type, OptionPaperTransactionType):
            raise TypeError("transaction_type must be OptionPaperTransactionType")
        if self.transaction_type is not OptionPaperTransactionType.SELL:
            raise ValueError("OSE-1 supports SELL only")
        if not isinstance(self.moneyness, OptionPaperMoneyness):
            raise TypeError("moneyness must be OptionPaperMoneyness")
        _non_negative_int(self.itm_steps, "itm_steps")
        _positive_int(self.instrument_token, "instrument_token")
        if not isinstance(self.exchange, Exchange):
            raise TypeError("exchange must be Exchange")
        for name in ("premium_reference", "selection_score"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        for name in ("bid", "ask", "spread", "implied_volatility", "delta"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite_real(value, name))
        if self.bid is not None and self.bid <= 0:
            raise ValueError("bid must be positive when supplied")
        if self.ask is not None and self.ask <= 0:
            raise ValueError("ask must be positive when supplied")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("bid cannot exceed ask")
        _non_negative_int(self.open_interest, "open_interest")
        _non_negative_int(self.volume, "volume")
        _positive_int(self.lot_size, "lot_size")
        object.__setattr__(self, "selection_reasoning", _strings(self.selection_reasoning, "selection_reasoning"))
        if not isinstance(self.selection_policy, OptionPaperSelectionPolicy):
            raise TypeError("selection_policy must be OptionPaperSelectionPolicy")
        diagnostics = tuple(self.selection_diagnostics)
        if any(not isinstance(item, OptionContractSelectionDiagnostic) for item in diagnostics):
            raise TypeError("selection_diagnostics must contain OptionContractSelectionDiagnostic values")
        object.__setattr__(self, "selection_diagnostics", diagnostics)


@dataclass(frozen=True, slots=True)
class OptionPaperRiskSnapshot:
    candidate: OptionTradeCandidate
    timestamp: datetime
    decision: OptionPaperRiskDecision
    requested_lots: int
    approved_lots: int
    approved_quantity: int
    entry_premium: float
    stop_premium: float
    target_premium: float
    risk_per_unit: float
    reward_per_unit: float
    planned_rupee_risk: float
    planned_rupee_reward: float
    paper_capital: float
    margin_available: float | None
    reason: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, OptionTradeCandidate):
            raise TypeError("candidate must be OptionTradeCandidate")
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.decision, OptionPaperRiskDecision):
            raise TypeError("decision must be OptionPaperRiskDecision")
        for name in ("requested_lots", "approved_lots", "approved_quantity"):
            _non_negative_int(getattr(self, name), name)
        for name in (
            "entry_premium",
            "stop_premium",
            "target_premium",
            "risk_per_unit",
            "reward_per_unit",
            "planned_rupee_risk",
            "planned_rupee_reward",
            "paper_capital",
        ):
            object.__setattr__(self, name, _non_negative_real(getattr(self, name), name))
        if self.entry_premium <= 0 or self.stop_premium <= self.entry_premium:
            raise ValueError("short option risk requires stop premium above entry")
        if self.target_premium >= self.entry_premium:
            raise ValueError("short option reward requires target premium below entry")
        if self.margin_available is not None:
            object.__setattr__(self, "margin_available", _non_negative_real(self.margin_available, "margin_available"))
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(self, "warnings", _strings(self.warnings, "warnings"))


@dataclass(frozen=True, slots=True)
class OptionPaperPositionSnapshot:
    position_id: str
    candidate: OptionTradeCandidate
    risk: OptionPaperRiskSnapshot
    status: OptionPaperPositionStatus
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    entry_premium: float
    current_premium: float
    exit_premium: float | None
    quantity: int
    lots: int
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    exit_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "position_id", _text(self.position_id, "position_id"))
        if not isinstance(self.candidate, OptionTradeCandidate):
            raise TypeError("candidate must be OptionTradeCandidate")
        if not isinstance(self.risk, OptionPaperRiskSnapshot):
            raise TypeError("risk must be OptionPaperRiskSnapshot")
        if not isinstance(self.status, OptionPaperPositionStatus):
            raise TypeError("status must be OptionPaperPositionStatus")
        for name in ("opened_at", "updated_at"):
            _aware(getattr(self, name), name)
        if self.closed_at is not None:
            _aware(self.closed_at, "closed_at")
        for name in ("entry_premium", "current_premium"):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        if self.exit_premium is not None:
            object.__setattr__(self, "exit_premium", _positive_real(self.exit_premium, "exit_premium"))
        _non_negative_int(self.quantity, "quantity")
        _non_negative_int(self.lots, "lots")
        for name in ("unrealized_pnl", "realized_pnl", "total_pnl"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))
        object.__setattr__(self, "exit_reason", _text(self.exit_reason, "exit_reason"))


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
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def _non_negative_real(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")


def _text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} cannot be empty")
    return normalized


def _strings(values, name: str) -> tuple[str, ...]:
    items = tuple(values)
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError(f"{name} must contain non-empty strings")
    return tuple(item.strip() for item in items)
