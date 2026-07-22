"""
Immutable TradingView Evidence Mapping Engine V1 models.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
import json
import math
from typing import Any

from application.enums import RuntimeInstrument
from core.models.building_candle import BuildingCandle
from core.models.candle import Candle
from engines.camarilla.levels import CamarillaLevels
from engines.cpr.levels import CPRLevels
from engines.market_context.models import MarketContextState
from engines.option_chain.models import OptionChainState
from engines.price_action.models import PriceActionState
from engines.vwap.levels import VWAPLevels

from .enums import (
    CPRRegion,
    CamarillaRegion,
    EvidenceAvailability,
    PriceLocation,
    TradingViewEvidenceLifecycle,
)


@dataclass(frozen=True, slots=True)
class EvidenceStatus:
    name: str
    availability: EvidenceAvailability
    source_timestamp: datetime | None
    age_seconds: float | None
    details: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be non-empty text")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.availability, EvidenceAvailability):
            raise TypeError("availability must be EvidenceAvailability")
        _validate_aware_optional(self.source_timestamp, "source_timestamp")
        if self.age_seconds is not None:
            if isinstance(self.age_seconds, bool) or not isinstance(self.age_seconds, (int, float)):
                raise TypeError("age_seconds must be numeric or None")
            if not math.isfinite(float(self.age_seconds)) or float(self.age_seconds) < 0:
                raise ValueError("age_seconds must be non-negative finite or None")
            object.__setattr__(self, "age_seconds", float(self.age_seconds))
        if self.details is not None:
            if not isinstance(self.details, str):
                raise TypeError("details must be text or None")
            object.__setattr__(self, "details", self.details.strip() or None)


@dataclass(frozen=True, slots=True)
class LevelDistance:
    level_name: str
    level_price: float | None
    absolute_points: float | None
    percentage: float | None
    price_location: PriceLocation

    def __post_init__(self) -> None:
        if not isinstance(self.level_name, str) or not self.level_name.strip():
            raise ValueError("level_name must be non-empty text")
        object.__setattr__(self, "level_name", self.level_name.strip().upper())
        if not isinstance(self.price_location, PriceLocation):
            raise TypeError("price_location must be PriceLocation")
        for field_name in ("level_price", "absolute_points", "percentage"):
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError(f"{field_name} must be numeric or None")
                if not math.isfinite(float(value)):
                    raise ValueError(f"{field_name} must be finite or None")
                object.__setattr__(self, field_name, float(value))


@dataclass(frozen=True, slots=True)
class MovingAverageObservation:
    name: str
    period: int | None
    value: float | None
    price_location: PriceLocation
    slope: float | None
    availability: EvidenceAvailability

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be non-empty text")
        object.__setattr__(self, "name", self.name.strip())
        if self.period is not None:
            if isinstance(self.period, bool) or not isinstance(self.period, int) or self.period <= 0:
                raise ValueError("period must be a positive integer or None")
        for field_name in ("value", "slope"):
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError(f"{field_name} must be numeric or None")
                if not math.isfinite(float(value)):
                    raise ValueError(f"{field_name} must be finite or None")
                object.__setattr__(self, field_name, float(value))
        if not isinstance(self.price_location, PriceLocation):
            raise TypeError("price_location must be PriceLocation")
        if not isinstance(self.availability, EvidenceAvailability):
            raise TypeError("availability must be EvidenceAvailability")


@dataclass(frozen=True, slots=True)
class TradingViewEvidenceRequest:
    evidence_id: str
    timestamp: datetime
    instrument: RuntimeInstrument
    timeframe: str
    latest_price: float | None
    latest_candle: BuildingCandle | Candle | object | None
    camarilla: CamarillaLevels | object | None
    cpr: CPRLevels | object | None
    vwap: VWAPLevels | object | None
    adr: object | None
    price_action: PriceActionState | object | None
    market_context: MarketContextState | object | None
    option_chain: OptionChainState | object | None
    moving_averages: tuple[object, ...] = ()
    momentum: object | None = None
    volume: object | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ValueError("evidence_id must be non-empty text")
        object.__setattr__(self, "evidence_id", self.evidence_id.strip())
        _validate_aware(self.timestamp, "timestamp")
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must be non-empty text")
        object.__setattr__(self, "timeframe", self.timeframe.strip())
        if self.latest_price is not None:
            if isinstance(self.latest_price, bool) or not isinstance(self.latest_price, (int, float)):
                raise TypeError("latest_price must be numeric or None")
            if not math.isfinite(float(self.latest_price)) or float(self.latest_price) <= 0:
                raise ValueError("latest_price must be positive finite or None")
            object.__setattr__(self, "latest_price", float(self.latest_price))
        if not isinstance(self.moving_averages, tuple):
            object.__setattr__(self, "moving_averages", tuple(self.moving_averages))
        if self.correlation_id is not None:
            if not isinstance(self.correlation_id, str):
                raise TypeError("correlation_id must be text or None")
            object.__setattr__(self, "correlation_id", self.correlation_id.strip() or None)
        for source in (
            self.latest_candle,
            self.camarilla,
            self.cpr,
            self.vwap,
            self.adr,
            self.price_action,
            self.market_context,
            self.option_chain,
            self.momentum,
            self.volume,
            *self.moving_averages,
        ):
            source_timestamp = evidence_timestamp(source)
            if source_timestamp is not None and source_timestamp > self.timestamp:
                raise ValueError("source timestamp cannot be newer than request timestamp")

    def fingerprint(self) -> str:
        payload = _stable(self)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class TradingViewEvidenceSnapshot:
    evidence_id: str
    timestamp: datetime
    instrument: RuntimeInstrument
    timeframe: str
    latest_price: float | None
    latest_candle: BuildingCandle | Candle | object | None
    latest_price_status: EvidenceStatus
    latest_candle_status: EvidenceStatus
    camarilla_status: EvidenceStatus
    camarilla_region: CamarillaRegion
    nearest_camarilla_level: LevelDistance | None
    camarilla_distances: tuple[LevelDistance, ...]
    cpr_status: EvidenceStatus
    cpr_region: CPRRegion
    cpr_distance_to_pivot: float | None
    cpr_distance_to_bc: float | None
    cpr_distance_to_tc: float | None
    vwap_status: EvidenceStatus
    vwap_location: PriceLocation
    vwap_distance_points: float | None
    vwap_distance_percentage: float | None
    adr_status: EvidenceStatus
    adr_observation: object | None
    price_action_status: EvidenceStatus
    price_action_observation: PriceActionState | object | None
    market_context_status: EvidenceStatus
    market_context_observation: MarketContextState | object | None
    option_chain_status: EvidenceStatus
    option_chain_observation: OptionChainState | object | None
    moving_average_status: EvidenceStatus
    moving_average_observations: tuple[MovingAverageObservation, ...]
    momentum_status: EvidenceStatus
    momentum_observation: object | None
    volume_status: EvidenceStatus
    volume_observation: object | None
    missing_evidence: tuple[str, ...]
    invalid_evidence: tuple[str, ...]
    stale_evidence: tuple[str, ...]
    source_fingerprint: str
    correlation_id: str | None
    trade_decision_generated: bool = False
    strategy_calls: int = 0
    risk_calls: int = 0
    execution_policy_calls: int = 0
    authorization_calls: int = 0
    paper_execution_calls: int = 0
    broker_order_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        _validate_aware(self.timestamp, "timestamp")
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        for field_name in ("evidence_id", "timeframe", "source_fingerprint"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty text")
        object.__setattr__(self, "camarilla_distances", tuple(self.camarilla_distances))
        object.__setattr__(self, "moving_average_observations", tuple(self.moving_average_observations))
        for field_name in ("missing_evidence", "invalid_evidence", "stale_evidence"):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        _validate_safety(self)


@dataclass(frozen=True, slots=True)
class TradingViewEvidenceEngineSnapshot:
    enabled: bool
    lifecycle_state: TradingViewEvidenceLifecycle
    mapping_count: int
    available_mapping_count: int
    partial_mapping_count: int
    invalid_mapping_count: int
    last_evidence: TradingViewEvidenceSnapshot | None
    trade_decision_generated: bool = False
    broker_order_calls: int = 0
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool")
        if not isinstance(self.lifecycle_state, TradingViewEvidenceLifecycle):
            raise TypeError("lifecycle_state must be TradingViewEvidenceLifecycle")
        for field_name in ("mapping_count", "available_mapping_count", "partial_mapping_count", "invalid_mapping_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        _validate_safety(self)


def evidence_timestamp(source: object | None) -> datetime | None:
    if source is None:
        return None
    for name in ("timestamp", "updated_at", "end_time"):
        value = getattr(source, name, None)
        if _aware_timestamp_or_none(value) is not None:
            return value
    last_candle = getattr(source, "last_candle", None)
    value = getattr(last_candle, "end_time", None)
    if _aware_timestamp_or_none(value) is not None:
        return value
    return None


def _aware_timestamp_or_none(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _validate_aware_optional(value: datetime | None, field_name: str) -> None:
    if value is not None:
        _validate_aware(value, field_name)


def _validate_safety(value: object) -> None:
    if getattr(value, "trade_decision_generated", False) is not False:
        raise ValueError("trade_decision_generated must remain False")
    if getattr(value, "live_order_submission_enabled", False) is not False:
        raise ValueError("live_order_submission_enabled must remain False")
    for field_name in (
        "strategy_calls",
        "risk_calls",
        "execution_policy_calls",
        "authorization_calls",
        "paper_execution_calls",
        "broker_order_calls",
    ):
        if hasattr(value, field_name) and getattr(value, field_name) != 0:
            raise ValueError(f"{field_name} must remain zero")


def _stable(value: Any) -> Any:
    if isinstance(value, RuntimeInstrument):
        return value.value
    if hasattr(value, "value") and value.__class__.__module__ != "builtins":
        return getattr(value, "value")
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _stable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_stable(item) for item in value]
    if isinstance(value, list):
        return [_stable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)
