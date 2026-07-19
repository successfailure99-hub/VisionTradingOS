from __future__ import annotations

import math
from collections import deque
from dataclasses import replace
from datetime import datetime, timedelta
from itertools import count
from time import monotonic

from application.enums import RuntimeInstrument
from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.events import (
    AI_DECISION_READY,
    AI_REASONING_V2_READY,
    AI_REASONING_V2_UPDATED,
    CAMARILLA_UPDATED,
    CANDLE_CLOSED,
    CANDLE_OPENED,
    CANDLE_UPDATED,
    CPR_UPDATED,
    EXECUTION_DRY_RUN_ACKNOWLEDGED,
    EXECUTION_DRY_RUN_CANCELLED,
    EXECUTION_DRY_RUN_FILLED,
    EXECUTION_DRY_RUN_PARTIALLY_FILLED,
    EXECUTION_DRY_RUN_REJECTED,
    EXECUTION_DRY_RUN_SUBMITTED,
    EXECUTION_INTENT_CREATED,
    MARKET_CONTEXT_UPDATED,
    MARKET_CONTEXT_V2_READY,
    MARKET_CONTEXT_V2_UPDATED,
    MARKET_UPDATED,
    NEW_TICK,
    OPTION_CHAIN_READY,
    OPTION_CHAIN_UPDATED,
    PAPER_ORDER_CREATED,
    PAPER_POSITION_CLOSED,
    PAPER_POSITION_OPENED,
    PAPER_TRADE_RECORDED,
    PERFORMANCE_ANALYTICS_UPDATED,
    POSITION_MANAGEMENT_V1_UPDATED,
    PRICE_ACTION_READY,
    RISK_MANAGEMENT_V2_READY,
    RISK_MANAGEMENT_V2_UPDATED,
    RISK_UPDATED,
    STRATEGY_DECISION_READY,
    STRATEGY_DECISION_V2_READY,
    STRATEGY_DECISION_V2_UPDATED,
    TRADE_JOURNAL_V1_UPDATED,
    TRADE_PERFORMANCE_ANALYTICS_UPDATED,
    VWAP_UPDATED,
)
from core.models.candle import Candle
from core.models.tick import Tick
from engines.live_market_validation.enums import (
    ComponentStatus,
    FindingResolution,
    OptionSnapshotQuality,
    RecoveryState,
    ValidationComponent,
    ValidationHealth,
    ValidationLifecycleState,
    ValidationMode,
    ValidationSeverity,
)
from engines.live_market_validation.models import (
    CandleValidationMetrics,
    ComponentFreshness,
    InstrumentValidationSummary,
    IST,
    LatencySummary,
    LiveMarketValidationConfiguration,
    OptionChainValidationMetrics,
    ReconnectSummary,
    TickValidationMetrics,
    ValidationCounters,
    ValidationFinding,
    ValidationSessionSnapshot,
)
from engines.live_market_validation.report import build_report, health_for_findings
from engines.live_market_validation.repository import LiveValidationRepository


VALIDATION_SESSION_STARTED = "live_validation_session_started"
VALIDATION_UPDATED = "live_validation_updated"
VALIDATION_FINDING = "live_validation_finding"
VALIDATION_SESSION_COMPLETED = "live_validation_session_completed"
VALIDATION_SESSION_FAILED = "live_validation_session_failed"
_VALIDATION_EVENTS = {
    VALIDATION_SESSION_STARTED,
    VALIDATION_UPDATED,
    VALIDATION_FINDING,
    VALIDATION_SESSION_COMPLETED,
    VALIDATION_SESSION_FAILED,
}
_INVALID_INSTRUMENT = object()

_EVENT_COMPONENTS = {
    NEW_TICK: ValidationComponent.MARKET_DATA,
    MARKET_UPDATED: ValidationComponent.MARKET_DATA,
    CANDLE_OPENED: ValidationComponent.CANDLE,
    CANDLE_UPDATED: ValidationComponent.CANDLE,
    CANDLE_CLOSED: ValidationComponent.CANDLE,
    PRICE_ACTION_READY: ValidationComponent.PRICE_ACTION,
    OPTION_CHAIN_UPDATED: ValidationComponent.OPTION_CHAIN,
    OPTION_CHAIN_READY: ValidationComponent.OPTION_CHAIN,
    CPR_UPDATED: ValidationComponent.CPR,
    CAMARILLA_UPDATED: ValidationComponent.CAMARILLA,
    VWAP_UPDATED: ValidationComponent.VWAP,
    MARKET_CONTEXT_UPDATED: ValidationComponent.MARKET_CONTEXT,
    MARKET_CONTEXT_V2_UPDATED: ValidationComponent.MARKET_CONTEXT,
    MARKET_CONTEXT_V2_READY: ValidationComponent.MARKET_CONTEXT,
    AI_DECISION_READY: ValidationComponent.AI_REASONING,
    AI_REASONING_V2_UPDATED: ValidationComponent.AI_REASONING,
    AI_REASONING_V2_READY: ValidationComponent.AI_REASONING,
    STRATEGY_DECISION_READY: ValidationComponent.STRATEGY,
    STRATEGY_DECISION_V2_UPDATED: ValidationComponent.STRATEGY,
    STRATEGY_DECISION_V2_READY: ValidationComponent.STRATEGY,
    RISK_UPDATED: ValidationComponent.RISK,
    RISK_MANAGEMENT_V2_UPDATED: ValidationComponent.RISK,
    RISK_MANAGEMENT_V2_READY: ValidationComponent.RISK,
    PAPER_ORDER_CREATED: ValidationComponent.PAPER_TRADING,
    PAPER_POSITION_OPENED: ValidationComponent.PAPER_TRADING,
    PAPER_POSITION_CLOSED: ValidationComponent.PAPER_TRADING,
    PAPER_TRADE_RECORDED: ValidationComponent.PAPER_TRADING,
    PERFORMANCE_ANALYTICS_UPDATED: ValidationComponent.PERFORMANCE_ANALYTICS,
    TRADE_PERFORMANCE_ANALYTICS_UPDATED: ValidationComponent.PERFORMANCE_ANALYTICS,
    TRADE_JOURNAL_V1_UPDATED: ValidationComponent.PERFORMANCE_ANALYTICS,
    EXECUTION_INTENT_CREATED: ValidationComponent.PAPER_TRADING,
    EXECUTION_DRY_RUN_SUBMITTED: ValidationComponent.PAPER_TRADING,
    EXECUTION_DRY_RUN_ACKNOWLEDGED: ValidationComponent.PAPER_TRADING,
    EXECUTION_DRY_RUN_PARTIALLY_FILLED: ValidationComponent.PAPER_TRADING,
    EXECUTION_DRY_RUN_FILLED: ValidationComponent.PAPER_TRADING,
    EXECUTION_DRY_RUN_CANCELLED: ValidationComponent.PAPER_TRADING,
    EXECUTION_DRY_RUN_REJECTED: ValidationComponent.PAPER_TRADING,
    POSITION_MANAGEMENT_V1_UPDATED: ValidationComponent.PAPER_TRADING,
}


