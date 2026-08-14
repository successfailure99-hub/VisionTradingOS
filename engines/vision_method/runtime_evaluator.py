"""Stateless Vision Method assembly for runtime-owned decision evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging

from core.enums.timeframe import TimeFrame
from core.models.daily_ohlc import DailyOHLC
from engines.option_chain.models import OptionChainSnapshot
from engines.option_chain_analytics.models import OptionChainAnalyticsSnapshot
from engines.vision_method import (
    VisionBOS,
    VisionBreakerBlock,
    VisionBreakerBlockState,
    VisionBreakDirection,
    VisionBreakStrength,
    VisionCHoCH,
    VisionContextAssemblyFailure,
    VisionContextAssemblyStatus,
    VisionLevelContextRequest,
    VisionLevelQuality,
    VisionLiquidityContext,
    VisionLiquidityPool,
    VisionLiquiditySweep,
    VisionLiquidityRequest,
    VisionMethodCalculationRequest,
    VisionMethodSnapshot,
    VisionMethodValidationReport,
    VisionMitigationState,
    VisionMSS,
    VisionOpeningRangeContext,
    VisionOpeningRangeRequest,
    VisionOpeningRangeState,
    VisionOptionConfirmation,
    VisionOptionConfirmationContext,
    VisionOptionConfirmationRequest,
    VisionPivotConfluenceRequest,
    VisionPriceActionTriggerRequest,
    VisionRangeLocation,
    VisionReversalState,
    VisionSetupQuality,
    VisionSetupQualificationContext,
    VisionSetupQualificationRequest,
    VisionSetupType,
    VisionStructureContext,
    VisionStructureEventContext,
    VisionStructureEventPhase,
    VisionStructureEventRequest,
    VisionStructurePattern,
    VisionStructureRequest,
    VisionStructureTrend,
    VisionSweepDirection,
    assemble_vision_level_context,
    assemble_vision_liquidity_context,
    assemble_vision_opening_range_context,
    assemble_vision_option_confirmation_context,
    assemble_vision_setup_qualification_context,
    assemble_vision_structure_context,
    assemble_vision_structure_event_context,
    build_pivot_confluence_context,
    build_price_action_trigger_context,
    calculate_vision_method_snapshot,
    failed_price_action_trigger_stage_result,
    insufficient_price_action_trigger_stage_result,
    price_action_trigger_stage_result_from_context,
    validate_vision_method,
)


LOGGER = logging.getLogger(__name__)
LIVE_MARKET_DATA_STALE_SECONDS = 120.0


@dataclass(frozen=True, slots=True)
class VisionMethodRuntimeAssembly:
    runtime_snapshot: object
    timeframe: TimeFrame
    timestamp: datetime
    trading_date: object
    level: object | None = None
    opening_range: object | None = None
    structure: object | None = None
    liquidity: object | None = None
    structure_events: object | None = None
    setup: object | None = None
    option_confirmation: object | None = None
    pivot_flight_plan: object | None = None
    pivot_opening_assessment: object | None = None
    pivot_confluence_context: object | None = None
    price_action_trigger_context: object | None = None
    price_action_trigger_stage_result: object | None = None
    snapshot: VisionMethodSnapshot | None = None
    report: VisionMethodValidationReport | None = None
    failures: tuple[VisionContextAssemblyFailure, ...] = ()


def assemble_vision_method_runtime(
    runtime,
    *,
    runtime_snapshot=None,
    timestamp: datetime | None = None,
    option_analytics_provider=None,
    observed_at: datetime | None = None,
    logger: logging.Logger | None = None,
    level_assembler=assemble_vision_level_context,
    opening_range_assembler=assemble_vision_opening_range_context,
    structure_assembler=assemble_vision_structure_context,
    liquidity_assembler=assemble_vision_liquidity_context,
    structure_event_assembler=assemble_vision_structure_event_context,
    setup_assembler=assemble_vision_setup_qualification_context,
    option_confirmation_assembler=assemble_vision_option_confirmation_context,
    calculator=calculate_vision_method_snapshot,
    validator=validate_vision_method,
) -> VisionMethodRuntimeAssembly:
    """Assemble and validate Vision Method from canonical runtime inputs.

    This evaluator is intentionally stateless. It does not publish events, mutate
    paper trading, write journals, or touch UI. Runtime owners decide when to call
    it and what to do with the immutable result.
    """

    log = logger or LOGGER
    runtime_snapshot = runtime.snapshot() if runtime_snapshot is None else runtime_snapshot
    timeframe = vision_decision_timeframe(runtime, runtime_snapshot)
    timestamp = timestamp or _runtime_timestamp(runtime_snapshot)
    trading_date = _market_session_date(timestamp)
    observed_at = observed_at or _default_clock()
    history = tuple(
        candle
        for candle in runtime.get_candle_history(timeframe)
        if candle.start_time.date() == trading_date and candle.end_time <= timestamp
    )
    if history:
        timestamp = _align_timestamp_to_closed_candle_timezone(timestamp, history)
        trading_date = _market_session_date(timestamp)
        history = tuple(
            candle
            for candle in history
            if candle.start_time.date() == trading_date and candle.end_time <= timestamp
        )

    failures: list[VisionContextAssemblyFailure] = []
    pivot_flight_plan = None
    pivot_opening_assessment = None
    pivot_confluence_context = None
    price_action_trigger_context = None
    price_action_trigger_stage_result = None
    runtime_owns_vision_extensions = hasattr(runtime, "_current_pivot_flight_plan")
    if not runtime_owns_vision_extensions:
        pivot_flight_plan = getattr(runtime_snapshot, "pivot_flight_plan", None)
        pivot_opening_assessment = getattr(runtime_snapshot, "pivot_opening_assessment", None)
        pivot_confluence_context = getattr(runtime_snapshot, "pivot_confluence_context", None)
        price_action_trigger_context = getattr(runtime_snapshot, "price_action_trigger_context", None)
        price_action_trigger_stage_result = getattr(runtime_snapshot, "price_action_trigger_stage_result", None)

    if not history:
        market_age = _market_age_seconds(runtime_snapshot, timestamp, observed_at=observed_at)
        if _is_live_market_data_stale(runtime_snapshot, timestamp, observed_at):
            failures.append(_missing_failure("Market Data", _stale_market_data_reason(timestamp, market_age)))
        else:
            failures.append(_missing_failure("Candle Engine", "Closed candle history is unavailable."))
        return VisionMethodRuntimeAssembly(
            runtime_snapshot=runtime_snapshot,
            timeframe=timeframe,
            timestamp=timestamp,
            trading_date=trading_date,
            pivot_flight_plan=pivot_flight_plan,
            pivot_opening_assessment=pivot_opening_assessment,
            pivot_confluence_context=pivot_confluence_context,
            price_action_trigger_context=price_action_trigger_context,
            price_action_trigger_stage_result=price_action_trigger_stage_result,
            failures=tuple(failures),
        )

    latest_price = _latest_price(runtime_snapshot, history)
    previous_price = history[-2].close if len(history) >= 2 else None
    opening_price = history[0].open
    cpr = runtime_snapshot.cpr
    camarilla = runtime_snapshot.camarilla
    level = None
    if cpr is None:
        failures.append(_missing_failure("CPR", "WAITING_DAILY_CONTEXT: Daily CPR levels are unavailable."))
    elif cpr.trading_date != trading_date:
        failures.append(_missing_failure("CPR", _waiting_daily_context_reason("CPR", cpr.trading_date, trading_date)))
    if camarilla is None:
        failures.append(_missing_failure("Camarilla", "WAITING_DAILY_CONTEXT: Daily Camarilla levels are unavailable."))
    elif camarilla.trading_date != trading_date:
        failures.append(_missing_failure("Camarilla", _waiting_daily_context_reason("Camarilla", camarilla.trading_date, trading_date)))
    if cpr is not None and camarilla is not None and cpr.trading_date == trading_date and camarilla.trading_date == trading_date:
        previous_day = _previous_day_from_cpr(cpr)
        adr, vwap = _session_aligned_optional_contexts(runtime_snapshot, trading_date, failures)
        try:
            level = level_assembler(
                VisionLevelContextRequest(
                    instrument=runtime_snapshot.symbol,
                    timeframe=timeframe,
                    trading_date=trading_date,
                    timestamp=timestamp,
                    latest_price=latest_price,
                    opening_price=opening_price,
                    previous_day=previous_day,
                    cpr=cpr,
                    camarilla=camarilla,
                    adr=adr,
                    vwap=vwap,
                    previous_price=previous_price,
                ),
                instrument=runtime_snapshot.symbol,
                timeframe=timeframe,
                max_snapshot_age=timedelta(days=1),
            )
            log.debug("[VisionMethodRuntime] LEVEL_CONTEXT available")
        except Exception as exc:
            failures.append(_failure("Level Context", exc))
            log.debug("[VisionMethodRuntime] LEVEL_CONTEXT failed reason=%r", _safe_error(exc))

    opening_range = None
    try:
        opening_range = opening_range_assembler(
            VisionOpeningRangeRequest(
                instrument=runtime_snapshot.symbol,
                timeframe=timeframe,
                trading_date=trading_date,
                timestamp=timestamp,
                candles=history,
            ),
            instrument=runtime_snapshot.symbol,
            timeframe=timeframe,
        )
        log.debug("[VisionMethodRuntime] OPENING_RANGE available")
    except Exception as exc:
        failures.append(_failure("Opening Range", exc))
        opening_range = _fallback_opening_range(timestamp, history, timeframe)
        log.debug("[VisionMethodRuntime] OPENING_RANGE failed reason=%r", _safe_error(exc))

    structure = None
    try:
        structure = structure_assembler(
            VisionStructureRequest(
                instrument=runtime_snapshot.symbol,
                timeframe=timeframe,
                trading_date=trading_date,
                timestamp=timestamp,
                candles=history,
            ),
            instrument=runtime_snapshot.symbol,
            timeframe=timeframe,
        )
        log.debug("[VisionMethodRuntime] STRUCTURE available")
    except Exception as exc:
        failures.append(_failure("Structure", exc))
        structure = _fallback_structure()
        log.debug("[VisionMethodRuntime] STRUCTURE failed reason=%r", _safe_error(exc))

    liquidity = None
    try:
        liquidity = liquidity_assembler(
            VisionLiquidityRequest(
                instrument=runtime_snapshot.symbol,
                timeframe=timeframe,
                trading_date=trading_date,
                timestamp=timestamp,
                candles=history,
            ),
            instrument=runtime_snapshot.symbol,
            timeframe=timeframe,
        )
        log.debug("[VisionMethodRuntime] LIQUIDITY available")
    except Exception as exc:
        failures.append(_failure("Liquidity", exc))
        liquidity = _fallback_liquidity()
        log.debug("[VisionMethodRuntime] LIQUIDITY failed reason=%r", _safe_error(exc))

    structure_events = None
    if structure is None or structure.quality is VisionLevelQuality.INSUFFICIENT:
        failures.append(_not_evaluated_failure("Structure Events", "Structure context is unavailable."))
    else:
        try:
            structure_events = structure_event_assembler(
                VisionStructureEventRequest(
                    instrument=runtime_snapshot.symbol,
                    timeframe=timeframe,
                    trading_date=trading_date,
                    timestamp=timestamp,
                    candles=history,
                    structure_context=structure,
                    liquidity_context=liquidity if liquidity is not None and liquidity.quality is not VisionLevelQuality.INSUFFICIENT else None,
                ),
                instrument=runtime_snapshot.symbol,
                timeframe=timeframe,
            )
            log.debug("[VisionMethodRuntime] STRUCTURE_EVENTS available")
        except Exception as exc:
            failures.append(_failure("Structure Events", exc))
            structure_events = _fallback_structure_events()
            log.debug("[VisionMethodRuntime] STRUCTURE_EVENTS failed reason=%r", _safe_error(exc))

    setup = None
    if level is None:
        failures.append(_not_evaluated_failure("Setup Qualification", "Level context is unavailable."))
    elif opening_range is None or opening_range.quality is VisionLevelQuality.INSUFFICIENT:
        failures.append(_not_evaluated_failure("Setup Qualification", "Opening range context is unavailable."))
    elif structure is None or structure.quality is VisionLevelQuality.INSUFFICIENT:
        failures.append(_not_evaluated_failure("Setup Qualification", "Structure context is unavailable."))
    elif structure_events is None or structure_events.quality is VisionLevelQuality.INSUFFICIENT:
        failures.append(_not_evaluated_failure("Setup Qualification", "Structure events context is unavailable."))
    else:
        try:
            setup = setup_assembler(
                VisionSetupQualificationRequest(
                    instrument=runtime_snapshot.symbol,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    level_context=level,
                    opening_range_context=opening_range,
                    structure_context=structure,
                    liquidity_context=liquidity,
                    structure_event_context=structure_events,
                ),
                instrument=runtime_snapshot.symbol,
                timeframe=timeframe,
            )
            log.debug("[VisionMethodRuntime] SETUP_QUALIFICATION available")
        except Exception as exc:
            failures.append(_failure("Setup Qualification", exc))
            setup = _fallback_setup(failures)
            log.debug("[VisionMethodRuntime] SETUP_QUALIFICATION failed reason=%r", _safe_error(exc))

    option_confirmation = None
    if setup is None:
        failures.append(_not_evaluated_failure("Option Confirmation", "Setup qualification is unavailable."))
    elif cpr is not None:
        option_chain, option_analytics = _option_inputs(runtime_snapshot, option_analytics_provider)
        option_expiry = option_chain.expiry_date if option_chain is not None else cpr.trading_date
        try:
            option_confirmation = option_confirmation_assembler(
                VisionOptionConfirmationRequest(
                    instrument=runtime_snapshot.symbol,
                    expiry=option_expiry,
                    timestamp=timestamp,
                    setup_qualification=setup,
                    option_chain=option_chain,
                    analytics=option_analytics,
                ),
                instrument=runtime_snapshot.symbol,
                expiry=option_expiry,
                max_snapshot_age=timedelta(days=1),
            )
            log.debug("[VisionMethodRuntime] OPTION_CONFIRMATION available")
        except Exception as exc:
            failures.append(_failure("Option Confirmation", exc))
            option_confirmation = _fallback_option_confirmation(timestamp, failures)
            log.debug("[VisionMethodRuntime] OPTION_CONFIRMATION failed reason=%r", _safe_error(exc))

    if runtime_owns_vision_extensions:
        pivot_flight_plan = _current_pivot_flight_plan(runtime, timestamp, runtime_snapshot)
        pivot_opening_assessment = _current_pivot_opening_assessment(runtime, timestamp, runtime_snapshot, pivot_flight_plan)
    if runtime_owns_vision_extensions and level is not None:
        try:
            pivot_confluence_context = build_pivot_confluence_context(
                VisionPivotConfluenceRequest(
                    instrument=runtime_snapshot.symbol,
                    timeframe=timeframe,
                    trading_date=trading_date,
                    timestamp=timestamp,
                    current_price=history[-1].close,
                    level_context=level,
                    opening_range_context=opening_range,
                    structure_context=structure,
                    liquidity_context=liquidity,
                    pivot_flight_plan=pivot_flight_plan,
                    pivot_opening_assessment=pivot_opening_assessment,
                )
            )
            log.debug("[VisionMethodRuntime] PIVOT_CONFLUENCE available")
        except Exception as exc:
            failures.append(_failure("Pivot Confluence", exc))
            log.debug("[VisionMethodRuntime] PIVOT_CONFLUENCE failed reason=%r", _safe_error(exc))

    trigger_timestamp = _trigger_stage_timestamp(timestamp)
    trigger_generation = _trigger_snapshot_generation(runtime_snapshot.symbol, timeframe, trigger_timestamp)
    source_candle = history[-1] if history else None
    source_reference = _trigger_candle_reference(source_candle)
    if runtime_owns_vision_extensions and level is not None and trigger_timestamp is not None and pivot_confluence_context is None:
        price_action_trigger_stage_result = insufficient_price_action_trigger_stage_result(
            reason="Pivot confluence context unavailable.",
            decision_timestamp=trigger_timestamp,
            source_candle_reference=source_reference,
            snapshot_generation=trigger_generation,
        )
    elif runtime_owns_vision_extensions and trigger_timestamp is not None and pivot_confluence_context is not None:
        try:
            price_action_trigger_context = build_price_action_trigger_context(
                VisionPriceActionTriggerRequest(
                    instrument=runtime_snapshot.symbol,
                    timeframe=timeframe,
                    trading_date=trading_date,
                    timestamp=timestamp,
                    candles=history,
                    pivot_confluence_context=pivot_confluence_context,
                    opening_range_context=opening_range,
                    structure_context=structure,
                    liquidity_context=liquidity,
                    structure_event_context=structure_events,
                    pivot_opening_assessment=pivot_opening_assessment,
                    previous_context=getattr(runtime, "_price_action_trigger_context", None),
                )
            )
            price_action_trigger_stage_result = price_action_trigger_stage_result_from_context(
                price_action_trigger_context,
                snapshot_generation=trigger_generation,
            )
            log.debug("[VisionMethodRuntime] PRICE_ACTION_TRIGGER available")
        except Exception as exc:
            price_action_trigger_stage_result = failed_price_action_trigger_stage_result(
                exc=exc,
                decision_timestamp=trigger_timestamp,
                source_candle_reference=source_reference,
                trigger_zone_reference=_trigger_zone_reference(pivot_confluence_context),
                snapshot_generation=trigger_generation,
            )
            price_action_trigger_context = None
            log.debug("[VisionMethodRuntime] PRICE_ACTION_TRIGGER failed reason=%r", _safe_error(exc))

    if (
        price_action_trigger_stage_result is not None
        and getattr(getattr(price_action_trigger_stage_result, "status", None), "value", None) == "trigger_assembly_failed"
    ):
        failures.append(
            VisionContextAssemblyFailure(
                stage="Price-Action Trigger",
                status=VisionContextAssemblyStatus.FAILED,
                failure_reason=getattr(price_action_trigger_stage_result, "failure_type", None) or "TriggerAssemblyFailed",
                validation_message=getattr(price_action_trigger_stage_result, "failure_reason", None)
                or "Price-action trigger assembly failed.",
            )
        )

    snapshot = None
    report = None
    if (
        level is not None
        and opening_range is not None
        and structure is not None
        and liquidity is not None
        and structure_events is not None
        and setup is not None
        and option_confirmation is not None
    ):
        snapshot = calculator(
            VisionMethodCalculationRequest(
                instrument=runtime_snapshot.symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                level_context=level,
                opening_range_context=opening_range,
                structure_context=structure,
                liquidity_context=liquidity,
                structure_event_context=structure_events,
                setup_qualification_context=setup,
                option_confirmation_context=option_confirmation,
                current_price=history[-1].close,
                pivot_flight_plan=pivot_flight_plan,
                pivot_opening_assessment=pivot_opening_assessment,
                pivot_confluence_context=pivot_confluence_context,
                price_action_trigger_context=price_action_trigger_context,
                price_action_trigger_stage_result=price_action_trigger_stage_result,
                assembly_failures=tuple(failures),
            ),
            instrument=runtime_snapshot.symbol,
            timeframe=timeframe,
        )
        log.debug("[VisionMethodRuntime] Snapshot generated")
        report = validator(snapshot)
        log.debug("[VisionMethodRuntime] Validation complete")

    return VisionMethodRuntimeAssembly(
        runtime_snapshot=runtime_snapshot,
        timeframe=timeframe,
        timestamp=timestamp,
        trading_date=trading_date,
        level=level,
        opening_range=opening_range,
        structure=structure,
        liquidity=liquidity,
        structure_events=structure_events,
        setup=setup,
        option_confirmation=option_confirmation,
        pivot_flight_plan=pivot_flight_plan,
        pivot_opening_assessment=pivot_opening_assessment,
        pivot_confluence_context=pivot_confluence_context,
        price_action_trigger_context=price_action_trigger_context,
        price_action_trigger_stage_result=price_action_trigger_stage_result,
        snapshot=snapshot,
        report=report,
        failures=tuple(failures),
    )


def _current_pivot_flight_plan(runtime, timestamp, runtime_snapshot):
    session = getattr(runtime_snapshot, "runtime_session", None)
    builder = getattr(runtime, "_current_pivot_flight_plan", None)
    if session is None or builder is None:
        return None
    try:
        return builder(timestamp, session)
    except Exception:
        return None


def _current_pivot_opening_assessment(runtime, timestamp, runtime_snapshot, pivot_flight_plan):
    session = getattr(runtime_snapshot, "runtime_session", None)
    builder = getattr(runtime, "_current_pivot_opening_assessment", None)
    if session is None or builder is None or pivot_flight_plan is None:
        return None
    try:
        return builder(timestamp, session, pivot_flight_plan)
    except Exception:
        return None


def _trigger_stage_timestamp(timestamp: datetime | None) -> datetime | None:
    if timestamp is None:
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return timestamp
    return timestamp.astimezone(timestamp.tzinfo)


def _trigger_snapshot_generation(instrument, timeframe: TimeFrame, timestamp: datetime | None) -> str:
    stamp = timestamp.isoformat() if timestamp is not None else "unknown"
    return f"{instrument.value}:{timeframe.value}:{stamp}"


def _trigger_candle_reference(candle) -> str:
    if candle is None:
        return "-"
    return f"{candle.timeframe}:{candle.start_time.isoformat()}:{candle.end_time.isoformat()}"


def _trigger_zone_reference(context) -> str:
    if context is None:
        return "-"
    zones = getattr(context, "hot_zones", ()) or ()
    if not zones:
        return "-"
    return getattr(zones[0], "zone_reference", None) or getattr(zones[0], "label", "-")


def vision_decision_timeframe(runtime, runtime_snapshot) -> TimeFrame:
    configured = getattr(runtime, "vision_decision_timeframe", None)
    if isinstance(configured, TimeFrame):
        return configured
    if configured is not None:
        return TimeFrame.from_value(str(configured))
    snapshot_value = getattr(runtime_snapshot, "vision_decision_timeframe", None)
    if snapshot_value is not None:
        return TimeFrame.from_value(str(snapshot_value))
    return TimeFrame.FIVE_MINUTES


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _runtime_timestamp(runtime_snapshot) -> datetime:
    runtime_session = getattr(runtime_snapshot, "runtime_session", None)
    timestamp = (
        getattr(runtime_session, "market_timestamp", None)
        or getattr(runtime_snapshot, "snapshot_created_at", None)
        or runtime_snapshot.latest_closed_candle_at
        or runtime_snapshot.latest_tick_at
        or runtime_snapshot.updated_at
    )
    if timestamp is None:
        raise RuntimeError("No market timestamp is available.")
    return timestamp


def _market_session_date(timestamp) -> object:
    return timestamp.date()


def _align_timestamp_to_closed_candle_timezone(timestamp, history) -> object:
    latest = history[-1] if history else None
    candle_time = getattr(latest, "end_time", None)
    candle_zone = getattr(candle_time, "tzinfo", None)
    if candle_zone is None or not hasattr(timestamp, "astimezone"):
        return timestamp
    if getattr(timestamp, "tzinfo", None) is None or timestamp.utcoffset() is None:
        return timestamp
    return timestamp.astimezone(candle_zone)


def _latest_price(runtime_snapshot, history) -> float:
    if runtime_snapshot.latest_tick is not None:
        return runtime_snapshot.latest_tick.last_price
    return history[-1].close


def _previous_day_from_cpr(cpr) -> DailyOHLC:
    previous_date = cpr.trading_date - timedelta(days=1)
    return DailyOHLC(
        trading_date=previous_date,
        open=cpr.previous_close,
        high=cpr.previous_high,
        low=cpr.previous_low,
        close=cpr.previous_close,
    )


def _option_inputs(
    runtime_snapshot,
    option_analytics_provider,
) -> tuple[OptionChainSnapshot | None, OptionChainAnalyticsSnapshot | None]:
    option_chain = getattr(runtime_snapshot, "option_chain_snapshot", None)
    analytics = getattr(runtime_snapshot, "option_chain_analytics", None)
    if option_chain is None and analytics is None and option_analytics_provider is not None:
        option_chain, analytics = option_analytics_provider(runtime_snapshot.symbol)
    if option_chain is not None and not isinstance(option_chain, OptionChainSnapshot):
        raise TypeError("option provider must return OptionChainSnapshot or None.")
    if analytics is not None and not isinstance(analytics, OptionChainAnalyticsSnapshot):
        raise TypeError("option provider must return OptionChainAnalyticsSnapshot or None.")
    return option_chain, analytics


def _missing_failure(stage: str, message: str) -> VisionContextAssemblyFailure:
    return VisionContextAssemblyFailure(
        stage=stage,
        status=VisionContextAssemblyStatus.MISSING,
        failure_reason=message,
        validation_message=message,
    )


def _not_evaluated_failure(stage: str, message: str) -> VisionContextAssemblyFailure:
    return VisionContextAssemblyFailure(
        stage=stage,
        status=VisionContextAssemblyStatus.NOT_EVALUATED,
        failure_reason=message,
        validation_message=message,
    )


def _failure(stage: str, exc: Exception) -> VisionContextAssemblyFailure:
    message = _operational_error_message(stage, exc)
    return VisionContextAssemblyFailure(
        stage=stage,
        status=VisionContextAssemblyStatus.FAILED,
        failure_reason=exc.__class__.__name__,
        validation_message=message,
    )


def _waiting_daily_context_reason(name: str, context_date, trading_date) -> str:
    return f"WAITING_DAILY_CONTEXT: {name} levels are not refreshed for {trading_date}."


def _session_aligned_optional_contexts(
    runtime_snapshot,
    trading_date,
    failures: list[VisionContextAssemblyFailure],
):
    adr = runtime_snapshot.adr
    if adr is not None and adr.trading_date != trading_date:
        failures.append(_missing_failure("ADR", _waiting_daily_context_reason("ADR", adr.trading_date, trading_date)))
        adr = None
    vwap = runtime_snapshot.vwap
    if vwap is not None and vwap.trading_date != trading_date:
        failures.append(_missing_failure("VWAP", _waiting_daily_context_reason("VWAP", vwap.trading_date, trading_date)))
        vwap = None
    return adr, vwap


def _market_age_seconds(runtime_snapshot, market_timestamp, *, observed_at=None) -> float | None:
    updated_at = observed_at or getattr(runtime_snapshot, "updated_at", None) or getattr(runtime_snapshot, "snapshot_created_at", None)
    if updated_at is None or market_timestamp is None:
        return None
    if not hasattr(updated_at, "utcoffset") or not hasattr(market_timestamp, "utcoffset"):
        return None
    if updated_at.utcoffset() is None or market_timestamp.utcoffset() is None:
        return None
    return max(0.0, (updated_at - market_timestamp).total_seconds())


def _is_live_market_data_stale(runtime_snapshot, market_timestamp, observed_at) -> bool:
    runtime_session = getattr(runtime_snapshot, "runtime_session", None)
    if getattr(runtime_session, "status", None) != "READY":
        return False
    age = _market_age_seconds(runtime_snapshot, market_timestamp, observed_at=observed_at)
    return age is not None and age > LIVE_MARKET_DATA_STALE_SECONDS


def _stale_market_data_reason(market_timestamp, market_age_seconds: float | None) -> str:
    if market_age_seconds is None:
        return "Live market data is stale."
    return (
        "Live market data is stale. "
        f"Last market timestamp is {market_timestamp.isoformat()}; age is {market_age_seconds:.0f}s."
    )


def _fallback_opening_range(timestamp, history, timeframe: TimeFrame) -> VisionOpeningRangeContext:
    session_start = timestamp.replace(hour=9, minute=15, second=0, microsecond=0)
    session_end = session_start + timedelta(minutes=15)
    opening_candles = _opening_window_candles(timestamp, history, timeframe, session_start, session_end)
    expected_starts = _expected_opening_starts(session_start, session_end, timeframe)
    missing_starts = _missing_opening_starts(opening_candles, expected_starts)
    high = max((candle.high for candle in opening_candles), default=1.0)
    low = min((candle.low for candle in opening_candles), default=high)
    if low <= 0:
        low = high
    return VisionOpeningRangeContext(
        opening_start_time=session_start,
        opening_end_time=session_end,
        opening_high=high,
        opening_low=low,
        opening_width=high - low,
        range_complete=False,
        current_location=VisionRangeLocation.INSIDE_RANGE,
        break_direction=VisionBreakDirection.NONE,
        retest_state=VisionOpeningRangeState.WAITING,
        false_break=False,
        elapsed_minutes=0,
        quality=VisionLevelQuality.INSUFFICIENT,
        expected_candle_count=len(expected_starts),
        actual_candle_count=len(opening_candles),
        missing_candle_timestamps=missing_starts,
    )


def _opening_window_candles(
    timestamp,
    history,
    timeframe: TimeFrame,
    session_start,
    session_end,
):
    return tuple(
        candle
        for candle in history
        if getattr(candle, "timeframe", None) == timeframe.value
        and getattr(candle, "start_time", timestamp).date() == timestamp.date()
        and getattr(candle, "end_time", timestamp).date() == timestamp.date()
        and candle.start_time >= session_start
        and candle.end_time <= session_end
        and candle.end_time <= timestamp
    )


def _expected_opening_starts(session_start, session_end, timeframe: TimeFrame) -> tuple[datetime, ...]:
    duration = timeframe.duration
    starts = []
    cursor = session_start
    while cursor < session_end:
        starts.append(cursor)
        cursor = cursor + duration
    return tuple(starts)


def _missing_opening_starts(opening_candles, expected_starts) -> tuple[datetime, ...]:
    observed = {candle.start_time for candle in opening_candles}
    return tuple(timestamp for timestamp in expected_starts if timestamp not in observed)


def _fallback_structure() -> VisionStructureContext:
    return VisionStructureContext(
        current_swing_high=None,
        current_swing_low=None,
        previous_swing_high=None,
        previous_swing_low=None,
        trend=VisionStructureTrend.UNKNOWN,
        structure_state=VisionStructurePattern.UNKNOWN,
        last_confirmed_swing=None,
        quality=VisionLevelQuality.INSUFFICIENT,
    )


def _fallback_liquidity() -> VisionLiquidityContext:
    return VisionLiquidityContext(
        equal_highs=(),
        equal_lows=(),
        liquidity_pool=VisionLiquidityPool.NONE,
        liquidity_sweep=VisionLiquiditySweep.NONE,
        sweep_direction=VisionSweepDirection.NONE,
        fair_value_gap=None,
        order_block=None,
        breaker_block=VisionBreakerBlock(VisionBreakerBlockState.NOT_EVALUATED),
        mitigation=VisionMitigationState.NOT_EVALUATED,
        quality=VisionLevelQuality.INSUFFICIENT,
    )


def _fallback_structure_events() -> VisionStructureEventContext:
    return VisionStructureEventContext(
        bos=VisionBOS.NONE,
        choch=VisionCHoCH.NONE,
        mss=VisionMSS.NONE,
        continuation=VisionStructureEventPhase.NONE,
        reversal=VisionReversalState.NONE,
        break_strength=VisionBreakStrength.NONE,
        quality=VisionLevelQuality.INSUFFICIENT,
    )


def _fallback_setup(failures: list[VisionContextAssemblyFailure]) -> VisionSetupQualificationContext:
    reasons = tuple(f"{failure.stage}: {failure.validation_message}" for failure in failures)
    return VisionSetupQualificationContext(
        setup_type=VisionSetupType.NO_QUALITY_SETUP,
        setup_quality=VisionSetupQuality.INVALID,
        blocking_reasons=reasons or ("Context assembly incomplete",),
        supporting_reasons=(),
        eligible_for_option_confirmation=False,
    )


def _fallback_option_confirmation(timestamp, failures: list[VisionContextAssemblyFailure]) -> VisionOptionConfirmationContext:
    option_failure = next((failure for failure in failures if failure.stage == "Option Confirmation"), None)
    reason = option_failure.validation_message if option_failure is not None else "Option confirmation unavailable"
    state = VisionOptionConfirmation.NEUTRAL if _is_nonblocking_option_alignment(reason) else VisionOptionConfirmation.UNAVAILABLE
    quality = VisionLevelQuality.PARTIAL if state is VisionOptionConfirmation.NEUTRAL else VisionLevelQuality.INSUFFICIENT
    return VisionOptionConfirmationContext(
        confirmation_state=state,
        supporting_factors=(),
        contradicting_factors=(),
        neutral_factors=(reason,),
        quality=quality,
        timestamp=timestamp,
    )


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip()
    return f"{exc.__class__.__name__}: {text}" if text else exc.__class__.__name__


def _operational_error_message(stage: str, exc: Exception) -> str:
    text = str(exc).strip()
    lowered = text.casefold()
    if "timezone mismatch" in lowered or "timezone-aware" in lowered or "candle timezone mismatch" in lowered:
        if stage == "Option Confirmation":
            return "Option chain timestamp is not aligned with the canonical runtime timestamp; ignored for setup evaluation."
        return f"{stage} waiting for timezone-aligned runtime data."
    if "incomplete opening data" in lowered:
        return f"Opening Range not complete. {text}"
    if "missing candles" in lowered or "insufficient closed candles" in lowered:
        return "Waiting for required closed candle history."
    if "trading date mismatch" in lowered:
        return f"{stage} waiting for active-session market data."
    if "session" in lowered and "mismatch" in lowered:
        return f"{stage} waiting for active trading session alignment."
    return text if text else exc.__class__.__name__


def _is_nonblocking_option_alignment(reason: str) -> bool:
    lowered = reason.casefold()
    return "option chain timestamp" in lowered and "ignored for setup evaluation" in lowered
