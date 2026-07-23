from engines.ai_reasoning_v2.enums import AIReasoningDirection
from engines.strategy_decision_v2.configuration import StrategyDecisionV2Configuration
from engines.strategy_decision_v2.eligibility import StrategyEligibilityEvaluator
from engines.strategy_decision_v2.enums import (
    StrategyAction,
    StrategyDecisionChange,
    StrategyDecisionQuality,
    StrategyDirection,
    StrategyInvalidationType,
    StrategyReferenceType,
    StrategySetupFamily,
    StrategySetupStatus,
    StrategyTriggerType,
)
from engines.strategy_decision_v2.models import (
    StrategyDecisionV2Input,
    StrategyDecisionV2Snapshot,
    StrategyEntryCondition,
    StrategyInvalidationRule,
    StrategyObjective,
    StrategyRiskHandoff,
    StrategyStructuralReference,
)
from engines.strategy_decision_v2.selector import StrategySetupSelector


class StrategyDecisionV2Calculator:
    def __init__(
        self,
        eligibility: StrategyEligibilityEvaluator | None = None,
        selector: StrategySetupSelector | None = None,
    ) -> None:
        self._eligibility = eligibility or StrategyEligibilityEvaluator()
        self._selector = selector or StrategySetupSelector()

    def calculate(
        self,
        *,
        inputs: StrategyDecisionV2Input,
        configuration: StrategyDecisionV2Configuration,
        previous: StrategyDecisionV2Snapshot | None = None,
    ) -> StrategyDecisionV2Snapshot:
        eligible, blocked_status, eligibility_notes = self._eligibility.evaluate(inputs, configuration)
        direction = _direction(inputs.reasoning.direction)
        family = self._selector.select(inputs, configuration) if eligible else StrategySetupFamily.NO_SETUP
        references = _references(inputs)
        primary = _primary_reference(direction, family, references)
        requires_retest = family in {StrategySetupFamily.BREAKOUT_RETEST, StrategySetupFamily.BREAKDOWN_RETEST}
        if requires_retest:
            status = StrategySetupStatus.WAITING_FOR_RETEST
            eligible = False
        elif family is StrategySetupFamily.REVERSAL_WATCH:
            status = StrategySetupStatus.WAITING_FOR_TRIGGER
            eligible = False
        elif eligible:
            status = StrategySetupStatus.READY_FOR_RISK_REVIEW
        else:
            status = blocked_status
        action = _action(direction, status, inputs.reasoning.direction)
        conditions = _conditions(direction, family, primary, configuration)
        invalidations = _invalidations(direction, primary, configuration)
        objectives = _objectives(direction, references, configuration)
        if action in {StrategyAction.NO_TRADE, StrategyAction.INSUFFICIENT_DATA}:
            conditions = ()
            invalidations = ()
            objectives = ()
            primary = None
        invalidation_ref = primary if direction in {StrategyDirection.LONG, StrategyDirection.SHORT} else None
        quality = _quality(eligible, inputs, configuration)
        risk = StrategyRiskHandoff(
            requires_risk_review=status is StrategySetupStatus.READY_FOR_RISK_REVIEW,
            direction=direction,
            setup_status=status,
            invalidation_reference=invalidation_ref,
            objective_count=len(objectives),
            context_confidence=_structural_confidence(inputs.reasoning),
            reasoning_confidence=inputs.reasoning.confidence,
            notes=("Risk Engine must make final approval.",),
        )
        snapshot = StrategyDecisionV2Snapshot(
            instrument=inputs.reasoning.instrument,
            timestamp=inputs.reasoning.timestamp,
            action=action,
            direction=direction,
            setup_family=family,
            setup_status=status,
            quality=quality,
            change=StrategyDecisionChange.INITIAL,
            ai_reasoning=inputs.reasoning,
            current_price=None,
            setup_name=family.value.replace("_", " "),
            thesis=_thesis(action, direction, family),
            entry_conditions=conditions,
            invalidation_rules=invalidations,
            objectives=objectives,
            primary_reference=primary,
            invalidation_reference=invalidation_ref,
            context_confidence=_structural_confidence(inputs.reasoning),
            reasoning_confidence=inputs.reasoning.confidence,
            eligible=eligible and status is StrategySetupStatus.READY_FOR_RISK_REVIEW,
            requires_retest=requires_retest,
            risk_handoff=risk,
            rationale=_rationale(inputs, family, primary, conditions, invalidations, objectives, eligibility_notes),
            warnings=_warnings(family, status, inputs.reasoning.multi_timeframe_evidence.evidence_conflict),
        )
        return _with_change(snapshot, _change(snapshot, previous))


