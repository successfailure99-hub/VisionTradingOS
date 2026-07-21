"""
Synchronous Trade Decision Authorization Gate V1.
"""

from __future__ import annotations

from core.base_engine import BaseEngine
from core import events
from engines.ai_confidence_calibration.enums import CalibrationDecision, ConfidenceBand
from engines.ai_confidence_calibration.models import ConfidenceCalibrationResult
from engines.risk.enums import RiskDecision, RiskReductionReason, RiskTier
from engines.risk.models import RiskDecisionState
from engines.strategy.enums import TradeDirection
from engines.strategy.models import StrategyDecisionState
from engines.trade_decision_authorization.enums import (
    TradeAuthorizationDecision,
    TradeAuthorizationLifecycle,
    TradeAuthorizationReason,
)
from engines.trade_decision_authorization.models import (
    TradeAuthorizationRequest,
    TradeAuthorizationResult,
    TradeAuthorizationSnapshot,
    source_instrument,
    source_timestamp,
)
from engines.trade_execution_policy.enums import ExecutionDecisionStatus, ExecutionPlanStatus
from engines.trade_execution_policy.models import TradeExecutionPlan


MAX_INPUT_AGE_SECONDS = 300
_INPUT_NAMES = (
    "strategy_decision",
    "confidence_result",
    "risk_result",
    "execution_policy_result",
)
_REASON_PRIORITY = (
    TradeAuthorizationReason.INVALID_INPUT,
    TradeAuthorizationReason.INSTRUMENT_MISMATCH,
    TradeAuthorizationReason.DIRECTION_MISMATCH,
    TradeAuthorizationReason.STALE_INPUT,
    TradeAuthorizationReason.CONFIDENCE_BLOCKED,
    TradeAuthorizationReason.RISK_BLOCKED,
    TradeAuthorizationReason.POLICY_BLOCKED,
    TradeAuthorizationReason.CONFIDENCE_REDUCED,
    TradeAuthorizationReason.RISK_REDUCED,
    TradeAuthorizationReason.POLICY_REDUCED,
    TradeAuthorizationReason.AUTHORIZED,
)


