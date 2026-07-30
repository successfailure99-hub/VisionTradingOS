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
    VisionLevelContextRequest,
    VisionLiquidityRequest,
    VisionMethodCalculationRequest,
    VisionMethodSnapshot,
    VisionMethodValidationReport,
    VisionOpeningRangeRequest,
    VisionOptionConfirmationRequest,
    VisionSetupQualificationRequest,
    VisionStructureEventRequest,
    VisionStructureRequest,
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
            snapshot = self._build_snapshot()
            self._logger.debug("[VisionMethod] Snapshot generated")
            report = validate_vision_method(snapshot)
            self._logger.debug("[VisionMethod] Validation complete")
        except _VisionMethodNotReady as exc:
            self._last_snapshot = None
            self._last_report = None
            self._inspector.render(None, None)
            self._logger.debug("[VisionMethod] Inspector updated")
            return VisionMethodInspectorLiveResult(None, None, True, False, str(exc))
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
        return VisionMethodInspectorLiveResult(snapshot, report, True, True)

    def _build_snapshot(self) -> VisionMethodSnapshot:
        runtime = self._select_runtime()
        runtime_snapshot = runtime.snapshot()
        timeframe = TimeFrame.from_value(runtime_snapshot.timeframe)
        timestamp = _runtime_timestamp(runtime_snapshot)
        trading_date = timestamp.date()
        cpr = runtime_snapshot.cpr
        camarilla = runtime_snapshot.camarilla
        if cpr is None:
            raise _VisionMethodNotReady("CPR is unavailable.")
        if camarilla is None:
            raise _VisionMethodNotReady("Camarilla is unavailable.")
        history = tuple(
            candle
            for candle in runtime.get_candle_history(timeframe)
            if candle.start_time.date() == trading_date and candle.end_time <= timestamp
        )
        if not history:
            raise _VisionMethodNotReady("Closed candle history is unavailable.")
        latest_price = _latest_price(runtime_snapshot, history)
        previous_price = history[-2].close if len(history) >= 2 else None
        opening_price = history[0].open
        previous_day = _previous_day_from_cpr(cpr)

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
        option_chain, option_analytics = self._option_inputs(runtime_snapshot.symbol)
        option_expiry = option_chain.expiry_date if option_chain is not None else cpr.trading_date
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
        return calculate_vision_method_snapshot(
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
            ),
            instrument=runtime_snapshot.symbol,
            timeframe=timeframe,
        )

    def _select_runtime(self):
        runtimes = tuple(self._lifecycle.orchestrator.runtimes)
        if not runtimes:
            raise _VisionMethodNotReady("No symbol runtime is available.")
        return runtimes[0]

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
    pass


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


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip()
    return f"{exc.__class__.__name__}: {text}" if text else exc.__class__.__name__
