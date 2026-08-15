"""
Live Vision Method inspector integration.

This module is presentation glue for VM-11.1. It reads the existing immutable
runtime state, assembles the already-certified Vision Method contexts, validates
the resulting snapshot, and renders the pair in the read-only inspector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    VisionPriceActionTriggerStageResult,
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
from engines.vision_method.runtime_evaluator import assemble_vision_method_runtime

from .status import VisionMethodLiveRuntimeState, VisionMethodLiveStatus
from .vision_method_inspector import VisionMethodInspector


LOGGER = logging.getLogger(__name__)
LIVE_MARKET_DATA_STALE_SECONDS = 120.0


def _default_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class VisionMethodInspectorLiveResult:
    snapshot: VisionMethodSnapshot | None
    validation_report: VisionMethodValidationReport | None
    status: VisionMethodLiveStatus
    rendered: bool
    ready: bool
    reason: str | None = None
    failures: tuple[VisionContextAssemblyFailure, ...] = ()


@dataclass(frozen=True, slots=True)
class _LiveAssembly:
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
        clock=None,
        logger: logging.Logger | None = None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be ApplicationLifecycleManager.")
        if not isinstance(inspector, VisionMethodInspector):
            raise TypeError("inspector must be VisionMethodInspector.")
        self._lifecycle = lifecycle
        self._inspector = inspector
        self._option_analytics_provider = option_analytics_provider
        self._clock = clock or _default_clock
        self._logger = logger or LOGGER
        self._last_snapshot: VisionMethodSnapshot | None = None
        self._last_report: VisionMethodValidationReport | None = None
        self._last_status: VisionMethodLiveStatus | None = None
        self._latest_signature: tuple[object, ...] | None = None
        self._last_rendered_signature: tuple[object, ...] | None = None
        self._visual_render_count = 0
        self._visual_render_skip_count = 0

    @property
    def last_snapshot(self) -> VisionMethodSnapshot | None:
        return self._last_snapshot

    @property
    def last_report(self) -> VisionMethodValidationReport | None:
        return self._last_report

    @property
    def last_status(self) -> VisionMethodLiveStatus | None:
        return self._last_status

    @property
    def visual_render_count(self) -> int:
        return self._visual_render_count

    @property
    def visual_render_skip_count(self) -> int:
        return self._visual_render_skip_count

    @property
    def has_unrendered_change(self) -> bool:
        return self._latest_signature is not None and self._latest_signature != self._last_rendered_signature

    def refresh(self, *, render_visual: bool = True) -> VisionMethodInspectorLiveResult:
        return self.refresh_diagnostic_local_assembly(render_visual=render_visual)

    def capture_latest_runtime_state(self) -> VisionMethodInspectorLiveResult:
        try:
            runtime = self._select_runtime()
            runtime_snapshot = runtime.snapshot()
        except _VisionMethodNotReady as exc:
            self._last_snapshot = None
            self._last_report = None
            status = self._status_from_not_ready(exc)
            self._last_status = status
            self._latest_signature = self._presentation_signature(None, None, status)
            self._log_status(status)
            return VisionMethodInspectorLiveResult(None, None, status, False, False, str(exc), (*status.missing_contexts, *status.failed_contexts))
        except Exception as exc:
            self._last_snapshot = None
            self._last_report = None
            status = self._internal_error_status(exc)
            self._last_status = status
            self._latest_signature = self._presentation_signature(None, None, status)
            self._logger.exception("[VisionMethodLive] state=INTERNAL_ERROR reason=%r", status.blocking_reason)
            return VisionMethodInspectorLiveResult(None, None, status, False, False, _safe_error(exc), status.failed_contexts)

        snapshot = getattr(runtime_snapshot, "vision_method_snapshot", None)
        report = getattr(runtime_snapshot, "vision_method_validation_report", None)
        if snapshot is not None and not isinstance(snapshot, VisionMethodSnapshot):
            raise TypeError("runtime vision_method_snapshot must be VisionMethodSnapshot or None.")
        if report is not None and not isinstance(report, VisionMethodValidationReport):
            raise TypeError("runtime vision_method_validation_report must be VisionMethodValidationReport or None.")
        self._last_snapshot = snapshot
        self._last_report = report
        status = self._status_from_runtime_snapshot(runtime_snapshot, snapshot, report)
        self._last_status = status
        self._latest_signature = self._presentation_signature(snapshot, report, status)
        self._log_status(status)
        failures = tuple(getattr(snapshot, "assembly_failures", ()) or ())
        return VisionMethodInspectorLiveResult(snapshot, report, status, False, snapshot is not None and report is not None and not failures, failures=failures)

    def refresh_diagnostic_local_assembly(self, *, render_visual: bool = False) -> VisionMethodInspectorLiveResult:
        try:
            assembly = self._assemble_live()
            snapshot = assembly.snapshot
            report = assembly.report
            failures = assembly.failures
        except _VisionMethodNotReady as exc:
            self._last_snapshot = None
            self._last_report = None
            status = self._status_from_not_ready(exc)
            self._last_status = status
            if render_visual:
                self._inspector.render_live_status(status)
            self._log_status(status)
            return VisionMethodInspectorLiveResult(None, None, status, render_visual, False, str(exc), (*status.missing_contexts, *status.failed_contexts))
        except Exception as exc:
            self._last_snapshot = None
            self._last_report = None
            status = self._internal_error_status(exc)
            self._last_status = status
            if render_visual:
                self._inspector.render_live_status(status)
            self._logger.exception("[VisionMethodLive] state=INTERNAL_ERROR reason=%r", status.blocking_reason)
            return VisionMethodInspectorLiveResult(None, None, status, render_visual, False, _safe_error(exc), status.failed_contexts)

        self._last_snapshot = snapshot
        self._last_report = report
        status = self._status_from_assembly(assembly)
        self._last_status = status
        if render_visual:
            self._inspector.render_live_status(status, snapshot, report)
        self._log_status(status)
        return VisionMethodInspectorLiveResult(snapshot, report, status, render_visual, not failures, failures=failures)

    def render_latest(self, *, force: bool = False) -> bool:
        if self._last_status is None:
            return False
        signature = self._latest_signature or self._presentation_signature(self._last_snapshot, self._last_report, self._last_status)
        if not force and signature == self._last_rendered_signature:
            self._visual_render_skip_count += 1
            return False
        self._inspector.render_live_status(self._last_status, self._last_snapshot, self._last_report)
        self._last_rendered_signature = signature
        self._visual_render_count += 1
        return True

    def _status_from_runtime_snapshot(
        self,
        runtime_snapshot,
        snapshot: VisionMethodSnapshot | None,
        report: VisionMethodValidationReport | None,
    ) -> VisionMethodLiveStatus:
        timestamp = _runtime_display_timestamp(runtime_snapshot)
        operational = getattr(runtime_snapshot, "operational_readiness", None)
        history = getattr(runtime_snapshot, "vision_decision_history_readiness", None)
        failures = tuple(getattr(snapshot, "assembly_failures", ()) or ())
        if snapshot is not None and report is not None:
            runtime_state = VisionMethodLiveRuntimeState.DEGRADED if failures else VisionMethodLiveRuntimeState.READY
            candidate_state = snapshot.candidate_state.value
            quality = str(snapshot.quality)
            validation_result = report.validation_result.value
            blocking_stage = report.metrics.blocking_stage or "none"
            blocking_reason = _runtime_blocking_reason(operational, failures, "none")
        else:
            runtime_state = _runtime_state_from_readiness(operational, history, timestamp)
            candidate_state = VisionCandidateState.INSUFFICIENT_DATA.value
            quality = "insufficient"
            validation_result = "insufficient_data"
            blocking_stage = _readiness_component(history) or "VISION_METHOD"
            blocking_reason = _runtime_blocking_reason(operational, failures, _readiness_reason(history))
        return VisionMethodLiveStatus(
            instrument=getattr(getattr(runtime_snapshot, "symbol", None), "value", "-"),
            timeframe=str(getattr(runtime_snapshot, "vision_decision_timeframe", None) or getattr(runtime_snapshot, "timeframe", "-")),
            market_timestamp=timestamp,
            runtime_state=runtime_state,
            candidate_state=candidate_state,
            quality=quality,
            validation_result=validation_result,
            blocking_stage=blocking_stage,
            blocking_reason=blocking_reason,
            available_contexts=_available_contexts(runtime_snapshot, snapshot),
            missing_contexts=(),
            failed_contexts=failures,
            unexpected_error=None,
            updated_at=self._clock(),
            market_data_age_seconds=_market_age_seconds(runtime_snapshot, _runtime_timestamp_or_none(runtime_snapshot), observed_at=self._clock()),
            level_context=getattr(snapshot, "level_context", None) if snapshot is not None else None,
            opening_range_context=getattr(snapshot, "opening_range_context", None) if snapshot is not None else None,
            structure_context=getattr(snapshot, "structure_context", None) if snapshot is not None else None,
            liquidity_context=getattr(snapshot, "liquidity_context", None) if snapshot is not None else None,
            structure_event_context=getattr(snapshot, "structure_event_context", None) if snapshot is not None else None,
            setup_qualification_context=getattr(snapshot, "setup_qualification_context", None) if snapshot is not None else None,
            option_confirmation_context=getattr(snapshot, "option_confirmation_context", None) if snapshot is not None else None,
            pivot_flight_plan=getattr(snapshot, "pivot_flight_plan", None) if snapshot is not None else getattr(runtime_snapshot, "pivot_flight_plan", None),
            pivot_opening_assessment=getattr(snapshot, "pivot_opening_assessment", None) if snapshot is not None else getattr(runtime_snapshot, "pivot_opening_assessment", None),
            pivot_confluence_context=getattr(snapshot, "pivot_confluence_context", None) if snapshot is not None else getattr(runtime_snapshot, "pivot_confluence_context", None),
            price_action_trigger_context=getattr(snapshot, "price_action_trigger_context", None) if snapshot is not None else getattr(runtime_snapshot, "price_action_trigger_context", None),
            price_action_trigger_stage_result=getattr(snapshot, "price_action_trigger_stage_result", None) if snapshot is not None else getattr(runtime_snapshot, "price_action_trigger_stage_result", None),
        )

    def _presentation_signature(
        self,
        snapshot: VisionMethodSnapshot | None,
        report: VisionMethodValidationReport | None,
        status: VisionMethodLiveStatus,
    ) -> tuple[object, ...]:
        report_metrics = getattr(report, "metrics", None)
        trigger_stage = getattr(status.price_action_trigger_stage_result, "status", None)
        return (
            getattr(snapshot, "instrument", None),
            getattr(snapshot, "timeframe", None),
            getattr(snapshot, "timestamp", None),
            getattr(getattr(snapshot, "candidate_state", None), "value", None),
            getattr(snapshot, "quality", None),
            getattr(getattr(report, "validation_result", None), "value", None),
            getattr(report_metrics, "completed_steps", None),
            getattr(report_metrics, "failed_steps", None),
            getattr(report_metrics, "missing_steps", None),
            getattr(report_metrics, "blocking_stage", None),
            status.runtime_state.value,
            status.blocking_stage,
            status.blocking_reason,
            status.candidate_state,
            status.quality,
            status.validation_result,
            getattr(trigger_stage, "value", trigger_stage),
            tuple((failure.stage, failure.status.value, failure.validation_message) for failure in (*status.missing_contexts, *status.failed_contexts)),
        )

    def _assemble_live(self) -> _LiveAssembly:
        runtime = self._select_runtime()
        try:
            return assemble_vision_method_runtime(
                runtime,
                option_analytics_provider=self._option_analytics_provider,
                observed_at=self._clock(),
                logger=self._logger,
                level_assembler=assemble_vision_level_context,
                opening_range_assembler=assemble_vision_opening_range_context,
                structure_assembler=assemble_vision_structure_context,
                liquidity_assembler=assemble_vision_liquidity_context,
                structure_event_assembler=assemble_vision_structure_event_context,
                setup_assembler=assemble_vision_setup_qualification_context,
                option_confirmation_assembler=assemble_vision_option_confirmation_context,
                calculator=calculate_vision_method_snapshot,
                validator=validate_vision_method,
            )
        except RuntimeError as exc:
            if str(exc) == "No market timestamp is available.":
                runtime_snapshot = runtime.snapshot()
                raise _VisionMethodNotReady(
                    "No market timestamp is available.",
                    failure=_missing_failure("Market Data", "No market timestamp is available."),
                    instrument=getattr(getattr(runtime_snapshot, "symbol", None), "value", "-"),
                    timeframe=str(_vision_decision_timeframe(runtime, runtime_snapshot).value),
                    timestamp="-",
                    market_data_age_seconds=None,
                    available_contexts=(),
                    runtime_state=VisionMethodLiveRuntimeState.WAITING_FOR_MARKET_DATA,
                    blocking_stage="MARKET_DATA",
                ) from exc
            raise

    def _build_snapshot(self) -> tuple[VisionMethodSnapshot, tuple[VisionContextAssemblyFailure, ...]]:
        runtime = self._select_runtime()
        runtime_snapshot = runtime.snapshot()
        timeframe = _vision_decision_timeframe(runtime, runtime_snapshot)
        timestamp = _runtime_timestamp(runtime_snapshot)
        trading_date = _market_session_date(timestamp)
        history = tuple(
            candle
            for candle in runtime.get_candle_history(timeframe)
            if candle.start_time.date() == trading_date and candle.end_time <= timestamp
        )
        if not history:
            raise self._not_ready(
                "Candle Engine",
                "Closed candle history is unavailable.",
                runtime_snapshot,
                timestamp,
                available_contexts=("Market Data",),
            )
        cpr = runtime_snapshot.cpr
        camarilla = runtime_snapshot.camarilla
        if cpr is None:
            raise self._not_ready(
                "CPR",
                "Daily CPR levels are unavailable.",
                runtime_snapshot,
                timestamp,
                available_contexts=("Market Data", "Candle Engine"),
            )
        if cpr.trading_date != trading_date:
            raise self._not_ready(
                "CPR",
                _session_mismatch_reason("CPR", cpr.trading_date, trading_date),
                runtime_snapshot,
                timestamp,
                available_contexts=("Market Data", "Candle Engine"),
            )
        if camarilla is None:
            raise self._not_ready(
                "Camarilla",
                "Daily Camarilla levels are unavailable.",
                runtime_snapshot,
                timestamp,
                available_contexts=("Market Data", "Candle Engine"),
            )
        if camarilla.trading_date != trading_date:
            raise self._not_ready(
                "Camarilla",
                _session_mismatch_reason("Camarilla", camarilla.trading_date, trading_date),
                runtime_snapshot,
                timestamp,
                available_contexts=("Market Data", "Candle Engine", "CPR"),
            )
        latest_price = _latest_price(runtime_snapshot, history)
        previous_price = history[-2].close if len(history) >= 2 else None
        opening_price = history[0].open
        previous_day = _previous_day_from_cpr(cpr)
        failures: list[VisionContextAssemblyFailure] = []
        adr, vwap = _session_aligned_optional_contexts(runtime_snapshot, trading_date, failures)

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
                    adr=adr,
                    vwap=vwap,
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
            opening_range = _fallback_opening_range(timestamp, history, timeframe)
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
                    liquidity_context=liquidity if liquidity.quality is not VisionLevelQuality.INSUFFICIENT else None,
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
        option_chain, option_analytics = self._option_inputs(runtime_snapshot)
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
                current_price=history[-1].close,
                pivot_flight_plan=getattr(runtime_snapshot, "pivot_flight_plan", None),
                pivot_opening_assessment=getattr(runtime_snapshot, "pivot_opening_assessment", None),
                pivot_confluence_context=getattr(runtime_snapshot, "pivot_confluence_context", None),
                price_action_trigger_context=getattr(runtime_snapshot, "price_action_trigger_context", None),
                assembly_failures=tuple(failures),
            ),
            instrument=runtime_snapshot.symbol,
            timeframe=timeframe,
        )
        return snapshot, tuple(failures)

    def _select_runtime(self):
        runtimes = tuple(self._lifecycle.orchestrator.runtimes)
        if not runtimes:
            raise _VisionMethodNotReady(
                "No symbol runtime is available.",
                failure=_missing_failure("Market Data", "No symbol runtime is available."),
                runtime_state=VisionMethodLiveRuntimeState.WAITING_FOR_MARKET_DATA,
                blocking_stage="MARKET_DATA",
            )
        return runtimes[0]

    def _not_ready(
        self,
        stage: str,
        message: str,
        runtime_snapshot,
        timestamp,
        *,
        available_contexts: tuple[str, ...] = (),
    ) -> _VisionMethodNotReady:
        failure = _missing_failure(stage, message)
        return _VisionMethodNotReady(
            message,
            failure=failure,
            instrument=getattr(getattr(runtime_snapshot, "symbol", None), "value", "-"),
            timeframe=str(getattr(runtime_snapshot, "timeframe", "-")),
            timestamp=timestamp.isoformat() if hasattr(timestamp, "isoformat") else "-",
            market_data_age_seconds=_market_age_seconds(runtime_snapshot, timestamp, observed_at=self._clock()),
            available_contexts=available_contexts,
            runtime_state=VisionMethodLiveRuntimeState.COLLECTING_CONTEXT,
            blocking_stage=_stage_label(stage),
        )

    def _option_inputs(
        self,
        runtime_snapshot,
    ) -> tuple[OptionChainSnapshot | None, OptionChainAnalyticsSnapshot | None]:
        option_chain = getattr(runtime_snapshot, "option_chain_snapshot", None)
        analytics = getattr(runtime_snapshot, "option_chain_analytics", None)
        if option_chain is None and analytics is None and self._option_analytics_provider is not None:
            option_chain, analytics = self._option_analytics_provider(runtime_snapshot.symbol)
        if option_chain is not None and not isinstance(option_chain, OptionChainSnapshot):
            raise TypeError("option provider must return OptionChainSnapshot or None.")
        if analytics is not None and not isinstance(analytics, OptionChainAnalyticsSnapshot):
            raise TypeError("option provider must return OptionChainAnalyticsSnapshot or None.")
        return option_chain, analytics

    def _status_from_not_ready(self, exc: _VisionMethodNotReady) -> VisionMethodLiveStatus:
        missing = (exc.failure,) if exc.failure is not None and exc.failure.status is not VisionContextAssemblyStatus.FAILED else ()
        failed = (exc.failure,) if exc.failure is not None and exc.failure.status is VisionContextAssemblyStatus.FAILED else ()
        return VisionMethodLiveStatus(
            instrument=exc.instrument,
            timeframe=exc.timeframe,
            market_timestamp=exc.timestamp,
            runtime_state=exc.runtime_state,
            candidate_state=VisionCandidateState.INSUFFICIENT_DATA.value,
            quality="insufficient",
            validation_result="insufficient_data",
            blocking_stage=exc.blocking_stage,
            blocking_reason=str(exc),
            available_contexts=exc.available_contexts,
            missing_contexts=missing,
            failed_contexts=failed,
            unexpected_error=None,
            updated_at=self._clock(),
            market_data_age_seconds=exc.market_data_age_seconds,
        )

    def _status_from_assembly(self, assembly: _LiveAssembly) -> VisionMethodLiveStatus:
        failures = assembly.failures
        missing = tuple(item for item in failures if item.status is not VisionContextAssemblyStatus.FAILED)
        failed = tuple(item for item in failures if item.status is VisionContextAssemblyStatus.FAILED)
        if assembly.report is not None and assembly.report.validation_result.value == "valid":
            runtime_state = VisionMethodLiveRuntimeState.READY
        elif failed:
            runtime_state = VisionMethodLiveRuntimeState.DEGRADED
        elif _has_daily_context_wait(failures):
            runtime_state = VisionMethodLiveRuntimeState.WAITING_DAILY_CONTEXT
        else:
            runtime_state = VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
        first_blocker = next((failure for failure in failures if _assembly_failure_blocks(failure)), None)
        snapshot = assembly.snapshot
        report = assembly.report
        updated_at = self._clock()
        return VisionMethodLiveStatus(
            instrument=getattr(getattr(assembly.runtime_snapshot, "symbol", None), "value", "-"),
            timeframe=assembly.timeframe.value,
            market_timestamp=assembly.timestamp.isoformat(),
            runtime_state=runtime_state,
            candidate_state=snapshot.candidate_state.value if snapshot is not None else VisionCandidateState.INSUFFICIENT_DATA.value,
            quality=snapshot.quality if snapshot is not None else "insufficient",
            validation_result=report.validation_result.value if report is not None else "insufficient_data",
            blocking_stage=(report.metrics.blocking_stage if report is not None and report.metrics.blocking_stage else None)
            or (_stage_label(first_blocker.stage) if first_blocker is not None else "none"),
            blocking_reason=first_blocker.validation_message if first_blocker is not None else "none",
            available_contexts=_available_contexts_from_assembly(assembly),
            missing_contexts=missing,
            failed_contexts=failed,
            unexpected_error=None,
            updated_at=updated_at,
            market_data_age_seconds=_market_age_seconds(assembly.runtime_snapshot, assembly.timestamp, observed_at=updated_at),
            level_context=assembly.level,
            opening_range_context=assembly.opening_range,
            structure_context=assembly.structure,
            liquidity_context=assembly.liquidity,
            structure_event_context=assembly.structure_events,
            setup_qualification_context=assembly.setup,
            option_confirmation_context=assembly.option_confirmation,
            pivot_flight_plan=assembly.pivot_flight_plan,
            pivot_opening_assessment=assembly.pivot_opening_assessment,
            pivot_confluence_context=assembly.pivot_confluence_context,
            price_action_trigger_context=assembly.price_action_trigger_context,
            price_action_trigger_stage_result=assembly.price_action_trigger_stage_result,
        )

    def _status_from_snapshot(
        self,
        snapshot: VisionMethodSnapshot,
        report: VisionMethodValidationReport,
        failures: tuple[VisionContextAssemblyFailure, ...],
    ) -> VisionMethodLiveStatus:
        missing = tuple(item for item in failures if item.status is not VisionContextAssemblyStatus.FAILED)
        failed = tuple(item for item in failures if item.status is VisionContextAssemblyStatus.FAILED)
        if report.validation_result.value == "valid":
            runtime_state = VisionMethodLiveRuntimeState.READY
        elif failed:
            runtime_state = VisionMethodLiveRuntimeState.DEGRADED
        else:
            runtime_state = VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
        blocking_reason = report.metrics.blocking_stage or "none"
        first_blocker = next((failure for failure in failures if _assembly_failure_blocks(failure)), None)
        if first_blocker is not None:
            blocking_reason = first_blocker.validation_message
        return VisionMethodLiveStatus(
            instrument=snapshot.instrument.value,
            timeframe=snapshot.timeframe.value,
            market_timestamp=snapshot.timestamp.isoformat(),
            runtime_state=runtime_state,
            candidate_state=snapshot.candidate_state.value,
            quality=snapshot.quality,
            validation_result=report.validation_result.value,
            blocking_stage=report.metrics.blocking_stage or "none",
            blocking_reason=blocking_reason,
            available_contexts=_available_contexts(snapshot),
            missing_contexts=missing,
            failed_contexts=failed,
            unexpected_error=None,
            updated_at=self._clock(),
            market_data_age_seconds=0.0,
            pivot_flight_plan=snapshot.pivot_flight_plan,
            pivot_opening_assessment=snapshot.pivot_opening_assessment,
            pivot_confluence_context=snapshot.pivot_confluence_context,
            price_action_trigger_context=snapshot.price_action_trigger_context,
            price_action_trigger_stage_result=snapshot.price_action_trigger_stage_result,
        )

    def _internal_error_status(self, exc: Exception) -> VisionMethodLiveStatus:
        failure = VisionContextAssemblyFailure(
            stage="Internal Error",
            status=VisionContextAssemblyStatus.FAILED,
            failure_reason=exc.__class__.__name__,
            validation_message=_safe_error(exc),
        )
        return VisionMethodLiveStatus(
            instrument="-",
            timeframe="-",
            market_timestamp="unavailable",
            runtime_state=VisionMethodLiveRuntimeState.INTERNAL_ERROR,
            candidate_state=VisionCandidateState.INSUFFICIENT_DATA.value,
            quality="invalid",
            validation_result="invalid",
            blocking_stage="INTERNAL_ERROR",
            blocking_reason=failure.validation_message,
            available_contexts=(),
            missing_contexts=(),
            failed_contexts=(failure,),
            unexpected_error=failure.validation_message,
            updated_at=self._clock(),
            market_data_age_seconds=None,
        )

    def _log_status(self, status: VisionMethodLiveStatus) -> None:
        if status.runtime_state is VisionMethodLiveRuntimeState.WAITING_FOR_MARKET_DATA:
            self._logger.debug("[VisionMethodLive] state=%s reason=%r", status.runtime_state.value, status.blocking_reason)
        elif status.runtime_state is VisionMethodLiveRuntimeState.DEGRADED:
            failed = ",".join(item.stage for item in status.failed_contexts) or "none"
            self._logger.debug("[VisionMethodLive] state=%s failed=%s reason=%r", status.runtime_state.value, failed, status.blocking_reason)
        elif status.runtime_state is VisionMethodLiveRuntimeState.READY:
            self._logger.debug(
                "[VisionMethodLive] state=%s candidate=%s validation=%s",
                status.runtime_state.value,
                status.candidate_state,
                status.validation_result,
            )
        else:
            self._logger.debug(
                "[VisionMethodLive] state=%s available=%s missing=%s failed=%s blocking=%s",
                status.runtime_state.value,
                len(status.available_contexts),
                len(status.missing_contexts),
                len(status.failed_contexts),
                status.blocking_stage,
            )


class _VisionMethodNotReady(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure: VisionContextAssemblyFailure | None = None,
        instrument: str = "-",
        timeframe: str = "-",
        timestamp: str = "-",
        market_data_age_seconds: float | None = None,
        available_contexts: tuple[str, ...] = (),
        runtime_state: VisionMethodLiveRuntimeState = VisionMethodLiveRuntimeState.COLLECTING_CONTEXT,
        blocking_stage: str = "VISION_METHOD",
    ):
        super().__init__(message)
        self.failure = failure
        self.instrument = instrument
        self.timeframe = timeframe
        self.timestamp = timestamp
        self.market_data_age_seconds = market_data_age_seconds
        self.available_contexts = available_contexts
        self.runtime_state = runtime_state
        self.blocking_stage = blocking_stage


def _runtime_timestamp(runtime_snapshot) -> object:
    runtime_session = getattr(runtime_snapshot, "runtime_session", None)
    timestamp = (
        getattr(runtime_session, "market_timestamp", None)
        or getattr(runtime_snapshot, "snapshot_created_at", None)
        or runtime_snapshot.latest_closed_candle_at
        or runtime_snapshot.latest_tick_at
        or runtime_snapshot.updated_at
    )
    if timestamp is None:
        raise _VisionMethodNotReady(
            "No market timestamp is available.",
            failure=_missing_failure("Market Data", "No market timestamp is available."),
            instrument=getattr(getattr(runtime_snapshot, "symbol", None), "value", "-"),
            timeframe=str(getattr(runtime_snapshot, "timeframe", "-")),
            runtime_state=VisionMethodLiveRuntimeState.WAITING_FOR_MARKET_DATA,
            blocking_stage="MARKET_DATA",
        )
    return timestamp


def _runtime_timestamp_or_none(runtime_snapshot):
    try:
        return _runtime_timestamp(runtime_snapshot)
    except _VisionMethodNotReady:
        return None


def _runtime_display_timestamp(runtime_snapshot) -> str:
    timestamp = _runtime_timestamp_or_none(runtime_snapshot)
    return timestamp.isoformat() if hasattr(timestamp, "isoformat") else "unavailable"


def _runtime_state_from_readiness(operational, history, timestamp: str) -> VisionMethodLiveRuntimeState:
    if timestamp in {"", "-", "unavailable"}:
        return VisionMethodLiveRuntimeState.WAITING_FOR_MARKET_DATA
    if history is not None and getattr(history, "status", None) not in {None, "READY"}:
        return VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
    if operational is not None and getattr(operational, "mandatory_blockers", ()):
        return VisionMethodLiveRuntimeState.COLLECTING_CONTEXT
    if operational is not None and getattr(operational, "optional_degradations", ()):
        return VisionMethodLiveRuntimeState.DEGRADED
    return VisionMethodLiveRuntimeState.COLLECTING_CONTEXT


def _readiness_component(readiness) -> str | None:
    component = getattr(readiness, "component", None)
    return _stage_label(component) if isinstance(component, str) and component.strip() else None


def _readiness_reason(readiness) -> str:
    reason = getattr(readiness, "reason", None)
    if isinstance(reason, str) and reason.strip() and reason.strip() != "-":
        return reason.strip()
    status = getattr(readiness, "status", None)
    if isinstance(status, str) and status.strip() and status.strip() != "-":
        return f"Vision runtime readiness is {status.strip()}."
    return "Canonical Vision runtime snapshot is not available yet."


def _runtime_blocking_reason(operational, failures: tuple[VisionContextAssemblyFailure, ...], fallback: str) -> str:
    if failures:
        return format_failures(failures)
    primary = getattr(operational, "primary_blocker", None)
    if isinstance(primary, str) and primary.strip() and primary.strip() != "-":
        return primary.strip()
    blockers = tuple(getattr(operational, "mandatory_blockers", ()) or ())
    if blockers:
        return "; ".join(str(item) for item in blockers if str(item).strip())
    degradations = tuple(getattr(operational, "optional_degradations", ()) or ())
    if degradations:
        return "; ".join(str(item) for item in degradations if str(item).strip())
    return fallback


def format_failures(failures: tuple[VisionContextAssemblyFailure, ...]) -> str:
    return "; ".join(f"{failure.stage}: {failure.validation_message}" for failure in failures) or "none"


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


def _failure(stage: str, exc: Exception) -> VisionContextAssemblyFailure:
    message = _operational_error_message(stage, exc)
    return VisionContextAssemblyFailure(
        stage=stage,
        status=VisionContextAssemblyStatus.FAILED,
        failure_reason=exc.__class__.__name__,
        validation_message=message,
    )


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


def _session_mismatch_reason(name: str, context_date, trading_date) -> str:
    if context_date < trading_date:
        return f"{name} belongs to previous trading session."
    if context_date > trading_date:
        return f"{name} belongs to a future trading session."
    return f"{name} belongs to a different trading session."


def _waiting_daily_context_reason(name: str, context_date, trading_date) -> str:
    return f"WAITING_DAILY_CONTEXT: {name} levels are not refreshed for {trading_date}."


def _has_daily_context_wait(failures: tuple[VisionContextAssemblyFailure, ...]) -> bool:
    daily_stages = {"CPR", "CAMARILLA", "PREVIOUS_DAY"}
    return any(
        _stage_label(item.stage) in daily_stages and "WAITING_DAILY_CONTEXT" in item.validation_message
        for item in failures
    )


def _assembly_failure_blocks(failure: VisionContextAssemblyFailure) -> bool:
    stage = failure.stage.strip().casefold().replace("_", " ")
    supporting_stages = {
        "adr",
        "vwap",
        "liquidity",
        "option confirmation",
        "option chain",
        "momentum",
        "volume",
    }
    return stage not in supporting_stages


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


def _stage_label(stage: str) -> str:
    return stage.strip().replace(" ", "_").upper()


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


def _available_contexts(runtime_snapshot, snapshot: VisionMethodSnapshot | None = None) -> tuple[str, ...]:
    if snapshot is None and isinstance(runtime_snapshot, VisionMethodSnapshot):
        snapshot = runtime_snapshot
        runtime_snapshot = None
    if snapshot is None:
        contexts = []
        if getattr(runtime_snapshot, "latest_tick", None) is not None or getattr(runtime_snapshot, "latest_closed_candle_at", None) is not None:
            contexts.append("Market Data")
        if getattr(runtime_snapshot, "candle_history_count", 0):
            contexts.append("Candle Engine")
        if getattr(runtime_snapshot, "cpr", None) is not None and getattr(runtime_snapshot, "camarilla", None) is not None:
            contexts.append("Level Context")
        if getattr(runtime_snapshot, "pivot_flight_plan", None) is not None:
            contexts.append("Pivot Flight Plan")
        if getattr(runtime_snapshot, "pivot_opening_assessment", None) is not None:
            contexts.append("Opening Assessment")
        if getattr(runtime_snapshot, "pivot_confluence_context", None) is not None:
            contexts.append("Pivot Confluence")
        if getattr(runtime_snapshot, "price_action_trigger_context", None) is not None:
            contexts.append("Price-Action Trigger")
        return tuple(contexts)
    contexts = ["Market Data", "Candle Engine", "Level Context"]
    if snapshot.pivot_flight_plan is not None:
        contexts.append("Pivot Flight Plan")
    if snapshot.pivot_opening_assessment is not None:
        contexts.append("Opening Assessment")
    if snapshot.opening_range_context.quality is not VisionLevelQuality.INSUFFICIENT:
        contexts.append("Opening Range")
    if snapshot.structure_context.quality is not VisionLevelQuality.INSUFFICIENT:
        contexts.append("Structure")
    if snapshot.liquidity_context.quality is not VisionLevelQuality.INSUFFICIENT:
        contexts.append("Liquidity")
    if snapshot.structure_event_context.quality is not VisionLevelQuality.INSUFFICIENT:
        contexts.append("Structure Events")
    if snapshot.setup_qualification_context.setup_quality is not VisionSetupQuality.INVALID:
        contexts.append("Setup Qualification")
    if snapshot.option_confirmation_context.quality is not VisionLevelQuality.INSUFFICIENT:
        contexts.append("Option Confirmation")
    return tuple(contexts)


def _available_contexts_from_assembly(assembly: _LiveAssembly) -> tuple[str, ...]:
    contexts = ["Market Data"]
    if not any(failure.stage == "Candle Engine" for failure in assembly.failures):
        contexts.append("Candle Engine")
    if assembly.level is not None:
        contexts.append("Level Context")
    if assembly.pivot_flight_plan is not None:
        contexts.append("Pivot Flight Plan")
    if assembly.pivot_opening_assessment is not None:
        contexts.append("Opening Assessment")
    if assembly.opening_range is not None and assembly.opening_range.quality is not VisionLevelQuality.INSUFFICIENT:
        contexts.append("Opening Range")
    if assembly.structure is not None and assembly.structure.quality is not VisionLevelQuality.INSUFFICIENT:
        contexts.append("Structure")
    if assembly.liquidity is not None and assembly.liquidity.quality is not VisionLevelQuality.INSUFFICIENT:
        contexts.append("Liquidity")
    if assembly.structure_events is not None and assembly.structure_events.quality is not VisionLevelQuality.INSUFFICIENT:
        contexts.append("Structure Events")
    if assembly.setup is not None and assembly.setup.setup_quality is not VisionSetupQuality.INVALID:
        contexts.append("Setup Qualification")
    if assembly.option_confirmation is not None and assembly.option_confirmation.quality is not VisionLevelQuality.INSUFFICIENT:
        contexts.append("Option Confirmation")
    stage = assembly.price_action_trigger_stage_result
    if stage is not None and getattr(getattr(stage, "status", None), "value", None) != "trigger_assembly_failed":
        contexts.append("Price-Action Trigger")
    return tuple(contexts)


def _fallback_opening_range(timestamp, history, timeframe: TimeFrame) -> object:
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


def _vision_decision_timeframe(runtime, runtime_snapshot) -> TimeFrame:
    configured = getattr(runtime, "vision_decision_timeframe", None)
    if isinstance(configured, TimeFrame):
        return configured
    if configured is not None:
        return TimeFrame.from_value(str(configured))
    snapshot_value = getattr(runtime_snapshot, "vision_decision_timeframe", None)
    if snapshot_value is not None:
        return TimeFrame.from_value(str(snapshot_value))
    return TimeFrame.FIVE_MINUTES


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
