"""
Configuration for Strategy Decision Engine V2.
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real


@dataclass(frozen=True, slots=True)
class StrategyDecisionV2Configuration:
    minimum_context_confidence: float = 0.50
    minimum_reasoning_confidence: float = 0.50
    high_quality_confidence: float = 0.75

    require_context_ready: bool = True
    require_actionable_reasoning: bool = True
    block_high_conflict: bool = True
    require_retest_for_breakout: bool = True
    require_retest_for_breakdown: bool = True

    allow_trend_continuation: bool = True
    allow_breakout_retest: bool = True
    allow_breakdown_retest: bool = True
    allow_range_watch: bool = True
    allow_reversal_watch: bool = True

    maximum_objectives: int = 3
    maximum_conditions: int = 6
    maximum_invalidation_rules: int = 4
    history_limit: int = 120

    def __post_init__(self) -> None:
        for name in (
            "minimum_context_confidence",
            "minimum_reasoning_confidence",
            "high_quality_confidence",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a finite number")
            if not isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be within 0.0 to 1.0")
        if self.high_quality_confidence < max(
            self.minimum_context_confidence,
            self.minimum_reasoning_confidence,
        ):
            raise ValueError("high_quality_confidence must meet minimum thresholds")
        bool_fields = (
            "require_context_ready",
            "require_actionable_reasoning",
            "block_high_conflict",
            "require_retest_for_breakout",
            "require_retest_for_breakdown",
            "allow_trend_continuation",
            "allow_breakout_retest",
            "allow_breakdown_retest",
            "allow_range_watch",
            "allow_reversal_watch",
        )
        for name in bool_fields:
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if not any(getattr(self, name) for name in bool_fields[5:]):
            raise ValueError("at least one setup family must be enabled")
        for name in (
            "maximum_objectives",
            "maximum_conditions",
            "maximum_invalidation_rules",
            "history_limit",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be a positive integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
