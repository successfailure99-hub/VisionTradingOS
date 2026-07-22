"""
TradingView Evidence Mapping Engine V1.
"""

from __future__ import annotations

import math

from core.base_engine import BaseEngine
from core import events
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
from .models import (
    EvidenceStatus,
    LevelDistance,
    MovingAverageObservation,
    TradingViewEvidenceEngineSnapshot,
    TradingViewEvidenceRequest,
    TradingViewEvidenceSnapshot,
    evidence_timestamp,
)


FOUNDATIONAL_EVIDENCE = (
    "latest_price",
    "latest_candle",
    "price_action",
    "camarilla",
    "cpr",
    "vwap",
    "option_chain",
    "market_context",
)
EVIDENCE_ORDER = (
    "latest_price",
    "latest_candle",
    "camarilla",
    "cpr",
    "vwap",
    "adr",
    "price_action",
    "market_context",
    "option_chain",
    "moving_averages",
    "momentum",
    "volume",
)
CAMARILLA_LEVEL_ORDER = ("H3", "H4", "H5", "H6", "L3", "L4", "L5", "L6")
_CAMARILLA_ATTRS = {
    "H3": "h3",
    "H4": "h4",
    "H5": "h5",
    "H6": "h6",
    "L3": "l3",
    "L4": "l4",
    "L5": "l5",
    "L6": "l6",
}
PRICE_TOLERANCE = 1e-9


