"""
Display-ready live status contracts for the Vision Method inspector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from engines.vision_method import VisionContextAssemblyFailure


class VisionMethodLiveRuntimeState(str, Enum):
    WAITING_FOR_MARKET_DATA = "WAITING_FOR_MARKET_DATA"
    COLLECTING_CONTEXT = "COLLECTING_CONTEXT"
    READY = "READY"
    DEGRADED = "DEGRADED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class VisionMethodLiveStatus:
    instrument: str
    timeframe: str
    market_timestamp: str
    runtime_state: VisionMethodLiveRuntimeState
    candidate_state: str
    quality: str
    validation_result: str
    blocking_stage: str
    blocking_reason: str
    available_contexts: tuple[str, ...]
    missing_contexts: tuple[VisionContextAssemblyFailure, ...]
    failed_contexts: tuple[VisionContextAssemblyFailure, ...]
    unexpected_error: str | None
    updated_at: datetime
    market_data_age_seconds: float | None = None
    level_context: object | None = None
    opening_range_context: object | None = None
    structure_context: object | None = None
    liquidity_context: object | None = None
    structure_event_context: object | None = None
    setup_qualification_context: object | None = None
    option_confirmation_context: object | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "instrument",
            "timeframe",
            "market_timestamp",
            "candidate_state",
            "quality",
            "validation_result",
            "blocking_stage",
            "blocking_reason",
        ):
            object.__setattr__(self, field_name, _normalize_optional_text(getattr(self, field_name), field_name))
        if not isinstance(self.runtime_state, VisionMethodLiveRuntimeState):
            raise TypeError("runtime_state must be VisionMethodLiveRuntimeState.")
        object.__setattr__(self, "available_contexts", _normalize_text_tuple(self.available_contexts, "available_contexts"))
        object.__setattr__(self, "missing_contexts", _normalize_failures(self.missing_contexts, "missing_contexts"))
        object.__setattr__(self, "failed_contexts", _normalize_failures(self.failed_contexts, "failed_contexts"))
        if self.unexpected_error is not None:
            object.__setattr__(self, "unexpected_error", _normalize_optional_text(self.unexpected_error, "unexpected_error"))
        if not isinstance(self.updated_at, datetime):
            raise TypeError("updated_at must be datetime.")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware.")
        if self.market_data_age_seconds is not None:
            age = self.market_data_age_seconds
            if isinstance(age, bool) or not isinstance(age, (int, float)):
                raise TypeError("market_data_age_seconds must be numeric or None.")
            age = float(age)
            if age < 0 or age != age or age in (float("inf"), float("-inf")):
                raise ValueError("market_data_age_seconds must be finite and non-negative.")
            object.__setattr__(self, "market_data_age_seconds", age)


def _normalize_failures(
    values: tuple[VisionContextAssemblyFailure, ...],
    field_name: str,
) -> tuple[VisionContextAssemblyFailure, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple.")
    for value in values:
        if not isinstance(value, VisionContextAssemblyFailure):
            raise TypeError(f"{field_name} must contain VisionContextAssemblyFailure objects.")
    return values


def _normalize_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple.")
    return tuple(_normalize_optional_text(value, field_name) for value in values)


def _normalize_optional_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str.")
    return value.strip()
