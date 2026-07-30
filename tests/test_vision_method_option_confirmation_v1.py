from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from application.enums import RuntimeInstrument
from core.enums.instrument import Instrument
from engines.option_chain.enums import PositioningBias, PressureType
from engines.option_chain.models import OptionChainSnapshot, OptionChainState
from engines.option_chain_analytics.enums import (
    OptionAnalyticsBias,
    OptionLevelMigration,
    OptionPressureType,
    OptionTrendDirection,
)
from engines.option_chain_analytics.models import (
    OptionChainAnalyticsSnapshot,
    OptionMetricTrend,
    OptionPressureSummary,
)
from engines.vision_method import (
    VisionLevelQuality,
    VisionOptionConfirmation,
    VisionOptionConfirmationContext,
    VisionOptionConfirmationRequest,
    VisionSetupQualificationContext,
    VisionSetupQuality,
    VisionSetupType,
    assemble_vision_option_confirmation_context,
)


IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 7, 29, 10, 30, tzinfo=IST)
EXPIRY = date(2026, 7, 30)


def setup(
    *,
    setup_type: VisionSetupType = VisionSetupType.TREND_CONTINUATION,
    supporting: tuple[str, ...] = ("Above CPR", "Above H3", "Bullish BOS"),
    eligible: bool = True,
    quality: VisionSetupQuality = VisionSetupQuality.HIGH,
) -> VisionSetupQualificationContext:
    return VisionSetupQualificationContext(
        setup_type=setup_type,
        setup_quality=quality,
        blocking_reasons=(),
        supporting_reasons=supporting,
        eligible_for_option_confirmation=eligible,
    )


def option_chain(
    *,
    symbol: str = "NIFTY",
    expiry: date = EXPIRY,
    timestamp: datetime = NOW,
) -> OptionChainSnapshot:
    return OptionChainSnapshot(
        symbol=symbol,
        exchange="NSE",
        expiry_date=expiry,
        timestamp=timestamp,
        underlying_price=24000.0,
        strikes=(),
    )


def option_state(
    snapshot: OptionChainSnapshot,
    *,
    bias: PositioningBias = PositioningBias.BULLISH,
) -> OptionChainState:
    return OptionChainState(
        symbol=snapshot.symbol,
        exchange=snapshot.exchange,
        expiry_date=snapshot.expiry_date,
        timestamp=snapshot.timestamp,
        underlying_price=snapshot.underlying_price,
        atm_strike=24000.0,
        strike_count=0,
        total_call_oi=1000,
        total_put_oi=2000,
        total_call_change_oi=100,
        total_put_change_oi=500,
        oi_pcr=1.5,
        change_oi_pcr=2.0,
        max_call_oi=None,
        max_put_oi=None,
        max_call_change_oi=None,
        max_put_change_oi=None,
        resistance_strike=24100.0,
        support_strike=23900.0,
        max_pain_strike=24000.0,
        call_pressure=PressureType.CALL_WRITING,
        put_pressure=PressureType.PUT_WRITING,
        positioning_bias=bias,
        strikes=(),
    )


def trend(direction: OptionTrendDirection) -> OptionMetricTrend:
    if direction is OptionTrendDirection.RISING:
        return OptionMetricTrend(1.2, 1.0, 0.2, direction)
    if direction is OptionTrendDirection.FALLING:
        return OptionMetricTrend(0.8, 1.0, -0.2, direction)
    return OptionMetricTrend(1.0, 1.0, 0.0, direction)