def _direction(ai_direction) -> StrategyDirection:
    if ai_direction in {AIReasoningDirection.BULLISH, AIReasoningDirection.STRONGLY_BULLISH}:
        return StrategyDirection.LONG
    if ai_direction in {AIReasoningDirection.BEARISH, AIReasoningDirection.STRONGLY_BEARISH}:
        return StrategyDirection.SHORT
    if ai_direction is AIReasoningDirection.NEUTRAL:
        return StrategyDirection.NEUTRAL
    return StrategyDirection.NONE


def _action(direction, status, ai_direction) -> StrategyAction:
    if ai_direction is AIReasoningDirection.INSUFFICIENT_DATA:
        return StrategyAction.INSUFFICIENT_DATA
    if status is StrategySetupStatus.BLOCKED_BY_CONFLICT:
        return StrategyAction.NO_TRADE
    if status is StrategySetupStatus.READY_FOR_RISK_REVIEW and direction is StrategyDirection.LONG:
        return StrategyAction.CONSIDER_LONG
    if status is StrategySetupStatus.READY_FOR_RISK_REVIEW and direction is StrategyDirection.SHORT:
        return StrategyAction.CONSIDER_SHORT
    if direction in {StrategyDirection.LONG, StrategyDirection.SHORT} and status not in {StrategySetupStatus.NO_SETUP, StrategySetupStatus.BLOCKED_BY_CONFLICT}:
        return StrategyAction.WAIT
    return StrategyAction.NO_TRADE


def _references(inputs):
    return ()


def _primary_reference(direction, family, refs):
    preferred = {
        StrategyDirection.LONG: [StrategyReferenceType.CAMARILLA_H4, StrategyReferenceType.CPR_TC, StrategyReferenceType.VWAP, StrategyReferenceType.CURRENT_PRICE],
        StrategyDirection.SHORT: [StrategyReferenceType.CAMARILLA_L4, StrategyReferenceType.CPR_BC, StrategyReferenceType.VWAP, StrategyReferenceType.CURRENT_PRICE],
    }.get(direction, [StrategyReferenceType.CURRENT_PRICE])
    for kind in preferred:
        for ref in refs:
            if ref.reference_type is kind:
                return ref
    return None


def _conditions(direction, family, reference, configuration):
    if direction not in {StrategyDirection.LONG, StrategyDirection.SHORT}:
        return ()
    trigger = StrategyTriggerType.STRUCTURE_CONTINUATION
    if family is StrategySetupFamily.BREAKOUT_RETEST:
        trigger = StrategyTriggerType.BULLISH_RETEST_HOLD
    if family is StrategySetupFamily.BREAKDOWN_RETEST:
        trigger = StrategyTriggerType.BEARISH_RETEST_REJECTION
    side = "bullish" if direction is StrategyDirection.LONG else "bearish"
    items = [
        StrategyEntryCondition(1, trigger, f"Require {side} context to remain aligned.", reference, True),
        StrategyEntryCondition(2, StrategyTriggerType.STRUCTURE_CONTINUATION, "Primary evidence must remain aligned.", None, True),
        StrategyEntryCondition(3, StrategyTriggerType.STRUCTURE_CONTINUATION, "Conflict severity must remain below HIGH.", None, True),
    ]
    return tuple(items[: configuration.maximum_conditions])


def _invalidations(direction, reference, configuration):
    if direction not in {StrategyDirection.LONG, StrategyDirection.SHORT}:
        return ()
    structural = StrategyInvalidationType.CLOSE_BACK_BELOW_LEVEL if direction is StrategyDirection.LONG else StrategyInvalidationType.CLOSE_BACK_ABOVE_LEVEL
    items = [
        StrategyInvalidationRule(1, structural, "Invalidate if price closes back through the structural reference.", reference),
        StrategyInvalidationRule(2, StrategyInvalidationType.PRIMARY_BIAS_REVERSAL, "Invalidate if primary bias reverses.", None),
        StrategyInvalidationRule(3, StrategyInvalidationType.CONFLICT_INCREASE, "Invalidate if primary conflict increases.", None),
        StrategyInvalidationRule(4, StrategyInvalidationType.CONTEXT_STALE, "Invalidate if context becomes stale.", None),
    ]
    return tuple(items[: configuration.maximum_invalidation_rules])