class TradingViewEvidenceMappingEngine(BaseEngine):
    """
    Maps existing upstream chart evidence into one immutable observation snapshot.
    """

    def __init__(self, event_bus, *, instrument: str, timeframe: str, maximum_source_age_seconds: int = 300):
        super().__init__(event_bus)
        self._instrument = _normalize_text(instrument, "instrument").upper()
        if self._instrument not in {"NIFTY", "BANKNIFTY", "SENSEX"}:
            raise ValueError("unsupported instrument")
        self._timeframe = _normalize_text(timeframe, "timeframe")
        if isinstance(maximum_source_age_seconds, bool) or not isinstance(maximum_source_age_seconds, int) or maximum_source_age_seconds < 0:
            raise ValueError("maximum_source_age_seconds must be a non-negative integer")
        self._maximum_source_age_seconds = maximum_source_age_seconds
        self._lifecycle_state = TradingViewEvidenceLifecycle.CREATED
        self._results: dict[str, TradingViewEvidenceSnapshot] = {}
        self._fingerprints: dict[str, str] = {}
        self._last_evidence: TradingViewEvidenceSnapshot | None = None
        self._mapping_count = 0
        self._available_mapping_count = 0
        self._partial_mapping_count = 0
        self._invalid_mapping_count = 0

    def start(self) -> TradingViewEvidenceEngineSnapshot:
        if self._lifecycle_state is TradingViewEvidenceLifecycle.CREATED:
            self._lifecycle_state = TradingViewEvidenceLifecycle.READY
            self._publish_state()
        return self.snapshot()

    def map_evidence(self, request: TradingViewEvidenceRequest) -> TradingViewEvidenceSnapshot:
        if self._lifecycle_state is TradingViewEvidenceLifecycle.STOPPED:
            raise RuntimeError("tradingview evidence mapping engine is stopped")
        if self._lifecycle_state is TradingViewEvidenceLifecycle.FAILED:
            raise RuntimeError("tradingview evidence mapping engine is failed")
        if self._lifecycle_state is TradingViewEvidenceLifecycle.CREATED:
            raise RuntimeError("tradingview evidence mapping engine must be started")
        if not isinstance(request, TradingViewEvidenceRequest):
            raise TypeError("request must be TradingViewEvidenceRequest")
        self._validate_request_context(request)
        fingerprint = request.fingerprint()
        stored = self._results.get(request.evidence_id)
        if stored is not None:
            if self._fingerprints[request.evidence_id] != fingerprint:
                raise ValueError("evidence_id already exists for different request")
            return stored

        try:
            result = self._map(request, fingerprint)
        except Exception as exc:
            if isinstance(exc, (TypeError, ValueError, RuntimeError)):
                raise
            self._lifecycle_state = TradingViewEvidenceLifecycle.FAILED
            self._event_bus.publish(events.TRADINGVIEW_EVIDENCE_FAILED, self.snapshot())
            self._publish_state()
            raise

        self._results[request.evidence_id] = result
        self._fingerprints[request.evidence_id] = fingerprint
        self._last_evidence = result
        self._data = result
        self._mapping_count += 1
        if result.invalid_evidence:
            self._invalid_mapping_count += 1
        is_partial = any(
            getattr(result, f"{name}_status").availability is not EvidenceAvailability.AVAILABLE
            for name in FOUNDATIONAL_EVIDENCE
        )
        if is_partial:
            self._partial_mapping_count += 1
        else:
            self._available_mapping_count += 1
        if self._lifecycle_state is TradingViewEvidenceLifecycle.READY:
            self._lifecycle_state = TradingViewEvidenceLifecycle.ACTIVE
        if result.invalid_evidence:
            self._event_bus.publish(events.TRADINGVIEW_EVIDENCE_INVALID, result)
        elif is_partial:
            self._event_bus.publish(events.TRADINGVIEW_EVIDENCE_PARTIAL, result)
        else:
            self._event_bus.publish(events.TRADINGVIEW_EVIDENCE_MAPPED, result)
        self._publish_state()
        return result

    def get_evidence(self, evidence_id: str) -> TradingViewEvidenceSnapshot | None:
        if not isinstance(evidence_id, str):
            return None
        return self._results.get(evidence_id.strip())

    def snapshot(self) -> TradingViewEvidenceEngineSnapshot:
        return TradingViewEvidenceEngineSnapshot(
            enabled=True,
            lifecycle_state=self._lifecycle_state,
            mapping_count=self._mapping_count,
            available_mapping_count=self._available_mapping_count,
            partial_mapping_count=self._partial_mapping_count,
            invalid_mapping_count=self._invalid_mapping_count,
            last_evidence=self._last_evidence,
            trade_decision_generated=False,
            broker_order_calls=0,
            live_order_submission_enabled=False,
        )

    def stop(self) -> TradingViewEvidenceEngineSnapshot:
        if self._lifecycle_state in {
            TradingViewEvidenceLifecycle.READY,
            TradingViewEvidenceLifecycle.ACTIVE,
        }:
            self._lifecycle_state = TradingViewEvidenceLifecycle.STOPPED
            self._publish_state()
        return self.snapshot()

    def reset(self) -> TradingViewEvidenceEngineSnapshot:
        self._results.clear()
        self._fingerprints.clear()
        self._last_evidence = None
        self._data = None
        self._mapping_count = 0
        self._available_mapping_count = 0
        self._partial_mapping_count = 0
        self._invalid_mapping_count = 0
        self._lifecycle_state = TradingViewEvidenceLifecycle.READY
        self._publish_state()
        return self.snapshot()

    def _map(self, request: TradingViewEvidenceRequest, fingerprint: str) -> TradingViewEvidenceSnapshot:
        statuses = {
            "latest_price": self._latest_price_status(request),
            "latest_candle": self._status("latest_candle", request.latest_candle, (BuildingCandle, Candle), request),
            "camarilla": self._status("camarilla", request.camarilla, CamarillaLevels, request),
            "cpr": self._status("cpr", request.cpr, CPRLevels, request),
            "vwap": self._status("vwap", request.vwap, VWAPLevels, request),
            "adr": self._status("adr", request.adr, (), request),
            "price_action": self._status("price_action", request.price_action, PriceActionState, request),
            "market_context": self._status("market_context", request.market_context, MarketContextState, request),
            "option_chain": self._status("option_chain", request.option_chain, OptionChainState, request),
            "moving_averages": self._moving_average_status(request),
            "momentum": self._status("momentum", request.momentum, (), request),
            "volume": self._status("volume", request.volume, (), request),
        }
        camarilla_distances, nearest_level, camarilla_region = self._map_camarilla(request, statuses["camarilla"])
        cpr_region, cpr_pivot, cpr_bc, cpr_tc = self._map_cpr(request, statuses["cpr"])
        vwap_location, vwap_points, vwap_percentage = self._map_vwap(request, statuses["vwap"])
        moving_average_observations = self._map_moving_averages(request, statuses["moving_averages"])
        return TradingViewEvidenceSnapshot(
            evidence_id=request.evidence_id,
            timestamp=request.timestamp,
            instrument=request.instrument,
            timeframe=request.timeframe,
            latest_price=request.latest_price,
            latest_candle=request.latest_candle,
            latest_price_status=statuses["latest_price"],
            latest_candle_status=statuses["latest_candle"],
            camarilla_status=statuses["camarilla"],
            camarilla_region=camarilla_region,
            nearest_camarilla_level=nearest_level,
            camarilla_distances=camarilla_distances,
            cpr_status=statuses["cpr"],
            cpr_region=cpr_region,
            cpr_distance_to_pivot=cpr_pivot,
            cpr_distance_to_bc=cpr_bc,
            cpr_distance_to_tc=cpr_tc,
            vwap_status=statuses["vwap"],
            vwap_location=vwap_location,
            vwap_distance_points=vwap_points,
            vwap_distance_percentage=vwap_percentage,
            adr_status=statuses["adr"],
            adr_observation=request.adr if statuses["adr"].availability is EvidenceAvailability.AVAILABLE else None,
            price_action_status=statuses["price_action"],
            price_action_observation=request.price_action if statuses["price_action"].availability is EvidenceAvailability.AVAILABLE else None,
            market_context_status=statuses["market_context"],
            market_context_observation=request.market_context if statuses["market_context"].availability is EvidenceAvailability.AVAILABLE else None,
            option_chain_status=statuses["option_chain"],
            option_chain_observation=request.option_chain if statuses["option_chain"].availability is EvidenceAvailability.AVAILABLE else None,
            moving_average_status=statuses["moving_averages"],
            moving_average_observations=moving_average_observations,
            momentum_status=statuses["momentum"],
            momentum_observation=request.momentum if statuses["momentum"].availability is EvidenceAvailability.AVAILABLE else None,
            volume_status=statuses["volume"],
            volume_observation=request.volume if statuses["volume"].availability is EvidenceAvailability.AVAILABLE else None,
            missing_evidence=tuple(name for name in EVIDENCE_ORDER if statuses[name].availability is EvidenceAvailability.MISSING),
            invalid_evidence=tuple(name for name in EVIDENCE_ORDER if statuses[name].availability is EvidenceAvailability.INVALID),
            stale_evidence=tuple(name for name in EVIDENCE_ORDER if statuses[name].availability is EvidenceAvailability.STALE),
            source_fingerprint=fingerprint,
            correlation_id=request.correlation_id,
            trade_decision_generated=False,
            strategy_calls=0,
            risk_calls=0,
            execution_policy_calls=0,
            authorization_calls=0,
            paper_execution_calls=0,
            broker_order_calls=0,
            live_order_submission_enabled=False,
        )

    def _latest_price_status(self, request: TradingViewEvidenceRequest) -> EvidenceStatus:
        if request.latest_price is None:
            return EvidenceStatus("latest_price", EvidenceAvailability.MISSING, None, None, "latest price is unavailable")
        return EvidenceStatus("latest_price", EvidenceAvailability.AVAILABLE, request.timestamp, 0.0, None)

    def _status(self, name: str, value: object | None, expected_type, request: TradingViewEvidenceRequest) -> EvidenceStatus:
        if value is None:
            return EvidenceStatus(name, EvidenceAvailability.MISSING, None, None, f"{name} is unavailable")
        if expected_type == ():
            return EvidenceStatus(name, EvidenceAvailability.MISSING, evidence_timestamp(value), None, f"{name} has no implemented upstream model")
        if not isinstance(value, expected_type):
            return EvidenceStatus(name, EvidenceAvailability.INVALID, evidence_timestamp(value), None, f"{name} type is invalid")
        source_timestamp = evidence_timestamp(value)
        age_seconds = None
        availability = EvidenceAvailability.AVAILABLE
        if source_timestamp is not None:
            age_seconds = (request.timestamp - source_timestamp).total_seconds()
            if age_seconds > self._maximum_source_age_seconds:
                availability = EvidenceAvailability.STALE
        return EvidenceStatus(name, availability, source_timestamp, age_seconds, None)

    def _moving_average_status(self, request: TradingViewEvidenceRequest) -> EvidenceStatus:
        if not request.moving_averages:
            return EvidenceStatus("moving_averages", EvidenceAvailability.MISSING, None, None, "moving averages are unavailable")
        for item in request.moving_averages:
            if not isinstance(item, MovingAverageObservation):
                return EvidenceStatus("moving_averages", EvidenceAvailability.INVALID, evidence_timestamp(item), None, "moving average type is invalid")
        timestamps = tuple(filter(None, (evidence_timestamp(item) for item in request.moving_averages)))
        source_timestamp = max(timestamps) if timestamps else None
        age_seconds = None
        availability = EvidenceAvailability.AVAILABLE
        if source_timestamp is not None:
            age_seconds = (request.timestamp - source_timestamp).total_seconds()
            if age_seconds > self._maximum_source_age_seconds:
                availability = EvidenceAvailability.STALE
        return EvidenceStatus("moving_averages", availability, source_timestamp, age_seconds, None)

    def _map_camarilla(self, request: TradingViewEvidenceRequest, status: EvidenceStatus):
        if request.latest_price is None or status.availability is not EvidenceAvailability.AVAILABLE:
            return (), None, CamarillaRegion.UNKNOWN
        levels = request.camarilla
        price = request.latest_price
        distances = tuple(
            self._level_distance(name, price, getattr(levels, _CAMARILLA_ATTRS[name]))
            for name in CAMARILLA_LEVEL_ORDER
        )
        nearest = min(distances, key=lambda item: (abs(item.absolute_points), CAMARILLA_LEVEL_ORDER.index(item.level_name)))
        return distances, nearest, _camarilla_region(price, levels)

    def _map_cpr(self, request: TradingViewEvidenceRequest, status: EvidenceStatus):
        if request.latest_price is None or status.availability is not EvidenceAvailability.AVAILABLE:
            return CPRRegion.UNKNOWN, None, None, None
        cpr = request.cpr
        price = request.latest_price
        lower = min(cpr.bc, cpr.tc)
        upper = max(cpr.bc, cpr.tc)
        if price > upper:
            region = CPRRegion.ABOVE_CPR
        elif price < lower:
            region = CPRRegion.BELOW_CPR
        else:
            region = CPRRegion.INSIDE_CPR
        return region, price - cpr.pivot, price - cpr.bc, price - cpr.tc

    def _map_vwap(self, request: TradingViewEvidenceRequest, status: EvidenceStatus):
        if request.latest_price is None or status.availability is not EvidenceAvailability.AVAILABLE:
            return PriceLocation.UNKNOWN, None, None
        points = request.latest_price - request.vwap.vwap
        percentage = (points / request.vwap.vwap) * 100
        return _price_location(request.latest_price, request.vwap.vwap), points, percentage

    def _map_moving_averages(self, request: TradingViewEvidenceRequest, status: EvidenceStatus) -> tuple[MovingAverageObservation, ...]:
        if status.availability is not EvidenceAvailability.AVAILABLE or request.latest_price is None:
            return ()
        observations = []
        for item in request.moving_averages:
            location = _price_location(request.latest_price, item.value) if item.value is not None else PriceLocation.UNKNOWN
            observations.append(
                MovingAverageObservation(
                    name=item.name,
                    period=item.period,
                    value=item.value,
                    price_location=location,
                    slope=item.slope,
                    availability=item.availability,
                )
            )
        return tuple(observations)

    def _level_distance(self, name: str, price: float, level: float) -> LevelDistance:
        points = price - level
        percentage = (points / level) * 100
        return LevelDistance(name, level, points, percentage, _price_location(price, level))

    def _validate_request_context(self, request: TradingViewEvidenceRequest) -> None:
        if request.instrument.value != self._instrument:
            raise ValueError("TradingView evidence request instrument does not match engine.")
        if request.timeframe != self._timeframe:
            raise ValueError("TradingView evidence request timeframe does not match engine.")

    def _publish_state(self) -> None:
        self._event_bus.publish(events.TRADINGVIEW_EVIDENCE_STATE_UPDATED, self.snapshot())


def _price_location(price: float | None, level: float | None) -> PriceLocation:
    if price is None or level is None:
        return PriceLocation.UNKNOWN
    if not math.isfinite(float(price)) or not math.isfinite(float(level)):
        return PriceLocation.UNKNOWN
    if abs(float(price) - float(level)) <= PRICE_TOLERANCE:
        return PriceLocation.AT
    if float(price) > float(level):
        return PriceLocation.ABOVE
    return PriceLocation.BELOW


def _camarilla_region(price: float, levels: CamarillaLevels) -> CamarillaRegion:
    if price > levels.h6:
        return CamarillaRegion.ABOVE_H6
    if price > levels.h5:
        return CamarillaRegion.H5_H6
    if price > levels.h4:
        return CamarillaRegion.H4_H5
    if price > levels.h3:
        return CamarillaRegion.H3_H4
    if price >= levels.l3:
        return CamarillaRegion.L3_H3
    if price >= levels.l4:
        return CamarillaRegion.L4_L3
    if price >= levels.l5:
        return CamarillaRegion.L5_L4
    if price >= levels.l6:
        return CamarillaRegion.L6_L5
    return CamarillaRegion.BELOW_L6


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized
