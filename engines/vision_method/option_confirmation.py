"""
Vision Method option-chain confirmation.

VM-08 consumes setup qualification and canonical option-chain analytics only.
It confirms, contradicts, or marks option-chain evidence unavailable without
creating trades, directions, strategy, risk, or execution intent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from application.enums import RuntimeInstrument
from engines.option_chain.models import OptionChainSnapshot
from engines.option_chain_analytics.enums import (
    OptionAnalyticsBias,
    OptionPressureType,
    OptionTrendDirection,
)
from engines.option_chain_analytics.models import OptionChainAnalyticsSnapshot

from .enums import (
    VisionLevelQuality,
    VisionOptionConfirmation,
    VisionSetupDirection,
    VisionSetupType,
)
from .models import (
    VisionOptionConfirmationContext,
    VisionSetupQualificationContext,
)


DEFAULT_MAX_OPTION_CONFIRMATION_AGE = timedelta(minutes=5)
DEFAULT_OPTION_CONFIRMATION_TIMESTAMP_TOLERANCE = timedelta(seconds=1)


@dataclass(frozen=True, slots=True)
class VisionOptionConfirmationRequest:
    instrument: RuntimeInstrument
    expiry: date
    timestamp: datetime
    setup_qualification: VisionSetupQualificationContext
    option_chain: OptionChainSnapshot | None
    analytics: OptionChainAnalyticsSnapshot | None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if not isinstance(self.expiry, date) or isinstance(self.expiry, datetime):
            raise TypeError("expiry must be date.")
        _validate_aware(self.timestamp, "timestamp")
        if not isinstance(self.setup_qualification, VisionSetupQualificationContext):
            raise TypeError("setup_qualification must be VisionSetupQualificationContext.")
        if self.option_chain is not None and not isinstance(self.option_chain, OptionChainSnapshot):
            raise TypeError("option_chain must be OptionChainSnapshot or None.")
        if self.analytics is not None and not isinstance(self.analytics, OptionChainAnalyticsSnapshot):
            raise TypeError("analytics must be OptionChainAnalyticsSnapshot or None.")


def assemble_vision_option_confirmation_context(
    request: VisionOptionConfirmationRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    expiry: date | None = None,
    max_snapshot_age: timedelta = DEFAULT_MAX_OPTION_CONFIRMATION_AGE,
    timestamp_tolerance: timedelta = DEFAULT_OPTION_CONFIRMATION_TIMESTAMP_TOLERANCE,
) -> VisionOptionConfirmationContext:
    """
    Confirm the qualified chart setup against existing option-chain analytics.
    """

    validate_option_confirmation_request(
        request,
        instrument=instrument,
        expiry=expiry,
        max_snapshot_age=max_snapshot_age,
        timestamp_tolerance=timestamp_tolerance,
    )
    if request.option_chain is None or request.analytics is None:
        return validate_option_confirmation_context(
            VisionOptionConfirmationContext(
                confirmation_state=VisionOptionConfirmation.UNAVAILABLE,
                supporting_factors=(),
                contradicting_factors=(),
                neutral_factors=("Option chain unavailable",),
                quality=VisionLevelQuality.INSUFFICIENT,
                timestamp=request.timestamp,
            )
        )
    if not request.setup_qualification.eligible_for_option_confirmation:
        return validate_option_confirmation_context(
            VisionOptionConfirmationContext(
                confirmation_state=VisionOptionConfirmation.NEUTRAL,
                supporting_factors=(),
                contradicting_factors=(),
                neutral_factors=("Setup is not eligible for option confirmation",),
                quality=VisionLevelQuality.PARTIAL,
                timestamp=request.timestamp,
            )
        )

    direction = _setup_direction(request.setup_qualification)
    supporting = list(_supporting_factors(request.analytics, direction))
    contradicting = list(_contradicting_factors(request.analytics, direction))
    neutral = list(_neutral_factors(request.analytics, direction))
    state = _classify_confirmation(supporting, contradicting, neutral, direction)
    quality = _quality_for_state(state)

    return validate_option_confirmation_context(
        VisionOptionConfirmationContext(
            confirmation_state=state,
            supporting_factors=tuple(supporting),
            contradicting_factors=tuple(contradicting),
            neutral_factors=tuple(neutral),
            quality=quality,
            timestamp=request.timestamp,
        )
    )


def validate_option_confirmation_request(
    request: VisionOptionConfirmationRequest,
    *,
    instrument: RuntimeInstrument | None = None,
    expiry: date | None = None,
    max_snapshot_age: timedelta = DEFAULT_MAX_OPTION_CONFIRMATION_AGE,
    timestamp_tolerance: timedelta = DEFAULT_OPTION_CONFIRMATION_TIMESTAMP_TOLERANCE,
) -> VisionOptionConfirmationRequest:
    if not isinstance(request, VisionOptionConfirmationRequest):
        raise TypeError("request must be VisionOptionConfirmationRequest.")
    if not isinstance(max_snapshot_age, timedelta):
        raise TypeError("max_snapshot_age must be timedelta.")
    if max_snapshot_age.total_seconds() < 0:
        raise ValueError("max_snapshot_age cannot be negative.")
    if not isinstance(timestamp_tolerance, timedelta):
        raise TypeError("timestamp_tolerance must be timedelta.")
    if timestamp_tolerance.total_seconds() < 0:
        raise ValueError("timestamp_tolerance cannot be negative.")
    expected_instrument = instrument or request.instrument
    expected_expiry = expiry or request.expiry
    if request.instrument is not expected_instrument:
        raise ValueError("instrument mismatch.")
    if request.expiry != expected_expiry:
        raise ValueError("expiry mismatch.")
    if request.option_chain is None or request.analytics is None:
        return request

    if request.option_chain.symbol != request.instrument.value:
        raise ValueError("option chain instrument mismatch.")
    if request.analytics.underlying.value != request.instrument.value:
        raise ValueError("analytics instrument mismatch.")
    if request.option_chain.expiry_date != request.expiry:
        raise ValueError("option chain expiry mismatch.")
    if request.analytics.expiry != request.expiry:
        raise ValueError("analytics expiry mismatch.")
    if request.analytics.source_snapshot != request.option_chain:
        raise ValueError("analytics source snapshot mismatch.")
    _validate_same_runtime_session(request.timestamp, request.option_chain.timestamp, "option_chain.timestamp")
    _validate_same_runtime_session(request.timestamp, request.analytics.timestamp, "analytics.timestamp")
    _validate_not_future(request.option_chain.timestamp, request.timestamp, "option_chain.timestamp", tolerance=timestamp_tolerance)
    _validate_not_future(request.analytics.timestamp, request.timestamp, "analytics.timestamp", tolerance=timestamp_tolerance)
    if request.timestamp - request.option_chain.timestamp > max_snapshot_age:
        raise ValueError("stale option chain.")
    if request.timestamp - request.analytics.timestamp > max_snapshot_age:
        raise ValueError("stale option analytics.")
    return request


def validate_option_confirmation_context(context: VisionOptionConfirmationContext) -> VisionOptionConfirmationContext:
    if not isinstance(context, VisionOptionConfirmationContext):
        raise TypeError("context must be VisionOptionConfirmationContext.")
    return context


def _setup_direction(setup: VisionSetupQualificationContext) -> str | None:
    if setup.setup_type in (VisionSetupType.FAILED_BREAKOUT, VisionSetupType.RANGE_FADE, VisionSetupType.NO_QUALITY_SETUP):
        return None
    if setup.setup_direction is VisionSetupDirection.BULLISH:
        return "bullish"
    if setup.setup_direction is VisionSetupDirection.BEARISH:
        return "bearish"
    return None


def _supporting_factors(analytics: OptionChainAnalyticsSnapshot, direction: str | None) -> tuple[str, ...]:
    if direction is None:
        return ()
    factors: list[str] = []
    if direction == "bullish":
        if analytics.bias in (OptionAnalyticsBias.BULLISH, OptionAnalyticsBias.STRONGLY_BULLISH):
            factors.append("Option analytics bias bullish")
        if _dominant_pressure(analytics) is OptionPressureType.PUT_WRITING:
            factors.append("Put writing supports setup")
        if analytics.pcr_trend.direction is OptionTrendDirection.RISING:
            factors.append("PCR rising")
        if analytics.change_oi_pcr_trend.direction is OptionTrendDirection.RISING:
            factors.append("Change OI PCR rising")
    else:
        if analytics.bias in (OptionAnalyticsBias.BEARISH, OptionAnalyticsBias.STRONGLY_BEARISH):
            factors.append("Option analytics bias bearish")
        if _dominant_pressure(analytics) is OptionPressureType.CALL_WRITING:
            factors.append("Call writing supports setup")
        if analytics.pcr_trend.direction is OptionTrendDirection.FALLING:
            factors.append("PCR falling")
        if analytics.change_oi_pcr_trend.direction is OptionTrendDirection.FALLING:
            factors.append("Change OI PCR falling")
    return _dedupe(factors)


def _contradicting_factors(analytics: OptionChainAnalyticsSnapshot, direction: str | None) -> tuple[str, ...]:
    if direction is None:
        return ()
    factors: list[str] = []
    if direction == "bullish":
        if analytics.bias in (OptionAnalyticsBias.BEARISH, OptionAnalyticsBias.STRONGLY_BEARISH):
            factors.append("Option analytics bias bearish")
        if _dominant_pressure(analytics) is OptionPressureType.CALL_WRITING:
            factors.append("Call writing contradicts setup")
        if analytics.pcr_trend.direction is OptionTrendDirection.FALLING:
            factors.append("PCR falling")
        if analytics.change_oi_pcr_trend.direction is OptionTrendDirection.FALLING:
            factors.append("Change OI PCR falling")
    else:
        if analytics.bias in (OptionAnalyticsBias.BULLISH, OptionAnalyticsBias.STRONGLY_BULLISH):
            factors.append("Option analytics bias bullish")
        if _dominant_pressure(analytics) is OptionPressureType.PUT_WRITING:
            factors.append("Put writing contradicts setup")
        if analytics.pcr_trend.direction is OptionTrendDirection.RISING:
            factors.append("PCR rising")
        if analytics.change_oi_pcr_trend.direction is OptionTrendDirection.RISING:
            factors.append("Change OI PCR rising")
    return _dedupe(factors)


def _neutral_factors(analytics: OptionChainAnalyticsSnapshot, direction: str | None) -> tuple[str, ...]:
    factors: list[str] = []
    if direction is None:
        factors.append("Setup direction unavailable")
    if analytics.bias is OptionAnalyticsBias.NEUTRAL:
        factors.append("Option analytics bias neutral")
    if analytics.bias is OptionAnalyticsBias.CONFLICTED:
        factors.append("Option analytics bias conflicted")
    if _dominant_pressure(analytics) in (
        OptionPressureType.BALANCED,
        OptionPressureType.MIXED,
        OptionPressureType.INSUFFICIENT_DATA,
    ):
        factors.append("Option pressure not directional")
    if analytics.pcr_trend.direction is OptionTrendDirection.FLAT:
        factors.append("PCR flat")
    if analytics.change_oi_pcr_trend.direction is OptionTrendDirection.FLAT:
        factors.append("Change OI PCR flat")
    return _dedupe(factors)


def _classify_confirmation(
    supporting: list[str],
    contradicting: list[str],
    neutral: list[str],
    direction: str | None,
) -> VisionOptionConfirmation:
    if direction is None:
        return VisionOptionConfirmation.NEUTRAL
    if supporting and contradicting:
        return VisionOptionConfirmation.PARTIAL
    if supporting:
        return VisionOptionConfirmation.CONFIRMS
    if contradicting:
        return VisionOptionConfirmation.CONTRADICTS
    if neutral:
        return VisionOptionConfirmation.NEUTRAL
    return VisionOptionConfirmation.NEUTRAL


def _quality_for_state(state: VisionOptionConfirmation) -> VisionLevelQuality:
    if state is VisionOptionConfirmation.UNAVAILABLE:
        return VisionLevelQuality.INSUFFICIENT
    if state is VisionOptionConfirmation.PARTIAL:
        return VisionLevelQuality.PARTIAL
    return VisionLevelQuality.FULL


def _dominant_pressure(analytics: OptionChainAnalyticsSnapshot) -> OptionPressureType:
    return analytics.pressure.dominant_pressure


def _validate_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _validate_same_runtime_session(trigger: datetime, value: datetime, field_name: str) -> None:
    _validate_aware(value, field_name)
    if value.astimezone(trigger.tzinfo).date() != trigger.date():
        raise ValueError(f"{field_name} trading session mismatch.")


def _validate_not_future(value: datetime, trigger: datetime, field_name: str, *, tolerance: timedelta) -> None:
    if value - trigger > tolerance:
        raise ValueError(f"{field_name} cannot be after request timestamp.")


def _dedupe(values: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            result.append(value)
            seen.add(key)
    return tuple(result)
