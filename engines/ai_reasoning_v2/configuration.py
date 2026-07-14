"""
Configuration for AI Reasoning Engine V2.
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real


@dataclass(frozen=True, slots=True)
class AIReasoningV2Configuration:
    very_high_confidence: float = 0.85
    high_confidence: float = 0.70
    moderate_confidence: float = 0.50
    low_confidence: float = 0.30

    maximum_supporting_points: int = 5
    maximum_conflicting_points: int = 5
    maximum_cautions: int = 5
    maximum_watch_conditions: int = 5

    require_ready_context_for_actionable: bool = True
    avoid_actionable_on_high_conflict: bool = True
    include_secondary_confirmations: bool = True
    history_limit: int = 120

    def __post_init__(self) -> None:
        thresholds = (
            self.very_high_confidence,
            self.high_confidence,
            self.moderate_confidence,
            self.low_confidence,
        )
        for value in thresholds:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError("confidence thresholds must be finite numbers")
            if not isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError("confidence thresholds must be within 0.0 to 1.0")
        if not (
            self.very_high_confidence
            > self.high_confidence
            > self.moderate_confidence
            > self.low_confidence
        ):
            raise ValueError("confidence thresholds must be strictly descending")
        for name in (
            "maximum_supporting_points",
            "maximum_conflicting_points",
            "maximum_cautions",
            "maximum_watch_conditions",
            "history_limit",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be a positive integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        for name in (
            "require_ready_context_for_actionable",
            "avoid_actionable_on_high_conflict",
            "include_secondary_confirmations",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
