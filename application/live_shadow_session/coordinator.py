"""
Application-level live shadow market session coordinator.
"""

from __future__ import annotations

from datetime import UTC, datetime

from adapters.zerodha.enums import ZerodhaConnectionState
from application.enums import RuntimeInstrument, RuntimeStatus
from core import events
from core.base_engine import BaseEngine
from core.enums.instrument import Instrument
from core.models.tick import Tick
from engines.shadow_trading_session.enums import ShadowSessionStatus
from engines.shadow_trading_session.models import ShadowTradingSessionRequest

from .enums import LiveShadowSessionState, LiveShadowSessionStatus
from .models import (
    LiveShadowInstrumentResult,
    LiveShadowSessionReport,
    LiveShadowSessionRequest,
    LiveShadowSessionSnapshot,
    normalize_instruments,
)


def _default_clock() -> datetime:
    return datetime.now(UTC)


class LiveShadowMarketSessionCoordinator(BaseEngine):
    def __init__(self, event_bus, *, orchestrator, clock=None):
        super().__init__(event_bus)
        self._orchestrator = orchestrator
        self._clock = clock or _default_clock
        self._state = LiveShadowSessionState.CREATED
        self._active_request: LiveShadowSessionRequest | None = None
        self._active_instruments: tuple[RuntimeInstrument, ...] = ()
        self._started_shadow: tuple[RuntimeInstrument, ...] = ()
        self._reports: dict[str, LiveShadowSessionReport] = {}
        self._last_report: LiveShadowSessionReport | None = None
        self._last_tick_at: datetime | None = None
        self._failure_code: str | None = None
        self._degraded = False
        self._completed_events: set[str] = set()
        self._seen_ticks: set[str] = set()
        self._instrument_market_ticks: dict[RuntimeInstrument, int] = {}
        self._instrument_accepted_ticks: dict[RuntimeInstrument, int] = {}
        self._instrument_rejected_ticks: dict[RuntimeInstrument, int] = {}
        self._instrument_observations: dict[RuntimeInstrument, int] = {}
        self._instrument_last_tick_at: dict[RuntimeInstrument, datetime] = {}

    def start(self) -> LiveShadowSessionSnapshot:
        if self._state is LiveShadowSessionState.CREATED:
            self._state = LiveShadowSessionState.READY
        self._publish_state()
        return self.snapshot()

    def start_session(self, request: LiveShadowSessionRequest) -> LiveShadowSessionSnapshot:
        if not isinstance(request, LiveShadowSessionRequest):
            raise TypeError("request must be LiveShadowSessionRequest")
        if self._state is LiveShadowSessionState.CREATED:
            self.start()
        if self._state in {
            LiveShadowSessionState.FAILED,
            LiveShadowSessionState.STOPPED,
            LiveShadowSessionState.COMPLETED,
        }:
            raise RuntimeError("reset live shadow coordinator before starting another session")
        if self._state is LiveShadowSessionState.RUNNING:
            if self._active_request is not None and self._active_request.fingerprint() == request.fingerprint():
                return self.snapshot()
            raise ValueError("a different live shadow session is already running")
        instruments = normalize_instruments(request.instruments)
        self._validate_configured(instruments)
        self._state = LiveShadowSessionState.STARTING
        self._failure_code = None
        self._publish_state()
        started: list[RuntimeInstrument] = []
        try:
            if self._orchestrator.status is not RuntimeStatus.RUNNING:
                self._orchestrator.start()
            zerodha = self._orchestrator.get_zerodha_connection_snapshot()
            if not zerodha.authenticated:
                raise RuntimeError("zerodha_not_authenticated")
            resolved = {RuntimeInstrument(token.instrument.value) for token in zerodha.resolved_tokens}
            if any(instrument not in resolved for instrument in instruments):
                raise RuntimeError("zerodha_tokens_not_resolved")
            if zerodha.state is not ZerodhaConnectionState.CONNECTED or not zerodha.connected:
                raise RuntimeError("zerodha_not_connected")
            for instrument in instruments:
                shadow_request = ShadowTradingSessionRequest(
                    session_id=f"{request.session_id}:{instrument.value}",
                    started_at=request.started_at,
                    instrument=instrument.value,
                    correlation_id=request.correlation_id,
                    metadata=request.metadata + (("live_shadow_session_id", request.session_id),),
                )
                self._orchestrator.start_shadow_session(instrument, shadow_request)
                started.append(instrument)
            self._orchestrator.subscribe_zerodha_instruments(tuple(instrument.value for instrument in instruments))
            self._active_request = request
            self._active_instruments = instruments
            self._started_shadow = tuple(started)
            self._reset_counters(instruments)
            self._state = LiveShadowSessionState.RUNNING
            self._event_bus.publish(events.LIVE_SHADOW_SESSION_STARTED, self.snapshot())
            self._publish_state()
            return self.snapshot()
        except Exception as exc:
            self._cleanup_started_shadow(tuple(started), request.started_at)
            self._active_request = None
            self._active_instruments = ()
            self._started_shadow = ()
            self._fail(_safe_error(exc))
            return self.snapshot()

    def observe_tick(self, tick: Tick, *, accepted: bool) -> LiveShadowSessionSnapshot:
        if self._state in {
            LiveShadowSessionState.FAILED,
            LiveShadowSessionState.STOPPED,
            LiveShadowSessionState.COMPLETED,
        }:
            return self.snapshot()
        if self._state is not LiveShadowSessionState.RUNNING:
            return self.snapshot()
        if not isinstance(tick, Tick):
            raise TypeError("tick must be Tick")
        instrument = RuntimeInstrument(tick.symbol.value)
        if instrument not in self._active_instruments:
            return self.snapshot()
        identity = _tick_identity(tick)
        if identity in self._seen_ticks:
            return self.snapshot()
        self._seen_ticks.add(identity)
        self._instrument_market_ticks[instrument] += 1
        if accepted:
            self._instrument_accepted_ticks[instrument] += 1
            self._orchestrator.observe_shadow_event(
                instrument,
                events.NEW_TICK,
                tick,
                timestamp=tick.timestamp,
            )
            self._instrument_observations[instrument] += 1
            self._event_bus.publish(events.LIVE_SHADOW_TICK_OBSERVED, self.snapshot())
        else:
            self._instrument_rejected_ticks[instrument] += 1
            self._event_bus.publish(events.LIVE_SHADOW_SESSION_WARNING, self.snapshot())
        self._last_tick_at = tick.timestamp
        self._instrument_last_tick_at[instrument] = tick.timestamp
        self._publish_state()
        return self.snapshot()

    def observe_zerodha_state(self) -> LiveShadowSessionSnapshot:
        zerodha = self._orchestrator.get_zerodha_connection_snapshot()
        if self._state is not LiveShadowSessionState.RUNNING:
            return self.snapshot()
        if zerodha.state is ZerodhaConnectionState.CONNECTED and zerodha.connected:
            return self.snapshot()
        if zerodha.state is ZerodhaConnectionState.DISCONNECTED:
            self._degraded = True
            self._event_bus.publish(events.LIVE_SHADOW_SESSION_DEGRADED, self.snapshot())
            self._publish_state()
            return self.snapshot()
        if zerodha.state in {ZerodhaConnectionState.FAILED, ZerodhaConnectionState.STOPPED}:
            self._fail(f"zerodha_{zerodha.state.value}")
        return self.snapshot()

    def stop_session(
        self,
        *,
        timestamp: datetime,
        reason: str = "session_completed",
    ) -> LiveShadowSessionReport:
        timestamp = _aware(timestamp, "timestamp")
        reason = _text(reason, "reason")
        if self._last_report is not None and self._state in {
            LiveShadowSessionState.COMPLETED,
            LiveShadowSessionState.FAILED,
        }:
            return self._last_report
        if self._active_request is None:
            if self._last_report is not None:
                return self._last_report
            raise RuntimeError("no active live shadow session")
        final_failed = self._state is LiveShadowSessionState.FAILED
        if not final_failed:
            self._state = LiveShadowSessionState.STOPPING
            self._publish_state()
        summaries = []
        for instrument in self._active_instruments:
            summary = self._orchestrator.stop_shadow_session(instrument, timestamp=timestamp, reason=reason)
            summaries.append((instrument, summary))
        zerodha = self._orchestrator.get_zerodha_connection_snapshot()
        if zerodha.state is ZerodhaConnectionState.CONNECTED:
            self._orchestrator.disconnect_zerodha_market_data()
            zerodha = self._orchestrator.get_zerodha_connection_snapshot()
        report = self._build_report(timestamp, reason, tuple(summaries), zerodha, final_failed=final_failed)
        self._reports[report.session_id] = report
        self._last_report = report
        self._active_request = None
        self._active_instruments = ()
        self._started_shadow = ()
        self._data = report
        if final_failed:
            self._state = LiveShadowSessionState.FAILED
        else:
            self._state = LiveShadowSessionState.COMPLETED
        if report.session_id not in self._completed_events:
            self._completed_events.add(report.session_id)
            self._event_bus.publish(events.LIVE_SHADOW_SESSION_COMPLETED, report)
            self._publish_state()
        return report

    def get_report(self, session_id: str) -> LiveShadowSessionReport | None:
        if not isinstance(session_id, str):
            return None
        return self._reports.get(session_id.strip())

    def snapshot(self) -> LiveShadowSessionSnapshot:
        return LiveShadowSessionSnapshot(
            enabled=True,
            state=self._state,
            active_session_id=None if self._active_request is None else self._active_request.session_id,
            active_instruments=self._active_instruments,
            started_at=None if self._active_request is None else self._active_request.started_at,
            last_tick_at=self._last_tick_at,
            market_tick_count=sum(self._instrument_market_ticks.values()),
            accepted_tick_count=sum(self._instrument_accepted_ticks.values()),
            rejected_tick_count=sum(self._instrument_rejected_ticks.values()),
            shadow_observation_count=sum(self._instrument_observations.values()),
            last_report=self._last_report,
            failure_code=self._failure_code,
            broker_order_calls=0,
            mutation_calls=0,
            live_order_submission_enabled=False,
        )

    def stop(self) -> LiveShadowSessionSnapshot:
        if self._state is LiveShadowSessionState.READY:
            self._state = LiveShadowSessionState.STOPPED
        elif self._state is LiveShadowSessionState.RUNNING:
            self.stop_session(timestamp=self._now(), reason="coordinator_stopped")
        self._publish_state()
        return self.snapshot()

    def reset(self) -> LiveShadowSessionSnapshot:
        if self._state in {
            LiveShadowSessionState.FAILED,
            LiveShadowSessionState.STOPPED,
            LiveShadowSessionState.COMPLETED,
        }:
            self._state = LiveShadowSessionState.READY
        self._active_request = None
        self._active_instruments = ()
        self._started_shadow = ()
        self._reports = {}
        self._last_report = None
        self._last_tick_at = None
        self._failure_code = None
        self._degraded = False
        self._completed_events = set()
        self._seen_ticks = set()
        self._instrument_market_ticks = {}
        self._instrument_accepted_ticks = {}
        self._instrument_rejected_ticks = {}
        self._instrument_observations = {}
        self._instrument_last_tick_at = {}
        self._data = None
        self._publish_state()
        return self.snapshot()

    def _build_report(self, ended_at, reason, summaries, zerodha, *, final_failed):
        request = self._active_request
        results = tuple(self._instrument_result(instrument, summary) for instrument, summary in summaries)
        status = self._classify(results, final_failed=final_failed)
        report_state = LiveShadowSessionState.FAILED if final_failed else LiveShadowSessionState.COMPLETED
        primary_reason = self._failure_code if final_failed and self._failure_code else reason
        return LiveShadowSessionReport(
            session_id=request.session_id,
            started_at=request.started_at,
            ended_at=ended_at,
            state=report_state,
            status=status,
            primary_reason=primary_reason,
            instruments=self._active_instruments,
            instrument_results=results,
            zerodha_state=zerodha.state,
            zerodha_authenticated=zerodha.authenticated,
            zerodha_connected=zerodha.connected,
            zerodha_received_tick_count=zerodha.received_tick_count,
            zerodha_published_tick_count=zerodha.published_tick_count,
            zerodha_rejected_tick_count=zerodha.rejected_tick_count,
            zerodha_duplicate_tick_count=zerodha.duplicate_tick_count,
            total_market_tick_count=sum(result.market_tick_count for result in results),
            total_accepted_tick_count=sum(result.accepted_tick_count for result in results),
            total_rejected_tick_count=sum(result.rejected_tick_count for result in results),
            total_shadow_observation_count=sum(result.shadow_observation_count for result in results),
            broker_order_calls=0,
            mutation_calls=0,
            live_order_submission_enabled=False,
            correlation_id=request.correlation_id,
        )

    def _instrument_result(self, instrument, summary) -> LiveShadowInstrumentResult:
        return LiveShadowInstrumentResult(
            instrument=instrument,
            shadow_session_id=summary.session_id,
            market_tick_count=self._instrument_market_ticks.get(instrument, 0),
            accepted_tick_count=self._instrument_accepted_ticks.get(instrument, 0),
            rejected_tick_count=self._instrument_rejected_ticks.get(instrument, 0),
            shadow_observation_count=self._instrument_observations.get(instrument, 0),
            shadow_status=summary.session_status.value,
            shadow_lifecycle=summary.lifecycle_state.value,
            shadow_summary=summary,
            last_tick_at=self._instrument_last_tick_at.get(instrument),
            primary_reason=summary.primary_reason,
        )

    def _classify(self, results, *, final_failed):
        if final_failed or self._state is LiveShadowSessionState.FAILED:
            return LiveShadowSessionStatus.FAILED
        statuses = tuple(result.shadow_summary.session_status for result in results)
        if any(status is ShadowSessionStatus.DEGRADED for status in statuses) or self._degraded:
            return LiveShadowSessionStatus.DEGRADED
        if statuses and all(status is ShadowSessionStatus.BLOCKED for status in statuses):
            return LiveShadowSessionStatus.BLOCKED
        if (
            any(status is ShadowSessionStatus.HEALTHY_WITH_WARNINGS for status in statuses)
            or any(value > 0 for value in self._instrument_rejected_ticks.values())
            or self._orchestrator.get_zerodha_connection_snapshot().duplicate_tick_count > 0
        ):
            return LiveShadowSessionStatus.HEALTHY_WITH_WARNINGS
        return LiveShadowSessionStatus.HEALTHY

    def _cleanup_started_shadow(self, instruments, timestamp) -> None:
        for instrument in instruments:
            try:
                self._orchestrator.stop_shadow_session(instrument, timestamp=timestamp, reason="startup_failed")
            except Exception:
                continue

    def _validate_configured(self, instruments) -> None:
        configured = set(self._orchestrator.configuration.instruments)
        for instrument in instruments:
            if instrument not in configured:
                raise ValueError("live shadow instrument is not configured in orchestrator")
            self._orchestrator.get_runtime(instrument)

    def _reset_counters(self, instruments) -> None:
        self._seen_ticks = set()
        self._degraded = False
        self._last_tick_at = None
        self._instrument_market_ticks = {instrument: 0 for instrument in instruments}
        self._instrument_accepted_ticks = {instrument: 0 for instrument in instruments}
        self._instrument_rejected_ticks = {instrument: 0 for instrument in instruments}
        self._instrument_observations = {instrument: 0 for instrument in instruments}
        self._instrument_last_tick_at = {}

    def _fail(self, code: str) -> None:
        self._state = LiveShadowSessionState.FAILED
        self._failure_code = _safe_text(code)
        self._event_bus.publish(events.LIVE_SHADOW_SESSION_FAILED, self.snapshot())
        self._publish_state()

    def _publish_state(self) -> None:
        snapshot = self.snapshot()
        self._data = snapshot
        self._event_bus.publish(events.LIVE_SHADOW_SESSION_STATE_UPDATED, snapshot)

    def _now(self) -> datetime:
        return _aware(self._clock(), "clock")


def _tick_identity(tick: Tick) -> str:
    return "|".join(
        (
            tick.symbol.value,
            tick.exchange.value,
            tick.timestamp.isoformat(),
            str(tick.last_price),
            str(tick.volume),
            str(tick.bid_price),
            str(tick.ask_price),
            str(tick.open_interest),
        )
    )


def _aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _safe_text(value: str) -> str:
    return _text(str(value).replace("{", "").replace("}", ""), "failure_code")[:160]


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    for token in ("api_key", "api_secret", "access_token", "request_token"):
        text = text.replace(token, "[REDACTED]")
    return _safe_text(text)