class ValidationLifecycleError(ValueError):
    pass


class LiveMarketValidationEngine(BaseEngine):
    def __init__(
        self,
        event_bus,
        configuration: LiveMarketValidationConfiguration | None = None,
        *,
        clock=None,
        monotonic_clock=None,
        repository: LiveValidationRepository | None = None,
    ):
        super().__init__(event_bus)
        self._configuration = configuration or LiveMarketValidationConfiguration()
        if not isinstance(self._configuration, LiveMarketValidationConfiguration):
            raise TypeError("configuration must be LiveMarketValidationConfiguration")
        self._clock = clock or (lambda: datetime.now(IST))
        self._monotonic_clock = monotonic_clock or monotonic
        self._repository = repository or LiveValidationRepository(self._configuration.output_dir)
        self._counter = count(1)
        self._subscribed = False
        self._session_id = "-"
        self._state = ValidationLifecycleState.IDLE
        self._mode = ValidationMode.OFF
        self._started_at = None
        self._ended_at = None
        self._failure_reason = None
        self._final_summary = "-"
        self._last_report = None
        self._session_instruments = self._configuration.instruments
        self._findings: dict[tuple, ValidationFinding] = {}
        self._finding_order: deque[tuple] = deque(maxlen=self._configuration.max_findings)
        self._recent_events = deque(maxlen=self._configuration.max_recent_identities)
        self._recent_ticks = {instrument: deque(maxlen=self._configuration.max_recent_identities) for instrument in self._configuration.instruments}
        self._recent_candles = {instrument: deque(maxlen=self._configuration.max_recent_identities) for instrument in self._configuration.instruments}
        self._last_candle_end = {}
        self._last_option_identity = {}
        self._last_option_expiry = {}
        self._tick_metrics = {instrument: TickValidationMetrics() for instrument in self._configuration.instruments}
        self._candle_metrics = {instrument: CandleValidationMetrics() for instrument in self._configuration.instruments}
        self._option_metrics = {instrument: OptionChainValidationMetrics() for instrument in self._configuration.instruments}
        self._component_freshness: dict[tuple[ValidationComponent, RuntimeInstrument | None], ComponentFreshness] = {}
        self._counters = ValidationCounters()
        self._latency_samples: dict[str, deque[float]] = {}
        self._correlations: dict[str, float] = {}
        self._reconnect = ReconnectSummary()
        self._active_outage_started = None
        if self._configuration.enabled:
            self._subscribe_once()
        self._data = self.snapshot()

    @property
    def configuration(self) -> LiveMarketValidationConfiguration:
        return self._configuration

    def start_session(self, *, mode: ValidationMode | str | None = None, session_id: str | None = None, instruments=None) -> ValidationSessionSnapshot:
        if not self._configuration.enabled:
            raise ValidationLifecycleError("live market validation is disabled")
        if self._state not in (ValidationLifecycleState.IDLE, ValidationLifecycleState.COMPLETED, ValidationLifecycleState.FAILED):
            raise ValidationLifecycleError("validation session is already active")
        selected_mode = self._normalize_mode(mode or self._configuration.mode)
        if selected_mode is ValidationMode.OFF:
            raise ValidationLifecycleError("validation mode must be SIMULATION or LIVE_OBSERVE")
        selected_instruments = self._normalize_instruments(instruments or self._configuration.instruments)
        started_at = self._now()
        self._subscribe_once()
        self._session_id = session_id or f"{selected_mode.value}-{started_at.astimezone(IST).strftime('%Y%m%d%H%M%S')}"
        self._mode = selected_mode
        self._started_at = started_at
        self._ended_at = None
        self._failure_reason = None
        self._final_summary = "-"
        self._state = ValidationLifecycleState.RUNNING
        self._reset_transient(selected_instruments)
        snapshot = self.snapshot()
        self._publish(VALIDATION_SESSION_STARTED, snapshot)
        return snapshot

    def complete_session(self, reason: str = "Validation session completed."):
        if self._state not in (ValidationLifecycleState.RUNNING, ValidationLifecycleState.DEGRADED):
            raise ValidationLifecycleError("only a running validation session can be completed")
        self._state = ValidationLifecycleState.COMPLETED
        self._ended_at = self._now()
        self._final_summary = str(reason).strip() or "Validation session completed."
        report = build_report(self.snapshot(), ended_at=self._ended_at)
        report = self._persist_final_report(report, self._ended_at)
        self._last_report = report
        self._data = self.snapshot()
        self._publish(VALIDATION_SESSION_COMPLETED, report)
        return report

    def fail_session(self, reason: str):
        if self._state in (ValidationLifecycleState.IDLE, ValidationLifecycleState.COMPLETED):
            raise ValidationLifecycleError("validation session is not active")
        self._state = ValidationLifecycleState.FAILED
        self._ended_at = self._now()
        self._failure_reason = str(reason).strip() or "Validation session failed."
        self._add_finding(ValidationSeverity.CRITICAL, ValidationComponent.EVENT_FLOW, "SESSION_FAILED", self._failure_reason)
        report = build_report(self.snapshot(), ended_at=self._ended_at)
        report = self._persist_final_report(report, self._ended_at)
        self._last_report = report
        self._publish(VALIDATION_SESSION_FAILED, report)
        return report

    def snapshot(self) -> ValidationSessionSnapshot:
        findings = tuple(self._findings[key] for key in self._finding_order if key in self._findings and self._findings[key].resolution is FindingResolution.ACTIVE)
        component_freshness = self._freshness_tuple(findings)
        summaries = tuple(self._instrument_summary(instrument, findings) for instrument in self._session_instruments)
        health = self._overall_health(findings, component_freshness)
        return ValidationSessionSnapshot(
            session_id=self._session_id,
            mode=self._mode,
            lifecycle_state=self._state,
            started_at=self._started_at,
            ended_at=self._ended_at,
            instruments=self._session_instruments,
            expected_market_session=self._expected_session_text(),
            counters=self._counters,
            active_findings=findings,
            component_freshness=component_freshness,
            instrument_summaries=summaries,
            reconnect_summary=self._reconnect,
            latency_summaries=tuple(self._latency_summary(name, samples) for name, samples in sorted(self._latency_samples.items())),
            final_summary=self._final_summary,
            failure_reason=self._failure_reason,
            overall_health=health,
        )

    def latest_report(self):
        return self._last_report

    def active_findings(self) -> tuple[ValidationFinding, ...]:
        return self.snapshot().active_findings

    def reset(self, *, clear_persistent_data: bool = False) -> None:
        self._state = ValidationLifecycleState.IDLE
        self._mode = ValidationMode.OFF
        self._session_id = "-"
        self._started_at = None
        self._ended_at = None
        self._failure_reason = None
        self._final_summary = "-"
        self._last_report = None
        self._reset_transient(self._configuration.instruments)
        self._repository.reset(clear_persistent_data=clear_persistent_data)
        self._data = self.snapshot()

    def observe_tick(self, tick: Tick) -> ValidationSessionSnapshot:
        if not self._active():
            return self.snapshot()
        try:
            instrument = self._runtime_instrument(getattr(tick, "symbol", None))
        except Exception:
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.MARKET_DATA, "UNSUPPORTED_INSTRUMENT", "Unsupported market-data instrument.", getattr(tick, "symbol", None))
            return self.snapshot()
        if not self._session_instrument_allowed(instrument, ValidationComponent.MARKET_DATA, getattr(tick, "symbol", None)):
            return self.snapshot()
        metrics = self._tick_metrics[instrument]
        timestamp = getattr(tick, "timestamp", None)
        price = getattr(tick, "last_price", None)
        identity = ("tick", instrument.value, timestamp, price, getattr(tick, "volume", None), getattr(tick, "bid_price", None), getattr(tick, "ask_price", None))
        duplicate = identity in self._recent_ticks[instrument]
        if duplicate:
            metrics = replace(metrics, duplicate_ticks=metrics.duplicate_ticks + 1)
            self._add_finding(ValidationSeverity.WARNING, ValidationComponent.MARKET_DATA, "DUPLICATE_TICK", "Duplicate tick identity observed.", instrument)
        else:
            self._recent_ticks[instrument].append(identity)
        valid = True
        if not _aware(timestamp) or isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(float(price)) or float(price) <= 0:
            valid = False
            metrics = replace(metrics, invalid_ticks=metrics.invalid_ticks + 1)
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.MARKET_DATA, "INVALID_TICK", "Tick has invalid timestamp or price.", instrument)
        latest = metrics.latest_tick_timestamp
        if valid and latest is not None:
            gap = (timestamp - latest).total_seconds()
            if gap < 0:
                metrics = replace(metrics, out_of_order_ticks=metrics.out_of_order_ticks + 1)
                self._add_finding(ValidationSeverity.ERROR, ValidationComponent.MARKET_DATA, "OUT_OF_ORDER_TICK", "Tick timestamp moved backward.", instrument)
            else:
                severity = None
                if gap >= self._configuration.tick_gap_critical_seconds:
                    severity = ValidationSeverity.ERROR
                elif gap >= self._configuration.tick_gap_warning_seconds:
                    severity = ValidationSeverity.WARNING
                if severity is not None:
                    self._add_finding(severity, ValidationComponent.MARKET_DATA, "TICK_GAP", "Unusually large tick gap.", instrument, observed_value=str(gap))
                metrics = replace(metrics, current_gap_seconds=gap, largest_gap_seconds=max(metrics.largest_gap_seconds, gap))
        if valid:
            now = self._now()
            age = max((now - timestamp.astimezone(now.tzinfo)).total_seconds(), 0.0)
            if age >= self._configuration.tick_stale_after_seconds:
                metrics = replace(metrics, stale_ticks=metrics.stale_ticks + 1)
                self._add_finding(ValidationSeverity.WARNING, ValidationComponent.MARKET_DATA, "STALE_TICK", "Tick is stale.", instrument, observed_value=str(age))
            if not self._in_session(timestamp):
                self._add_finding(ValidationSeverity.WARNING, ValidationComponent.MARKET_DATA, "OUTSIDE_SESSION_TICK", "Tick arrived outside configured session.", instrument)
            if timestamp.astimezone(IST).date() != now.astimezone(IST).date():
                self._add_finding(ValidationSeverity.ERROR, ValidationComponent.MARKET_DATA, "WRONG_TRADING_DATE", "Tick trading date does not match validator date.", instrument)
            metrics = replace(
                metrics,
                received_ticks=metrics.received_ticks + 1,
                valid_ticks=metrics.valid_ticks + 1,
                first_tick_timestamp=metrics.first_tick_timestamp or timestamp,
                latest_tick_timestamp=timestamp if latest is None or timestamp >= latest else latest,
                last_tick_age_seconds=age,
                last_price=float(price),
            )
            self._observe_component(ValidationComponent.MARKET_DATA, instrument, timestamp)
            if self._reconnect.recovery_state is RecoveryState.RECOVERING:
                self._reconnect = replace(self._reconnect, recovery_state=RecoveryState.RECOVERED)
        else:
            metrics = replace(metrics, received_ticks=metrics.received_ticks + 1)
        self._tick_metrics[instrument] = metrics
        self._data = self.snapshot()
        return self._data

    def observe_candle(self, candle: Candle, *, closed: bool = False) -> ValidationSessionSnapshot:
        if not self._active():
            return self.snapshot()
        instrument = self._safe_runtime_instrument(getattr(candle, "symbol", None))
        if instrument is None:
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.CANDLE, "UNSUPPORTED_CANDLE_INSTRUMENT", "Unsupported candle instrument.", observed_value=getattr(candle, "symbol", None))
            return self.snapshot()
        if not self._session_instrument_allowed(instrument, ValidationComponent.CANDLE, getattr(candle, "symbol", None)):
            return self.snapshot()
        timeframe = self._candle_timeframe(getattr(candle, "timeframe", None))
        expected_duration = timeframe.duration.total_seconds() if timeframe is not None else None
        metrics = self._candle_metrics[instrument]
        if closed:
            metrics = replace(metrics, closed_candles=metrics.closed_candles + 1)
        else:
            metrics = replace(metrics, updated_candles=metrics.updated_candles + 1)
        identity = (candle.symbol, timeframe.value if timeframe else getattr(candle, "timeframe", None), candle.start_time, candle.end_time, closed)
        if closed and identity in self._recent_candles[instrument]:
            metrics = replace(metrics, duplicate_closed_candles=metrics.duplicate_closed_candles + 1)
            self._add_finding(ValidationSeverity.WARNING, ValidationComponent.CANDLE, "DUPLICATE_CANDLE_CLOSE", "Duplicate closed candle observed.", instrument)
        self._recent_candles[instrument].append(identity)
        invalid = (
            not _aware(candle.start_time)
            or not _aware(candle.end_time)
            or candle.start_time >= candle.end_time
            or timeframe is None
            or min(candle.open, candle.high, candle.low, candle.close) <= 0
            or candle.volume < 0
            or candle.high < candle.low
            or candle.high < candle.open
            or candle.high < candle.close
            or candle.low > candle.open
            or candle.low > candle.close
        )
        if invalid:
            metrics = replace(metrics, invalid_ohlc_candles=metrics.invalid_ohlc_candles + 1)
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.CANDLE, "INVALID_CANDLE", "Candle violates OHLC or timing invariants.", instrument)
        if _aware(candle.start_time) and _aware(candle.end_time):
            duration = (candle.end_time - candle.start_time).total_seconds()
            if expected_duration is None or duration != expected_duration:
                metrics = replace(metrics, late_closes=metrics.late_closes + 1)
                self._add_finding(ValidationSeverity.WARNING, ValidationComponent.CANDLE, "UNEXPECTED_CANDLE_DURATION", "Candle duration does not match timeframe.", instrument)
            candle_key = (instrument, timeframe) if timeframe is not None else (instrument, getattr(candle, "timeframe", None))
            previous = self._last_candle_end.get(candle_key)
            if previous is not None:
                gap = (candle.start_time - previous).total_seconds()
                if gap < 0:
                    metrics = replace(metrics, out_of_order_candles=metrics.out_of_order_candles + 1)
                    self._add_finding(ValidationSeverity.ERROR, ValidationComponent.CANDLE, "OUT_OF_ORDER_CANDLE", "Candle order moved backward.", instrument)
                elif expected_duration is not None and gap > expected_duration:
                    metrics = replace(metrics, missing_intervals=metrics.missing_intervals + int(gap // expected_duration) - 1)
                    self._add_finding(ValidationSeverity.WARNING, ValidationComponent.CANDLE, "MISSING_CANDLE_INTERVAL", "Missing candle interval detected.", instrument)
            self._last_candle_end[candle_key] = candle.end_time
            if candle.start_time.astimezone(IST).date() != self._now().astimezone(IST).date():
                self._add_finding(ValidationSeverity.ERROR, ValidationComponent.CANDLE, "CANDLE_TRADING_DATE_MISMATCH", "Candle trading date does not match validator date.", instrument)
            self._observe_component(ValidationComponent.CANDLE, instrument, candle.end_time)
        self._candle_metrics[instrument] = metrics
        self._data = self.snapshot()
        return self._data

    def observe_cpr(self, levels) -> None:
        if not self._active() or levels is None:
            return
        if levels.bc > levels.tc or levels.width < 0 or not _finite_positive_or_zero(levels.pivot):
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.CPR, "INVALID_CPR", "CPR invariant failed.")
        self._observe_component(ValidationComponent.CPR, None, self._now())

    def observe_camarilla(self, levels) -> None:
        if not self._active() or levels is None:
            return
        valid = levels.h6 >= levels.h5 >= levels.h4 >= levels.h3 and levels.h3 > levels.l3 and levels.l3 >= levels.l4 >= levels.l5 >= levels.l6
        values = (levels.h6, levels.h5, levels.h4, levels.h3, levels.l3, levels.l4, levels.l5, levels.l6)
        if not valid or any(not _finite_positive_or_zero(value) for value in values):
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.CAMARILLA, "INVALID_CAMARILLA", "Camarilla invariant failed.")
        self._observe_component(ValidationComponent.CAMARILLA, None, self._now())

    def observe_vwap(self, levels) -> None:
        if not self._active() or levels is None:
            return
        instrument = self._safe_runtime_instrument(getattr(levels, "symbol", None))
        if instrument is None:
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.VWAP, "UNSUPPORTED_VWAP_INSTRUMENT", "Unsupported VWAP instrument.", observed_value=getattr(levels, "symbol", None))
            return
        if not self._session_instrument_allowed(instrument, ValidationComponent.VWAP, getattr(levels, "symbol", None)):
            return
        if not _finite_positive_or_zero(getattr(levels, "vwap", None)) or getattr(levels, "vwap", 0) <= 0:
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.VWAP, "INVALID_VWAP", "VWAP must be finite and positive.", instrument)
        self._observe_component(ValidationComponent.VWAP, instrument, getattr(levels, "timestamp", self._now()))

    def observe_option_chain(self, state) -> OptionSnapshotQuality:
        if not self._active() or state is None:
            return OptionSnapshotQuality.UNAVAILABLE
        instrument = self._safe_runtime_instrument(getattr(state, "symbol", None))
        if instrument is None:
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.OPTION_CHAIN, "UNSUPPORTED_OPTION_CHAIN_INSTRUMENT", "Unsupported option-chain instrument.", observed_value=getattr(state, "symbol", None))
            return OptionSnapshotQuality.UNAVAILABLE
        if not self._session_instrument_allowed(instrument, ValidationComponent.OPTION_CHAIN, getattr(state, "symbol", None)):
            return OptionSnapshotQuality.UNAVAILABLE
        metrics = self._option_metrics[instrument]
        strikes = tuple(getattr(state, "strikes", ()) or ())
        strike_values = tuple(getattr(strike, "strike_price", None) for strike in strikes)
        has_duplicate = len(set(strike_values)) != len(strike_values)
        has_missing_side = any(getattr(strike, "call", None) is None or getattr(strike, "put", None) is None for strike in strikes)
        invalid = not strikes or tuple(sorted(strike_values)) != strike_values or has_duplicate
        for strike in strikes:
            for leg in (getattr(strike, "call", None), getattr(strike, "put", None)):
                if leg is None:
                    continue
                if getattr(leg, "open_interest", 0) < 0 or getattr(leg, "volume", 0) < 0:
                    invalid = True
                bid = getattr(leg, "bid_price", None)
                ask = getattr(leg, "ask_price", None)
                if bid is not None and ask is not None and bid > ask:
                    invalid = True
        age = max((self._now() - state.timestamp.astimezone(IST)).total_seconds(), 0.0) if _aware(getattr(state, "timestamp", None)) else 0.0
        if invalid:
            quality = OptionSnapshotQuality.INVALID
            metrics = replace(metrics, invalid_snapshots=metrics.invalid_snapshots + 1)
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.OPTION_CHAIN, "INVALID_OPTION_CHAIN", "Option-chain snapshot failed domain checks.", instrument)
        elif age >= self._configuration.option_chain_stale_seconds:
            quality = OptionSnapshotQuality.STALE
            metrics = replace(metrics, stale_snapshots=metrics.stale_snapshots + 1)
            self._add_finding(ValidationSeverity.WARNING, ValidationComponent.OPTION_CHAIN, "STALE_OPTION_CHAIN", "Option-chain snapshot is stale.", instrument)
        elif has_missing_side:
            quality = OptionSnapshotQuality.PARTIAL
            metrics = replace(metrics, partial_snapshots=metrics.partial_snapshots + 1)
        else:
            quality = OptionSnapshotQuality.COMPLETE
            metrics = replace(metrics, complete_snapshots=metrics.complete_snapshots + 1)
        identity = (instrument.value, getattr(state, "expiry_date", None), getattr(state, "timestamp", None), strike_values)
        if self._last_option_identity.get(instrument) == identity:
            metrics = replace(metrics, duplicate_snapshots=metrics.duplicate_snapshots + 1)
        previous_expiry = self._last_option_expiry.get(instrument)
        if previous_expiry is not None and previous_expiry != getattr(state, "expiry_date", None):
            self._add_finding(ValidationSeverity.INFO, ValidationComponent.OPTION_CHAIN, "OPTION_EXPIRY_TRANSITION", "Option-chain expiry transitioned.", instrument)
        self._last_option_identity[instrument] = identity
        self._last_option_expiry[instrument] = getattr(state, "expiry_date", None)
        metrics = replace(metrics, snapshots_received=metrics.snapshots_received + 1, latest_snapshot_age_seconds=age, quality=quality)
        self._option_metrics[instrument] = metrics
        self._observe_component(ValidationComponent.OPTION_CHAIN, instrument, getattr(state, "timestamp", self._now()))
        self._data = self.snapshot()
        return quality

    def record_event(self, event_name: str, payload=None, *, timestamp: datetime | None = None) -> ValidationSessionSnapshot:
        if event_name in _VALIDATION_EVENTS:
            return self.snapshot()
        if not self._active():
            return self.snapshot()
        observed_at = timestamp or self._event_timestamp(payload) or self._now()
        identity = (event_name, self._payload_identity(payload), observed_at)
        duplicate = identity in self._recent_events
        self._recent_events.append(identity)
        self._counters = replace(
            self._counters,
            observed_events=self._counters.observed_events + 1,
            duplicate_events=self._counters.duplicate_events + (1 if duplicate else 0),
        )
        if duplicate:
            self._add_finding(ValidationSeverity.WARNING, ValidationComponent.EVENT_FLOW, "DUPLICATE_EVENT", "Duplicate event identity observed.")
        component = _EVENT_COMPONENTS.get(event_name)
        if component is not None:
            instrument = self._payload_instrument(payload, component)
            if instrument is not _INVALID_INSTRUMENT:
                self._observe_component(component, instrument, observed_at)
        if event_name in (CANDLE_UPDATED, CANDLE_OPENED) and isinstance(payload, Candle):
            self.observe_candle(payload, closed=False)
        elif event_name == CANDLE_CLOSED and isinstance(payload, Candle):
            self.observe_candle(payload, closed=True)
        elif event_name in (NEW_TICK, MARKET_UPDATED) and isinstance(payload, Tick):
            self.observe_tick(payload)
        elif event_name in (OPTION_CHAIN_UPDATED, OPTION_CHAIN_READY):
            self.observe_option_chain(payload)
        elif event_name == CPR_UPDATED:
            self.observe_cpr(payload)
        elif event_name == CAMARILLA_UPDATED:
            self.observe_camarilla(payload)
        elif event_name == VWAP_UPDATED:
            self.observe_vwap(payload)
        if event_name in (PAPER_TRADE_RECORDED,):
            self._correlations["paper_trade"] = self._monotonic()
        elif event_name in (PERFORMANCE_ANALYTICS_UPDATED, TRADE_PERFORMANCE_ANALYTICS_UPDATED):
            self._record_latency("paper_trade_completion_to_analytics_update", self._correlations.pop("paper_trade", None))
        self._data = self.snapshot()
        return self._data

    def record_disconnect(self, timestamp: datetime | None = None) -> None:
        value = timestamp or self._now()
        self._active_outage_started = value
        self._reconnect = replace(self._reconnect, recovery_state=RecoveryState.DISCONNECTED, disconnect_count=self._reconnect.disconnect_count + 1, last_disconnect_at=value)
        self._add_finding(ValidationSeverity.WARNING, ValidationComponent.RECONNECT, "FEED_DISCONNECTED", "Market feed disconnected.")

    def record_reconnect(self, timestamp: datetime | None = None) -> None:
        value = timestamp or self._now()
        outage = 0.0
        if self._active_outage_started is not None:
            outage = max((value - self._active_outage_started).total_seconds(), 0.0)
        self._reconnect = replace(
            self._reconnect,
            recovery_state=RecoveryState.RECOVERING,
            reconnect_count=self._reconnect.reconnect_count + 1,
            total_outage_seconds=self._reconnect.total_outage_seconds + outage,
            longest_outage_seconds=max(self._reconnect.longest_outage_seconds, outage),
            last_reconnect_at=value,
        )

    def _subscribe_once(self) -> None:
        if self._subscribed:
            return
        for event_name in _EVENT_COMPONENTS:
            self._event_bus.subscribe(event_name, lambda payload, name=event_name: self.record_event(name, payload))
        self._subscribed = True

    def _active(self) -> bool:
        return self._state in (ValidationLifecycleState.RUNNING, ValidationLifecycleState.DEGRADED)

    def _reset_transient(self, instruments) -> None:
        self._session_instruments = tuple(instruments)
        self._findings = {}
        self._finding_order = deque(maxlen=self._configuration.max_findings)
        self._recent_events = deque(maxlen=self._configuration.max_recent_identities)
        self._recent_ticks = {instrument: deque(maxlen=self._configuration.max_recent_identities) for instrument in instruments}
        self._recent_candles = {instrument: deque(maxlen=self._configuration.max_recent_identities) for instrument in instruments}
        self._last_candle_end = {}
        self._last_option_identity = {}
        self._last_option_expiry = {}
        self._tick_metrics = {instrument: TickValidationMetrics() for instrument in instruments}
        self._candle_metrics = {instrument: CandleValidationMetrics() for instrument in instruments}
        self._option_metrics = {instrument: OptionChainValidationMetrics() for instrument in instruments}
        self._component_freshness = {}
        self._counters = ValidationCounters()
        self._latency_samples = {}
        self._correlations = {}
        self._reconnect = ReconnectSummary()
        self._active_outage_started = None

    def _add_finding(self, severity, component, code, message, instrument=None, *, observed_value=None, expected_value=None) -> ValidationFinding:
        if instrument is not None and not isinstance(instrument, RuntimeInstrument):
            try:
                instrument = RuntimeInstrument(str(getattr(instrument, "value", instrument)).strip().upper())
            except Exception:
                instrument = None
        key = (component, instrument, code, str(expected_value))
        now = self._now()
        if key in self._findings:
            finding = self._findings[key].aggregate(now, str(observed_value) if observed_value is not None else None)
        else:
            finding = ValidationFinding(
                finding_id=f"{self._session_id}-{next(self._counter)}",
                session_id=self._session_id,
                timestamp=now,
                severity=severity,
                category=component.value,
                component=component,
                code=code,
                message=message,
                instrument=instrument,
                observed_value=str(observed_value) if observed_value is not None else None,
                expected_value=str(expected_value) if expected_value is not None else None,
            )
            if len(self._finding_order) == self._finding_order.maxlen and self._finding_order:
                self._findings.pop(self._finding_order[0], None)
            self._finding_order.append(key)
        self._findings[key] = finding
        if severity in (ValidationSeverity.WARNING, ValidationSeverity.ERROR, ValidationSeverity.CRITICAL) and self._state is ValidationLifecycleState.RUNNING:
            self._state = ValidationLifecycleState.DEGRADED
        self._publish(VALIDATION_FINDING, finding)
        return finding

    def _observe_component(self, component, instrument, source_at) -> None:
        if instrument is not None and instrument not in self._session_instruments:
            return
        key = (component, instrument)
        now = self._now()
        age = max((now - source_at.astimezone(now.tzinfo)).total_seconds(), 0.0) if _aware(source_at) else None
        status = ComponentStatus.HEALTHY
        if age is not None and age >= self._configuration.component_stale_seconds:
            status = ComponentStatus.STALE
        existing = self._component_freshness.get(key)
        self._component_freshness[key] = ComponentFreshness(
            component=component,
            instrument=instrument,
            latest_observed_at=now,
            latest_source_at=source_at if _aware(source_at) else now,
            age_seconds=age,
            status=status,
            observations=(existing.observations if existing else 0) + 1,
        )

    def _freshness_tuple(self, findings) -> tuple[ComponentFreshness, ...]:
        items = []
        for component in ValidationComponent:
            if component in (ValidationComponent.EVENT_FLOW, ValidationComponent.RECONNECT, ValidationComponent.PERSISTENCE):
                continue
            for instrument in self._session_instruments:
                key = (component, instrument)
                item = self._component_freshness.get(key)
                if item is None:
                    status = ComponentStatus.NOT_OBSERVED if component in self._configuration.required_components else ComponentStatus.NOT_ENABLED
                    item = ComponentFreshness(component=component, instrument=instrument, status=status)
                items.append(item)
        return tuple(items)

    def _instrument_summary(self, instrument, findings) -> InstrumentValidationSummary:
        active = tuple(item for item in findings if item.instrument is instrument)
        return InstrumentValidationSummary(
            instrument=instrument,
            health=health_for_findings(active) if active else ValidationHealth.HEALTHY if self._tick_metrics[instrument].valid_ticks else ValidationHealth.UNKNOWN,
            tick_metrics=self._tick_metrics[instrument],
            candle_metrics=self._candle_metrics[instrument],
            option_chain_metrics=self._option_metrics[instrument],
            active_findings=len(active),
        )

    def _overall_health(self, findings, freshness) -> ValidationHealth:
        if self._state is ValidationLifecycleState.FAILED:
            return ValidationHealth.FAILED
        health = health_for_findings(findings)
        if health is not ValidationHealth.HEALTHY:
            return health
        if any(item.status in (ComponentStatus.STALE, ComponentStatus.INVALID, ComponentStatus.FAILED) for item in freshness):
            return ValidationHealth.DEGRADED
        if any(summary.valid_ticks for summary in self._tick_metrics.values()):
            return ValidationHealth.HEALTHY
        return ValidationHealth.UNKNOWN

    def _latency_summary(self, name, samples) -> LatencySummary:
        values = tuple(sorted(samples))
        if not values:
            return LatencySummary(name)
        total = sum(values)
        return LatencySummary(
            name=name,
            count=len(values),
            latest_ms=samples[-1],
            minimum_ms=values[0],
            maximum_ms=values[-1],
            average_ms=total / len(values),
            p50_ms=_percentile(values, 0.50),
            p95_ms=_percentile(values, 0.95),
        )

    def _persist_final_report(self, report, ended_at):
        try:
            self._repository.write_findings(report.findings)
            if report.findings:
                self._counters = replace(self._counters, persistence_writes=self._counters.persistence_writes + 1)
        except Exception as exc:
            self._counters = replace(self._counters, persistence_failures=self._counters.persistence_failures + 1)
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.PERSISTENCE, "FINDINGS_WRITE_FAILED", str(exc))
            report = build_report(self.snapshot(), ended_at=ended_at)
        try:
            path = self._repository.write_report(report)
            self._counters = replace(self._counters, persistence_writes=self._counters.persistence_writes + 1)
            return replace(report, report_path=path, counters=self._counters)
        except Exception as exc:
            self._counters = replace(self._counters, persistence_failures=self._counters.persistence_failures + 1)
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.PERSISTENCE, "REPORT_WRITE_FAILED", str(exc))
            return build_report(self.snapshot(), ended_at=ended_at)

    def _record_latency(self, name: str, started: float | None) -> None:
        if started is None:
            return
        elapsed = max((self._monotonic() - started) * 1000.0, 0.0)
        samples = self._latency_samples.setdefault(name, deque(maxlen=self._configuration.max_latency_samples))
        samples.append(elapsed)
        if elapsed >= self._configuration.event_latency_critical_ms:
            self._add_finding(ValidationSeverity.ERROR, ValidationComponent.EVENT_FLOW, "LATENCY_CRITICAL", "Latency exceeded critical threshold.", observed_value=elapsed)
        elif elapsed >= self._configuration.event_latency_warning_ms:
            self._add_finding(ValidationSeverity.WARNING, ValidationComponent.EVENT_FLOW, "LATENCY_WARNING", "Latency exceeded warning threshold.", observed_value=elapsed)

    def _normalize_mode(self, mode) -> ValidationMode:
        return mode if isinstance(mode, ValidationMode) else ValidationMode(str(mode).strip().lower())

    def _normalize_instruments(self, instruments) -> tuple[RuntimeInstrument, ...]:
        result = []
        for instrument in tuple(instruments):
            item = instrument if isinstance(instrument, RuntimeInstrument) else RuntimeInstrument(str(instrument).strip().upper())
            if item not in self._configuration.instruments:
                raise ValueError("validation session instrument is not configured")
            if item not in result:
                result.append(item)
        return tuple(result)

    def _payload_identity(self, payload) -> str:
        return str((payload.__class__.__name__, getattr(payload, "symbol", None), getattr(payload, "timestamp", None), getattr(payload, "updated_at", None)))

    def _payload_instrument(self, payload, component):
        if payload is None or not hasattr(payload, "symbol"):
            return None
        instrument = self._safe_runtime_instrument(getattr(payload, "symbol", None))
        if instrument is None:
            self._add_finding(ValidationSeverity.ERROR, component, "UNSUPPORTED_EVENT_INSTRUMENT", "Unsupported event payload instrument.", observed_value=getattr(payload, "symbol", None))
            return _INVALID_INSTRUMENT
        if not self._session_instrument_allowed(instrument, component, getattr(payload, "symbol", None)):
            return _INVALID_INSTRUMENT
        return instrument

    def _runtime_instrument(self, value):
        if isinstance(value, RuntimeInstrument):
            return value
        if isinstance(value, Instrument):
            return RuntimeInstrument(value.value)
        return RuntimeInstrument(str(getattr(value, "value", value)).strip().upper())

    def _safe_runtime_instrument(self, value):
        try:
            return self._runtime_instrument(value)
        except Exception:
            return None

    def _session_instrument_allowed(self, instrument, component, observed_value) -> bool:
        if instrument not in self._configuration.instruments:
            self._add_finding(ValidationSeverity.ERROR, component, "UNSUPPORTED_INSTRUMENT", "Unsupported validation instrument.", observed_value=observed_value)
            return False
        if instrument not in self._session_instruments:
            self._add_finding(ValidationSeverity.ERROR, component, "UNSUPPORTED_SESSION_INSTRUMENT", "Instrument is not active in this validation session.", instrument, observed_value=observed_value)
            return False
        return True

    def _candle_timeframe(self, value) -> TimeFrame | None:
        if isinstance(value, TimeFrame):
            timeframe = value
        else:
            try:
                timeframe = TimeFrame.from_value(str(value))
            except Exception:
                return None
        try:
            timeframe.duration
        except ValueError:
            return None
        return timeframe

    def _event_timestamp(self, payload):
        for name in ("timestamp", "updated_at", "closed_at", "exit_time"):
            value = getattr(payload, name, None)
            if _aware(value):
                return value
        return None

    def _in_session(self, value: datetime) -> bool:
        if not _aware(value):
            return False
        local = value.astimezone(IST)
        if local.weekday() >= 5:
            return False
        return self._configuration.session_start <= local.time() <= self._configuration.session_end

    def _expected_session_text(self) -> str:
        return f"{self._configuration.session_start.strftime('%H:%M')}-{self._configuration.session_end.strftime('%H:%M')} Asia/Kolkata"

    def _publish(self, event_name: str, payload) -> None:
        try:
            self._event_bus.publish(event_name, payload)
        except Exception:
            self._counters = replace(self._counters, handler_failures=self._counters.handler_failures + 1)
            raise

    def _now(self) -> datetime:
        value = self._clock()
        if not _aware(value):
            raise ValueError("validation clock must return timezone-aware datetime")
        return value.astimezone(IST)

    def _monotonic(self) -> float:
        value = self._monotonic_clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("monotonic clock must return a finite number")
        return float(value)


def _aware(value) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _finite_positive_or_zero(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) >= 0


def _percentile(values: tuple[float, ...], percentile: float) -> float:
    if not values:
        return 0.0
    index = int(math.ceil(percentile * len(values))) - 1
    return values[max(0, min(index, len(values) - 1))]
