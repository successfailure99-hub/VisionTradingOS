"""
Live Vision Method inspector integration.

This module is presentation glue for VM-11.1. It reads the existing immutable
runtime state, assembles the already-certified Vision Method contexts, validates
the resulting snapshot, and renders the pair in the read-only inspector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from application.enums import RuntimeInstrument
from application.lifecycle_manager import ApplicationLifecycleManager
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
    VisionCandidateState,
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
    VisionOpeningRangeRequest,
    VisionOpeningRangeState,
    VisionOpeningRangeContext,
    VisionOptionConfirmationRequest,
    VisionOptionConfirmation,
    VisionOptionConfirmationContext,
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
    calculate_vision_method_snapshot,
    validate_vision_method,
)

from .vision_method_inspector import VisionMethodInspector


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VisionMethodInspectorLiveResult:
    snapshot: VisionMethodSnapshot | None
    validation_report: VisionMethodValidationReport | None
    rendered: bool
    ready: bool
    reason: str | None = None
    failures: tuple[VisionContextAssemblyFailure, ...] = ()


class VisionMethodLiveInspectorBridge:
    """
    Build and render Vision Method inspector state from existing runtime data.

    The bridge owns no market state and publishes no events. It is deliberately
    dashboard-local so VM-11.1 does not introduce a new runtime pipeline.
    """

    def __init__(
        self,
        lifecycle: ApplicationLifecycleManager,
        inspector: VisionMethodInspector,
        *,
        option_analytics_provider=None,
        logger: logging.Logger | None = None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be ApplicationLifecycleManager.")
        if not isinstance(inspector, VisionMethodInspector):
            raise TypeError("inspector must be VisionMethodInspector.")
        self._lifecycle = lifecycle
        self._inspector = inspector
        self._option_analytics_provider = option_analytics_provider
        self._logger = logger or LOGGER
        self._last_snapshot: VisionMethodSnapshot | None = None
        self._last_report: VisionMethodValidationReport | None = None

    @property
    def last_snapshot(self) -> VisionMethodSnapshot | None:
        return self._last_snapshot

    @property
    def last_report(self) -> VisionMethodValidationReport | None:
        return self._last_report

    def refresh(self) -> VisionMethodInspectorLiveResult:
        try:
            snapshot, failures = self._build_snapshot()
            self._logger.debug("[VisionMethod] Snapshot generated")
            report = validate_vision_method(snapshot)
            self._logger.debug("[VisionMethod] Validation complete")
        except _VisionMethodNotReady as exc:
            self._last_snapshot = None
            self._last_report = None
            if exc.failure is None:
                self._inspector.render(None, None)
                failures = ()
            else:
                self._inspector.render_failure(
                    exc.failure,
                    instrument=exc.instrument,
                    timeframe=exc.timeframe,
                    timestamp=exc.timestamp,
                )
                failures = (exc.failure,)
            self._logger.debug("[VisionMethod] Inspector updated")
            return VisionMethodInspectorLiveResult(None, None, True, False, str(exc), failures)
        except Exception as exc:
            self._last_snapshot = None
            self._last_report = None
            self._inspector.render(None, None)
            self._logger.debug("[VisionMethod] Inspector updated")
            return VisionMethodInspectorLiveResult(None, None, True, False, _safe_error(exc))

        self._last_snapshot = snapshot
        self._last_report = report
        self._inspector.render(snapshot, report)
        self._logger.debug("[VisionMethod] Inspector updated")
        return VisionMethodInspectorLiveResult(snapshot, report, True, not failures, failures=failures)

    def _build_snapshot(self) -> tuple[VisionMethodSnapshot, tuple[VisionContextAssemblyFailure, ...]]:
        runtime = self._select_runtime()
        runtime_snapshot = runtime.snapshot()
        timeframe = TimeFrame.from_value(runtime_snapshot.timeframe)
        timestamp = _runtime_timestamp(runtime_snapshot)
        trading_date = timestamp.date()
        cpr = runtime_snapshot.cpr
        camarilla = runtime_snapshot.camarilla
        if cpr is None:
            raise self._not_ready("Level Context", "CPR is unavailable.", runtime_snapshot, timestamp)
        if camarilla is None:
            raise self._not_ready("Level Context", "Camarilla is unavailable.", runtime_snapshot, timestamp)
        history = tuple(
            candle
            for candle in runtime.get_candle_history(timeframe)
            if candle.start_time.date() == trading_date and candle.end_time <= timestamp
        )
        if not history:
            raise self._not_ready("Candle Engine", "Closed candle history is unavailable.", runtime_snapshot, timestamp)
        latest_price = _latest_price(runtime_snapshot, history)
        previous_price = history[-2].close if len(history) >= 2 else None
        opening_price = history[0].open
        previous_day = _previous_day_from_cpr(cpr)
        failures: list[VisionContextAssemblyFailure] = []

        try:
            level = assemble_vision_level_context(
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
                    adr=runtime_snapshot.adr,
                    vwap=runtime_snapshot.vwap,
                    previous_price=previous_price,
                ),
                instrument=runtime_snapshot.symbol,
                timeframe=timeframe,
                max_snapshot_age=timedelta(days=1),
            )
        except Exception as exc:
            failures.append(_failure("Level Context", exc))
            level = assemble_vision_level_context(
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
                    adr=None,
                    vwap=None,
                    previous_price=previous_price,
                ),
                instrument=runtime_snapshot.symbol,
                timeframe=timeframe,
                max_snapshot_age=timedelta(days=1),
            )
        try:
            opening_range = assemble_vision_opening_range_context(
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
        except Exception as exc:
            failures.append(_failure("Opening Range", exc))
            opening_range = _fallback_opening_range(timestamp, history)
        try:
            structure = assemble_vision_structure_context(
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
        except Exception as exc:
            failures.append(_failure("Structure", exc))
            structure = _fallback_structure()
        try:
            liquidity = assemble_vision_liquidity_context(
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
        except Exception as exc:
            failures.append(_failure("Liquidity", exc))
            liquidity = _fallback_liquidity()
        try:
            structure_events = assemble_vision_structure_event_context(
                VisionStructureEventRequest(
                    instrument=runtime_snapshot.symbol,
                    timeframe=timeframe,
                    trading_date=trading_date,
                    timestamp=timestamp,
                    candles=history,
                    structure_context=structure,
                    liquidity_context=liquidity,
                ),
                instrument=runtime_snapshot.symbol,
                timeframe=timeframe,
            )
        except Exception as exc:
            failures.append(_failure("Structure Events", exc))
            structure_events = _fallback_structure_events()
        try:
            setup = assemble_vision_setup_qualification_context(
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
        except Exception as exc:
            failures.append(_failure("Setup", exc))
            setup = _fallback_setup(failures)
        option_chain, option_analytics = self._option_inputs(runtime_snapshot.symbol)
        option_expiry = option_chain.expiry_date if option_chain is not None else cpr.trading_date
        try:
            option_confirmation = assemble_vision_option_confirmation_context(
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
        except Exception as exc:
            failures.append(_failure("Option Confirmation", exc))
            option_confirmation = _fallback_option_confirmation(timestamp, failures)
        snapshot = calculate_vision_method_snapshot(
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
                assembly_failures=tuple(failures),
            ),
            instrument=runtime_snapshot.symbol,
            timeframe=timeframe,
        )
        return snapshot, tuple(failures)

    def _select_runtime(self):
        runtimes = tuple(self._lifecycle.orchestrator.runtimes)
        if not runtimes:
            raise _VisionMethodNotReady("No symbol runtime is available.")
        return runtimes[0]

    def _not_ready(self, stage: str, message: str, runtime_snapshot, timestamp) -> _VisionMethodNotReady:
        failure = VisionContextAssemblyFailure(
            stage=stage,
            status=VisionContextAssemblyStatus.MISSING,
            failure_reason=message,
            validation_message=message,
        )
        return _VisionMethodNotReady(
            message,
            failure=failure,
            instrument=getattr(getattr(runtime_snapshot, "symbol", None), "value", "-"),
            timeframe=str(getattr(runtime_snapshot, "timeframe", "-")),
            timestamp=timestamp.isoformat() if hasattr(timestamp, "isoformat") else "-",
        )

    def _option_inputs(
        self,
        instrument: RuntimeInstrument,
    ) -> tuple[OptionChainSnapshot | None, OptionChainAnalyticsSnapshot | None]:
        if self._option_analytics_provider is None:
            return None, None
        option_chain, analytics = self._option_analytics_provider(instrument)
        if option_chain is not None and not isinstance(option_chain, OptionChainSnapshot):
            raise TypeError("option provider must return OptionChainSnapshot or None.")
        if analytics is not None and not isinstance(analytics, OptionChainAnalyticsSnapshot):
            raise TypeError("option provider must return OptionChainAnalyticsSnapshot or None.")
        return option_chain, analytics


class _VisionMethodNotReady(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure: VisionContextAssemblyFailure | None = None,
        instrument: str = "-",
        timeframe: str = "-",
        timestamp: str = "-",
    ):
        super().__init__(message)
        self.failure = failure
        self.instrument = instrument
        self.timeframe = timeframe
        self.timestamp = timestamp


def _runtime_timestamp(runtime_snapshot) -> object:
    timestamp = runtime_snapshot.latest_closed_candle_at or runtime_snapshot.latest_tick_at or runtime_snapshot.updated_at
    if timestamp is None:
        raise _VisionMethodNotReady("No market timestamp is available.")
    return timestamp


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


def _failure(stage: str, exc: Exception) -> VisionContextAssemblyFailure:
    message = _safe_error(exc)
    return VisionContextAssemblyFailure(
        stage=stage,
        status=VisionContextAssemblyStatus.FAILED,
        failure_reason=exc.__class__.__name__,
        validation_message=message,
    )


def _fallback_opening_range(timestamp, history) -> object:
    session_start = timestamp.replace(hour=9, minute=15, second=0, microsecond=0)
    session_end = session_start + timedelta(minutes=15)
    high = max((candle.high for candle in history), default=1.0)
    low = min((candle.low for candle in history), default=high)
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
    )


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
    return VisionOptionConfirmationContext(
        confirmation_state=VisionOptionConfirmation.UNAVAILABLE,
        supporting_factors=(),
        contradicting_factors=(),
        neutral_factors=(reason,),
        quality=VisionLevelQuality.INSUFFICIENT,
        timestamp=timestamp,
    )


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip()
    return f"{exc.__class__.__name__}: {text}" if text else exc.__class__.__name__