def analytics(
    snapshot: OptionChainSnapshot,
    *,
    bias: OptionAnalyticsBias = OptionAnalyticsBias.BULLISH,
    pressure: OptionPressureType = OptionPressureType.PUT_WRITING,
    pcr_direction: OptionTrendDirection = OptionTrendDirection.RISING,
    change_pcr_direction: OptionTrendDirection = OptionTrendDirection.RISING,
    bullish_score: int = 4,
    bearish_score: int = 1,
) -> OptionChainAnalyticsSnapshot:
    pressure_summary = OptionPressureSummary(
        call_writing_oi=2000 if pressure is OptionPressureType.CALL_WRITING else 100,
        put_writing_oi=2000 if pressure is OptionPressureType.PUT_WRITING else 100,
        call_unwinding_oi=0,
        put_unwinding_oi=0,
        call_short_buildup_count=2 if pressure is OptionPressureType.CALL_WRITING else 0,
        put_short_buildup_count=2 if pressure is OptionPressureType.PUT_WRITING else 0,
        call_short_covering_count=0,
        put_short_covering_count=0,
        pressure_ratio=1.0,
        dominant_pressure=pressure,
    )
    return OptionChainAnalyticsSnapshot(
        underlying=Instrument.from_symbol(snapshot.symbol),
        expiry=snapshot.expiry_date,
        timestamp=snapshot.timestamp,
        source_snapshot=snapshot,
        source_analysis=option_state(snapshot),
        strikes=(),
        pressure=pressure_summary,
        pcr_trend=trend(pcr_direction),
        change_oi_pcr_trend=trend(change_pcr_direction),
        max_pain_trend=trend(OptionTrendDirection.FLAT),
        support_migration=OptionLevelMigration.UNCHANGED,
        resistance_migration=OptionLevelMigration.UNCHANGED,
        atm_migration=OptionLevelMigration.UNCHANGED,
        previous_support=23900.0,
        current_support=23900.0,
        previous_resistance=24100.0,
        current_resistance=24100.0,
        previous_atm_strike=24000.0,
        current_atm_strike=24000.0,
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        bias=bias,
        rationale=("canonical analytics fixture",),
    )


def request(
    *,
    setup_context: VisionSetupQualificationContext | None = None,
    chain: OptionChainSnapshot | None = None,
    analytics_snapshot: OptionChainAnalyticsSnapshot | None = None,
    timestamp: datetime = NOW,
    expiry: date = EXPIRY,
) -> VisionOptionConfirmationRequest:
    if chain is None:
        chain = option_chain(expiry=expiry, timestamp=timestamp)
    if analytics_snapshot is None:
        analytics_snapshot = analytics(chain)
    return VisionOptionConfirmationRequest(
        instrument=RuntimeInstrument.NIFTY,
        expiry=expiry,
        timestamp=timestamp,
        setup_qualification=setup_context or setup(),
        option_chain=chain,
        analytics=analytics_snapshot,
    )


def test_option_chain_confirms_bullish_setup_with_put_writing():
    result = assemble_vision_option_confirmation_context(request())

    assert result.confirmation_state is VisionOptionConfirmation.CONFIRMS
    assert result.quality is VisionLevelQuality.FULL
    assert "Put writing supports setup" in result.supporting_factors
    assert "Option analytics bias bullish" in result.supporting_factors
    assert result.contradicting_factors == ()


def test_option_chain_contradicts_bullish_setup_with_call_writing():
    chain = option_chain()
    bearish_analytics = analytics(
        chain,
        bias=OptionAnalyticsBias.BEARISH,
        pressure=OptionPressureType.CALL_WRITING,
        pcr_direction=OptionTrendDirection.FALLING,
        change_pcr_direction=OptionTrendDirection.FALLING,
        bullish_score=1,
        bearish_score=4,
    )

    result = assemble_vision_option_confirmation_context(request(chain=chain, analytics_snapshot=bearish_analytics))

    assert result.confirmation_state is VisionOptionConfirmation.CONTRADICTS
    assert result.quality is VisionLevelQuality.FULL
    assert "Call writing contradicts setup" in result.contradicting_factors
    assert "Option analytics bias bearish" in result.contradicting_factors


def test_option_chain_partial_when_confirmation_and_contradiction_coexist():
    chain = option_chain()
    mixed_analytics = analytics(
        chain,
        bias=OptionAnalyticsBias.BEARISH,
        pressure=OptionPressureType.PUT_WRITING,
        pcr_direction=OptionTrendDirection.RISING,
        change_pcr_direction=OptionTrendDirection.FALLING,
    )

    result = assemble_vision_option_confirmation_context(request(chain=chain, analytics_snapshot=mixed_analytics))

    assert result.confirmation_state is VisionOptionConfirmation.PARTIAL
    assert result.quality is VisionLevelQuality.PARTIAL
    assert result.supporting_factors
    assert result.contradicting_factors