class TradeDecisionAuthorizationEngine(BaseEngine):
    """
    Deterministic authorization boundary for already-created trade decisions.

    The engine reads immutable upstream decisions only. It does not recalculate
    strategy, confidence, risk, policy, execution, paper trading, reconciliation,
    position state, broker state, or external services.
    """

    def __init__(self, event_bus, *, instrument: str, timeframe: str):
        super().__init__(event_bus)
        self._instrument = _normalize_text(instrument, "instrument")
        self._timeframe = _normalize_text(timeframe, "timeframe")
        self._lifecycle_state = TradeAuthorizationLifecycle.CREATED
        self._results: dict[str, TradeAuthorizationResult] = {}
        self._fingerprints: dict[str, str] = {}
        self._last_result: TradeAuthorizationResult | None = None
        self._authorization_count = 0
        self._authorized_count = 0
        self._reduced_count = 0
        self._blocked_count = 0

    def start(self) -> TradeAuthorizationSnapshot:
        if self._lifecycle_state is TradeAuthorizationLifecycle.CREATED:
            self._lifecycle_state = TradeAuthorizationLifecycle.READY
            self._publish_state()
        return self.snapshot()

    def authorize(self, request: TradeAuthorizationRequest) -> TradeAuthorizationResult:
        if self._lifecycle_state is TradeAuthorizationLifecycle.STOPPED:
            raise RuntimeError("Trade authorization gate is stopped.")
        if self._lifecycle_state is TradeAuthorizationLifecycle.FAILED:
            raise RuntimeError("Trade authorization gate is failed.")
        if self._lifecycle_state is TradeAuthorizationLifecycle.CREATED:
            raise RuntimeError("Trade authorization gate must be started.")
        if not isinstance(request, TradeAuthorizationRequest):
            raise TypeError("request must be TradeAuthorizationRequest")
        if request.instrument.value != self._instrument:
            raise ValueError("Trade authorization request instrument does not match engine context.")
        fingerprint = request.fingerprint()
        stored = self._results.get(request.authorization_id)
        if stored is not None:
            if self._fingerprints[request.authorization_id] != fingerprint:
                raise ValueError("authorization_id already exists for different request")
            return stored

        try:
            result = self._authorize(request)
        except Exception as exc:
            if isinstance(exc, (TypeError, ValueError, RuntimeError)):
                raise
            self._lifecycle_state = TradeAuthorizationLifecycle.FAILED
            self._event_bus.publish(events.TRADE_AUTHORIZATION_FAILED, self.snapshot())
            self._publish_state()
            raise

        self._results[request.authorization_id] = result
        self._fingerprints[request.authorization_id] = fingerprint
        self._last_result = result
        self._data = result
        self._authorization_count += 1
        if result.decision is TradeAuthorizationDecision.BLOCK:
            self._blocked_count += 1
        elif result.decision is TradeAuthorizationDecision.REDUCE:
            self._reduced_count += 1
        else:
            self._authorized_count += 1
        if self._lifecycle_state is TradeAuthorizationLifecycle.READY:
            self._lifecycle_state = TradeAuthorizationLifecycle.ACTIVE
        self._event_bus.publish(events.TRADE_AUTHORIZATION_COMPLETED, result)
        if result.decision is TradeAuthorizationDecision.AUTHORIZE:
            self._event_bus.publish(events.TRADE_AUTHORIZATION_APPROVED, result)
        elif result.decision is TradeAuthorizationDecision.REDUCE:
            self._event_bus.publish(events.TRADE_AUTHORIZATION_REDUCED, result)
        else:
            self._event_bus.publish(events.TRADE_AUTHORIZATION_BLOCKED, result)
        self._publish_state()
        return result

    def get_result(self, authorization_id: str) -> TradeAuthorizationResult | None:
        key = _normalize_text(authorization_id, "authorization_id")
        return self._results.get(key)

    def snapshot(self) -> TradeAuthorizationSnapshot:
        return TradeAuthorizationSnapshot(
            enabled=True,
            lifecycle_state=self._lifecycle_state,
            authorization_count=self._authorization_count,
            authorized_count=self._authorized_count,
            reduced_count=self._reduced_count,
            blocked_count=self._blocked_count,
            last_result=self._last_result,
        )

    def stop(self) -> TradeAuthorizationSnapshot:
        if self._lifecycle_state in {
            TradeAuthorizationLifecycle.CREATED,
            TradeAuthorizationLifecycle.READY,
            TradeAuthorizationLifecycle.ACTIVE,
        }:
            self._lifecycle_state = TradeAuthorizationLifecycle.STOPPED
            self._publish_state()
        return self.snapshot()

    def reset(self) -> TradeAuthorizationSnapshot:
        self._results.clear()
        self._fingerprints.clear()
        self._last_result = None
        self._data = None
        self._authorization_count = 0
        self._authorized_count = 0
        self._reduced_count = 0
        self._blocked_count = 0
        self._lifecycle_state = TradeAuthorizationLifecycle.READY
        self._publish_state()
        return self.snapshot()

    def _authorize(self, request: TradeAuthorizationRequest) -> TradeAuthorizationResult:
        reasons: list[TradeAuthorizationReason] = []
        invalid_inputs = self._invalid_inputs(request)
        if invalid_inputs:
            reasons.append(TradeAuthorizationReason.INVALID_INPUT)
        if not invalid_inputs and self._instrument_mismatch(request):
            reasons.append(TradeAuthorizationReason.INSTRUMENT_MISMATCH)
        if not invalid_inputs and not self._instrument_mismatch(request) and self._direction_mismatch(request):
            reasons.append(TradeAuthorizationReason.DIRECTION_MISMATCH)

        stale_inputs = () if invalid_inputs else self._stale_inputs(request)
        if stale_inputs:
            reasons.append(TradeAuthorizationReason.STALE_INPUT)

        if not invalid_inputs:
            reasons.extend(self._confidence_reasons(request.confidence_result))
            reasons.extend(self._risk_reasons(request.risk_result))
            reasons.extend(self._policy_reasons(request.execution_policy_result))

        reasons = _ordered_unique(reasons)
        if not reasons:
            reasons = (TradeAuthorizationReason.AUTHORIZED,)
        primary = reasons[0]
        decision = _decision_from_reasons(reasons)
        direction = request.strategy_decision.direction if isinstance(request.strategy_decision, StrategyDecisionState) else TradeDirection.NONE
        return TradeAuthorizationResult(
            authorization_id=request.authorization_id,
            timestamp=request.timestamp,
            instrument=request.instrument,
            direction=direction,
            decision=decision,
            primary_reason=primary,
            reasons=tuple(reasons),
            authorization_multiplier=_multiplier(decision),
            stale_inputs=stale_inputs,
            invalid_inputs=invalid_inputs,
            source_strategy_id=getattr(request.strategy_decision, "plan_id", None),
            source_confidence_id=getattr(request.confidence_result, "calibration_id", None),
            source_risk_id=getattr(request.risk_result, "plan_id", None),
            source_policy_id=getattr(request.execution_policy_result, "execution_plan_id", None),
            correlation_id=request.correlation_id,
        )

    def _invalid_inputs(self, request: TradeAuthorizationRequest) -> tuple[str, ...]:
        expected = (
            ("strategy_decision", request.strategy_decision, StrategyDecisionState),
            ("confidence_result", request.confidence_result, ConfidenceCalibrationResult),
            ("risk_result", request.risk_result, RiskDecisionState),
            ("execution_policy_result", request.execution_policy_result, TradeExecutionPlan),
        )
        return tuple(name for name, value, kind in expected if not isinstance(value, kind))

    def _instrument_mismatch(self, request: TradeAuthorizationRequest) -> bool:
        expected = request.instrument.value
        for name in _INPUT_NAMES:
            observed = source_instrument(getattr(request, name))
            if observed != expected:
                return True
        return False

    def _direction_mismatch(self, request: TradeAuthorizationRequest) -> bool:
        strategy_direction = request.strategy_decision.direction
        directions = (
            request.confidence_result.direction,
            request.risk_result.direction,
            request.execution_policy_result.direction,
        )
        return any(direction is not strategy_direction for direction in directions)

    def _stale_inputs(self, request: TradeAuthorizationRequest) -> tuple[str, ...]:
        stale = []
        for name in _INPUT_NAMES:
            timestamp = source_timestamp(getattr(request, name))
            if timestamp is not None and (request.timestamp - timestamp).total_seconds() > MAX_INPUT_AGE_SECONDS:
                stale.append(name)
        return tuple(stale)

    def _confidence_reasons(self, result: ConfidenceCalibrationResult) -> tuple[TradeAuthorizationReason, ...]:
        if result.confidence_band is ConfidenceBand.BLOCKED or result.calibration_decision is CalibrationDecision.BLOCK:
            return (TradeAuthorizationReason.CONFIDENCE_BLOCKED,)
        if result.calibration_decision is CalibrationDecision.REDUCE:
            return (TradeAuthorizationReason.CONFIDENCE_REDUCED,)
        return ()

    def _risk_reasons(self, result: RiskDecisionState) -> tuple[TradeAuthorizationReason, ...]:
        if result.decision is RiskDecision.REJECTED or result.risk_tier is RiskTier.BLOCKED:
            return (TradeAuthorizationReason.RISK_BLOCKED,)
        if result.risk_tier is RiskTier.REDUCED or result.reduction_reason is not RiskReductionReason.NONE:
            return (TradeAuthorizationReason.RISK_REDUCED,)
        return ()

    def _policy_reasons(self, plan: TradeExecutionPlan) -> tuple[TradeAuthorizationReason, ...]:
        if plan.decision_status in {
            ExecutionDecisionStatus.REJECTED,
            ExecutionDecisionStatus.LOCKED,
            ExecutionDecisionStatus.INVALID,
            ExecutionDecisionStatus.EXPIRED,
        } or plan.status in {
            ExecutionPlanStatus.LOCKED,
            ExecutionPlanStatus.REJECTED,
            ExecutionPlanStatus.EXPIRED,
            ExecutionPlanStatus.CANCELLED,
        }:
            return (TradeAuthorizationReason.POLICY_BLOCKED,)
        if plan.status is ExecutionPlanStatus.AWAITING_MANUAL_APPROVAL:
            return (TradeAuthorizationReason.POLICY_REDUCED,)
        return ()

    def _publish_state(self) -> None:
        self._event_bus.publish(events.TRADE_AUTHORIZATION_STATE_UPDATED, self.snapshot())


