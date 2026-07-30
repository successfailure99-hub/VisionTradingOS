"""
Immutable trade-candidate contract produced from Vision Method snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from application.enums import RuntimeInstrument
from core.enums.exchange import Exchange
from core.enums.timeframe import TimeFrame

from .enums import TradeCandidateDirection, TradeCandidateState


@dataclass(frozen=True, slots=True)
class TradeCandidate:
    instrument: RuntimeInstrument
    exchange: Exchange
    timeframe: TimeFrame
    timestamp: datetime
    candidate_state: TradeCandidateState
    direction: TradeCandidateDirection
    entry_zone: str
    stop_loss_zone: str
    target_zone: str
    confidence: str
    reason: str
    snapshot_reference: str
    validation_reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.exchange, Exchange):
            raise TypeError("exchange must be Exchange.")
        if not isinstance(self.timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        _validate_aware(self.timestamp, "timestamp")
        if not isinstance(self.candidate_state, TradeCandidateState):
            raise TypeError("candidate_state must be TradeCandidateState.")
        if not isinstance(self.direction, TradeCandidateDirection):
            raise TypeError("direction must be TradeCandidateDirection.")
        for field_name in (
            "entry_zone",
            "stop_loss_zone",
            "target_zone",
            "confidence",
            "reason",
            "snapshot_reference",
            "validation_reference",
        ):
            object.__setattr__(self, field_name, _normalize_text(getattr(self, field_name), field_name))
        _validate_state_direction(self.candidate_state, self.direction)


def _validate_state_direction(candidate_state: TradeCandidateState, direction: TradeCandidateDirection) -> None:
    expected = {
        TradeCandidateState.LONG: TradeCandidateDirection.LONG,
        TradeCandidateState.SHORT: TradeCandidateDirection.SHORT,
        TradeCandidateState.WAITING_LONG: TradeCandidateDirection.LONG,
        TradeCandidateState.WAITING_SHORT: TradeCandidateDirection.SHORT,
        TradeCandidateState.NO_CANDIDATE: TradeCandidateDirection.NONE,
    }[candidate_state]
    if direction is not expected:
        raise ValueError("candidate_state and direction are inconsistent.")


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty.")
    return normalized