def test_option_chain_neutral_when_setup_direction_is_unavailable():
    chain = option_chain()
    neutral_analytics = analytics(
        chain,
        bias=OptionAnalyticsBias.NEUTRAL,
        pressure=OptionPressureType.BALANCED,
        pcr_direction=OptionTrendDirection.FLAT,
        change_pcr_direction=OptionTrendDirection.FLAT,
        bullish_score=1,
        bearish_score=1,
    )

    result = assemble_vision_option_confirmation_context(
        request(
            setup_context=setup(setup_type=VisionSetupType.RANGE_FADE, supporting=("Inside CPR",), quality=VisionSetupQuality.MEDIUM),
            chain=chain,
            analytics_snapshot=neutral_analytics,
        )
    )

    assert result.confirmation_state is VisionOptionConfirmation.NEUTRAL
    assert result.quality is VisionLevelQuality.FULL
    assert "Setup direction unavailable" in result.neutral_factors


def test_option_chain_unavailable_when_chain_or_analytics_missing():
    result = assemble_vision_option_confirmation_context(
        VisionOptionConfirmationRequest(
            instrument=RuntimeInstrument.NIFTY,
            expiry=EXPIRY,
            timestamp=NOW,
            setup_qualification=setup(),
            option_chain=None,
            analytics=None,
        )
    )

    assert result.confirmation_state is VisionOptionConfirmation.UNAVAILABLE
    assert result.quality is VisionLevelQuality.INSUFFICIENT
    assert result.neutral_factors == ("Option chain unavailable",)


def test_option_confirmation_validator_rejects_mismatches_and_stale_chain():
    with pytest.raises(ValueError, match="instrument mismatch"):
        assemble_vision_option_confirmation_context(request(), instrument=RuntimeInstrument.BANKNIFTY)

    wrong_symbol = option_chain(symbol="BANKNIFTY")
    with pytest.raises(ValueError, match="option chain instrument mismatch"):
        assemble_vision_option_confirmation_context(request(chain=wrong_symbol, analytics_snapshot=analytics(wrong_symbol)))

    wrong_expiry = option_chain(expiry=date(2026, 8, 6))
    with pytest.raises(ValueError, match="expiry mismatch"):
        assemble_vision_option_confirmation_context(request(chain=wrong_expiry, analytics_snapshot=analytics(wrong_expiry)))

    stale_timestamp = NOW - timedelta(minutes=6)
    stale_chain = option_chain(timestamp=stale_timestamp)
    with pytest.raises(ValueError, match="stale option chain"):
        assemble_vision_option_confirmation_context(request(chain=stale_chain, analytics_snapshot=analytics(stale_chain)))

    future_chain = option_chain(timestamp=NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="cannot be after request timestamp"):
        assemble_vision_option_confirmation_context(request(chain=future_chain, analytics_snapshot=analytics(future_chain)))


def test_option_confirmation_context_rejects_duplicate_factors_and_is_immutable():
    with pytest.raises(ValueError, match="duplicated"):
        VisionOptionConfirmationContext(
            confirmation_state=VisionOptionConfirmation.PARTIAL,
            supporting_factors=("PCR rising",),
            contradicting_factors=("pcr rising",),
            neutral_factors=(),
            quality=VisionLevelQuality.PARTIAL,
            timestamp=NOW,
        )

    result = assemble_vision_option_confirmation_context(request())
    with pytest.raises(FrozenInstanceError):
        result.confirmation_state = VisionOptionConfirmation.NEUTRAL


def test_vm08_boundary_creates_no_runtime_strategy_ai_or_risk_code():
    package = Path("engines/vision_method")
    source = (package / "option_confirmation.py").read_text(encoding="utf-8").lower()

    assert (package / "option_confirmation.py").exists()
    assert not (package / "engine.py").exists()
    assert "strategydecision" not in source
    assert "aireasoning" not in source
    assert "riskmanagement" not in source
    assert "broker" not in source
    assert "eventbus" not in source