def _ordered_unique(values: list[TradeAuthorizationReason]) -> tuple[TradeAuthorizationReason, ...]:
    result = []
    for reason in _REASON_PRIORITY:
        if reason in values and reason not in result:
            result.append(reason)
    return tuple(result)


def _decision_from_reasons(reasons: tuple[TradeAuthorizationReason, ...]) -> TradeAuthorizationDecision:
    if any(
        reason in reasons
        for reason in (
            TradeAuthorizationReason.INVALID_INPUT,
            TradeAuthorizationReason.INSTRUMENT_MISMATCH,
            TradeAuthorizationReason.DIRECTION_MISMATCH,
            TradeAuthorizationReason.STALE_INPUT,
            TradeAuthorizationReason.CONFIDENCE_BLOCKED,
            TradeAuthorizationReason.RISK_BLOCKED,
            TradeAuthorizationReason.POLICY_BLOCKED,
        )
    ):
        return TradeAuthorizationDecision.BLOCK
    if any(
        reason in reasons
        for reason in (
            TradeAuthorizationReason.CONFIDENCE_REDUCED,
            TradeAuthorizationReason.RISK_REDUCED,
            TradeAuthorizationReason.POLICY_REDUCED,
        )
    ):
        return TradeAuthorizationDecision.REDUCE
    return TradeAuthorizationDecision.AUTHORIZE


def _multiplier(decision: TradeAuthorizationDecision) -> float:
    if decision is TradeAuthorizationDecision.BLOCK:
        return 0.0
    if decision is TradeAuthorizationDecision.REDUCE:
        return 0.5
    return 1.0


def _normalize_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip().upper() if name == "instrument" else value.strip()