def _objectives(direction, refs, configuration):
    return ()


def _quality(eligible, inputs, configuration):
    conflict = inputs.reasoning.multi_timeframe_evidence.evidence_conflict.value
    if not eligible:
        return StrategyDecisionQuality.UNAVAILABLE if conflict in {"major", "insufficient"} else StrategyDecisionQuality.LOW
    if inputs.reasoning.confidence >= configuration.high_quality_confidence and conflict in {"none", "minor"}:
        return StrategyDecisionQuality.HIGH
    return StrategyDecisionQuality.MODERATE


def _thesis(action, direction, family):
    if action in {StrategyAction.CONSIDER_LONG, StrategyAction.CONSIDER_SHORT, StrategyAction.WAIT}:
        return f"AI reasoning supports a {direction.value} {family.value.replace('_', ' ')} evaluation."
    if action is StrategyAction.INSUFFICIENT_DATA:
        return "Primary evidence is insufficient for a strategy decision."
    return "Strategy decision is no trade because required context is blocked."


def _rationale(inputs, family, primary, conditions, invalidations, objectives, notes):
    return (
        inputs.reasoning.primary_thesis,
        notes[0],
        f"{family.value} setup family is selected.",
        f"{primary.label if primary else 'No'} structural reference is primary.",
        f"{len(conditions)} entry conditions are defined.",
        f"{len(invalidations)} invalidation rules are defined.",
        f"{len(objectives)} structural objectives are available.",
        "The setup must be reviewed by the Risk Engine before execution.",
    )


def _warnings(family, status, conflict):
    warnings = []
    if status is StrategySetupStatus.WAITING_FOR_RETEST:
        warnings.append("Breakout retest has not yet been confirmed.")
    if family is StrategySetupFamily.REVERSAL_WATCH:
        warnings.append("Reversal-watch setups are observation-only.")
    if conflict.value in {"major", "insufficient"}:
        warnings.append("Conflict has increased.")
    return tuple(warnings) or ("Risk Engine remains the final approval gate.",)


def _structural_confidence(reasoning) -> float:
    return {
        "high_structure": 0.85,
        "medium_structure": 0.65,
        "low_structure": 0.35,
    }.get(reasoning.market_state.confidence_level.value, 0.0)


def _change(snapshot, previous):
    if previous is None:
        return StrategyDecisionChange.INITIAL
    if previous.action in {StrategyAction.NO_TRADE, StrategyAction.INSUFFICIENT_DATA, StrategyAction.WAIT} and snapshot.action in {StrategyAction.CONSIDER_LONG, StrategyAction.CONSIDER_SHORT}:
        return StrategyDecisionChange.SETUP_APPEARED
    if previous.direction is StrategyDirection.LONG and snapshot.direction is StrategyDirection.SHORT:
        return StrategyDecisionChange.TURNED_SHORT
    if previous.direction is StrategyDirection.SHORT and snapshot.direction is StrategyDirection.LONG:
        return StrategyDecisionChange.TURNED_LONG
    if snapshot.action is StrategyAction.WAIT and previous.action in {StrategyAction.CONSIDER_LONG, StrategyAction.CONSIDER_SHORT}:
        return StrategyDecisionChange.BECAME_WAIT
    if snapshot.action is StrategyAction.NO_TRADE and previous.action is not StrategyAction.NO_TRADE:
        return StrategyDecisionChange.BECAME_NO_TRADE
    delta = snapshot.reasoning_confidence - previous.reasoning_confidence
    if snapshot.direction is previous.direction and snapshot.setup_family is previous.setup_family:
        if delta >= 0.10:
            return StrategyDecisionChange.SETUP_STRENGTHENED
        if delta <= -0.10:
            return StrategyDecisionChange.SETUP_WEAKENED
    return StrategyDecisionChange.UNCHANGED


def _with_change(snapshot, change):
    data = {field: getattr(snapshot, field) for field in snapshot.__dataclass_fields__}
    data["change"] = change
    return StrategyDecisionV2Snapshot(**data)
