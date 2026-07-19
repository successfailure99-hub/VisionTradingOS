from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from pathlib import Path

from application.enums import ExecutionSafetyMode
from brokers.zerodha.enums import BrokerExecutionMode
from engines.deterministic_backtest.enums import (
    BacktestLifecycleState,
    BacktestMode,
    BacktestOutcome,
    BacktestSeverity,
    ReproducibilityStatus,
)
from engines.historical_market_replay.enums import ReplayOutcome
from engines.performance_analytics.models import AnalyticsSnapshot, PerformanceSummary


BACKTEST_SCHEMA_VERSION = 1
DEFAULT_MAX_SESSIONS = 100
DEFAULT_MAX_FINDINGS = 500
DEFAULT_MAX_SESSION_RESULTS = 100


@dataclass(frozen=True, slots=True)
class BacktestConfiguration:
    enabled: bool = False
    mode: BacktestMode = BacktestMode.SINGLE_SESSION
    session_paths: tuple[Path | str, ...] = ()
    output_directory: Path | str = Path("logs/backtests")
    max_sessions: int = DEFAULT_MAX_SESSIONS
    max_findings: int = DEFAULT_MAX_FINDINGS
    max_session_results: int = DEFAULT_MAX_SESSION_RESULTS
    reproducibility_check_enabled: bool = False
    stop_on_session_failure: bool = True
    safety_mode: ExecutionSafetyMode = ExecutionSafetyMode.ANALYSIS_ONLY
    broker_mode: BrokerExecutionMode = BrokerExecutionMode.DRY_RUN

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be bool")
        if not isinstance(self.mode, BacktestMode):
            raise TypeError("mode must be BacktestMode")
        if type(self.reproducibility_check_enabled) is not bool:
            raise TypeError("reproducibility_check_enabled must be bool")
        if type(self.stop_on_session_failure) is not bool:
            raise TypeError("stop_on_session_failure must be bool")
        for name in ("max_sessions", "max_findings", "max_session_results"):
            _positive_int(getattr(self, name), name)
        if self.safety_mode is not ExecutionSafetyMode.ANALYSIS_ONLY:
            raise ValueError("deterministic backtest requires ANALYSIS_ONLY safety mode")
        if self.broker_mode is not BrokerExecutionMode.DRY_RUN:
            raise ValueError("deterministic backtest requires DRY_RUN broker mode")
        paths = tuple(Path(path).expanduser() for path in tuple(self.session_paths or ()))
        normalized = tuple(path if path.is_absolute() else Path.cwd() / path for path in paths)
        normalized = tuple(path.resolve(strict=False) for path in normalized)
        if len(set(normalized)) != len(normalized):
            raise ValueError("BACKTEST_SESSION_PATHS must not contain duplicates")
        output = Path(self.output_directory).expanduser()
        output = (output if output.is_absolute() else Path.cwd() / output).resolve(strict=False)
        if self.enabled:
            if not normalized:
                raise ValueError("enabled deterministic backtest requires at least one session path")
            if self.mode is BacktestMode.SINGLE_SESSION and len(normalized) != 1:
                raise ValueError("SINGLE_SESSION requires exactly one session path")
            if self.mode is BacktestMode.BATCH and len(normalized) > self.max_sessions:
                raise ValueError("BATCH session count exceeds max_sessions")
        for source in normalized:
            if output == source or output in source.parents:
                raise ValueError("BACKTEST_OUTPUT_DIRECTORY must not overlap source session files")
        object.__setattr__(self, "session_paths", normalized)
        object.__setattr__(self, "output_directory", output)


@dataclass(frozen=True, slots=True)
class BacktestFinding:
    finding_id: str
    timestamp: datetime
    severity: BacktestSeverity
    code: str
    message: str
    occurrence_count: int = 1

    def __post_init__(self) -> None:
        _text(self.finding_id, "finding_id")
        _aware(self.timestamp, "timestamp")
        if not isinstance(self.severity, BacktestSeverity):
            raise TypeError("severity must be BacktestSeverity")
        _text(self.code, "code")
        _text(self.message, "message")
        _positive_int(self.occurrence_count, "occurrence_count")


@dataclass(frozen=True, slots=True)
class BacktestSessionResult:
    session_identity: str
    source_path: Path
    trading_date: object
    instruments: tuple[str, ...]
    source_record_count: int
    published_record_count: int
    replay_outcome: ReplayOutcome | None
    backtest_outcome: BacktestOutcome
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: float | None
    signals_generated: int
    orders_accepted: int
    orders_rejected: int
    trades_opened: int
    trades_closed: int
    open_positions: int
    analytics_snapshot: AnalyticsSnapshot
    findings: tuple[BacktestFinding, ...]
    deterministic_session_fingerprint: str
    session_event_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_path", Path(self.source_path))
        object.__setattr__(self, "instruments", tuple(str(item) for item in self.instruments))
        object.__setattr__(self, "findings", tuple(self.findings))
        for name in (
            "source_record_count",
            "published_record_count",
            "signals_generated",
            "orders_accepted",
            "orders_rejected",
            "trades_opened",
            "trades_closed",
            "open_positions",
        ):
            _non_negative_int(getattr(self, name), name)
        _optional_aware(self.started_at, "started_at")
        _optional_aware(self.ended_at, "ended_at")


@dataclass(frozen=True, slots=True)
class BacktestAggregateAnalytics:
    starting_equity: float | None = None
    ending_equity: float | None = None
    net_pnl: float | None = None
    gross_profit: float | None = None
    gross_loss: float | None = None
    fees: float | None = None
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    profit_factor: float | None = None
    expectancy: float | None = None
    maximum_observed_session_drawdown: float | None = None
    maximum_observed_session_drawdown_percentage: float | None = None
    return_percentage: float | None = None
    average_risk_reward: float | None = None
    largest_win: float | None = None
    largest_loss: float | None = None
    consecutive_wins: int = 0
    consecutive_losses: int = 0


@dataclass(frozen=True, slots=True)
class BacktestBatchResult:
    run_id: str
    deterministic_run_fingerprint: str
    mode: BacktestMode
    lifecycle_state: BacktestLifecycleState
    total_sessions: int
    completed_sessions: int
    failed_sessions: int
    stopped_sessions: int
    aggregate_analytics: BacktestAggregateAnalytics
    session_results: tuple[BacktestSessionResult, ...]
    findings: tuple[BacktestFinding, ...]
    started_at: datetime | None
    ended_at: datetime | None
    outcome: BacktestOutcome
    final_summary: str
    report_path: Path | None
    reproducibility_status: ReproducibilityStatus = ReproducibilityStatus.NOT_CHECKED
    result_digest: str = "-"

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_results", tuple(self.session_results))
        object.__setattr__(self, "findings", tuple(self.findings))
        if self.report_path is not None:
            object.__setattr__(self, "report_path", Path(self.report_path))


@dataclass(frozen=True, slots=True)
class BacktestSessionProgress:
    source_path: Path | None = None
    session_id: str = "-"
    current_record_index: int = 0
    total_records: int = 0
    progress_percentage: float = 0.0


@dataclass(frozen=True, slots=True)
class BacktestSnapshot:
    enabled: bool
    lifecycle_state: BacktestLifecycleState
    mode: BacktestMode
    run_id: str
    deterministic_run_fingerprint: str
    current_session_index: int
    total_sessions: int
    completed_sessions: int
    failed_sessions: int
    stopped_sessions: int
    current_progress: BacktestSessionProgress
    aggregate_analytics: BacktestAggregateAnalytics
    findings: tuple[BacktestFinding, ...]
    latest_result: BacktestBatchResult | None
    started_at: datetime | None
    ended_at: datetime | None
    outcome: BacktestOutcome
    final_summary: str
    report_path: Path | None
    reproducibility_status: ReproducibilityStatus
    broker_order_calls: int = 0


def configuration_fingerprint(configuration: BacktestConfiguration, session_fingerprints: tuple[str, ...]) -> str:
    return runtime_configuration_fingerprint(configuration, session_fingerprints, None)


def runtime_configuration_fingerprint(configuration: BacktestConfiguration, session_fingerprints: tuple[str, ...], runtime_configuration) -> str:
    risk_configuration = getattr(runtime_configuration, "risk_configuration", None)
    paper_configuration = getattr(runtime_configuration, "paper_trading_configuration", None)
    analytics_configuration = getattr(runtime_configuration, "performance_analytics_configuration", None)
    payload = {
        "schema_version": BACKTEST_SCHEMA_VERSION,
        "mode": configuration.mode.value,
        "session_fingerprints": session_fingerprints,
        "strategy_configuration": {"version": "application_default_v1"},
        "risk_configuration": _stable_configuration_payload(risk_configuration),
        "paper_trading_configuration": _stable_configuration_payload(paper_configuration),
        "performance_analytics_configuration": _stable_configuration_payload(
            analytics_configuration,
            excluded_fields={"journal_path", "export_directory"},
        ),
        "execution_policy": {
            "safety_mode": configuration.safety_mode.value,
            "broker_mode": configuration.broker_mode.value,
            "intrabar_policy": getattr(getattr(paper_configuration, "intrabar_policy", None), "value", None),
        },
        "max_sessions": configuration.max_sessions,
        "max_findings": configuration.max_findings,
        "max_session_results": configuration.max_session_results,
        "stop_on_session_failure": configuration.stop_on_session_failure,
    }
    return stable_digest(payload)


def stable_digest(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")).hexdigest()


def session_result_digest(results: tuple[BacktestSessionResult, ...], findings: tuple[BacktestFinding, ...], fingerprint: str) -> str:
    payload = {
        "fingerprint": fingerprint,
        "sessions": [
            {
                "session": item.session_identity,
                "published": item.published_record_count,
                "replay_outcome": getattr(item.replay_outcome, "value", None),
                "backtest_outcome": item.backtest_outcome.value,
                "trades_closed": item.trades_closed,
                "open_positions": item.open_positions,
                "analytics": _summary_payload(item.analytics_snapshot.overall),
                "fingerprint": item.deterministic_session_fingerprint,
                "event_digest": item.session_event_digest,
            }
            for item in results
        ],
        "findings": [item.code for item in findings],
    }
    return stable_digest(payload)


def aggregate_analytics(snapshots: tuple[AnalyticsSnapshot, ...], starting_equity: float | None) -> BacktestAggregateAnalytics:
    summaries = tuple(snapshot.overall for snapshot in snapshots)
    count = sum(item.record_count for item in summaries)
    wins = sum(item.winning_trades for item in summaries)
    losses = sum(item.losing_trades for item in summaries)
    gross_profit = sum(item.gross_profit for item in summaries)
    gross_loss = sum(item.gross_loss for item in summaries)
    net = sum(item.net_profit for item in summaries)
    fees = sum(item.total_fees for item in summaries)
    return BacktestAggregateAnalytics(
        starting_equity=starting_equity,
        ending_equity=(starting_equity + net) if starting_equity is not None else None,
        net_pnl=net,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        fees=fees,
        trade_count=count,
        winning_trades=wins,
        losing_trades=losses,
        win_rate=(wins / count * 100.0) if count else None,
        average_win=(gross_profit / wins) if wins else None,
        average_loss=(-(gross_loss / losses)) if losses else None,
        profit_factor=(gross_profit / gross_loss) if gross_loss else None,
        expectancy=(net / count) if count else None,
        maximum_observed_session_drawdown=max((item.maximum_drawdown for item in summaries), default=0.0),
        maximum_observed_session_drawdown_percentage=max((item.maximum_drawdown_percentage for item in summaries), default=0.0),
        return_percentage=(net / starting_equity * 100.0) if starting_equity else None,
        average_risk_reward=_weighted_average(summaries, "average_r"),
        largest_win=max((item.largest_win for item in summaries if item.largest_win is not None), default=None),
        largest_loss=min((item.largest_loss for item in summaries if item.largest_loss is not None), default=None),
        consecutive_wins=max((item.maximum_consecutive_wins for item in summaries), default=0),
        consecutive_losses=max((item.maximum_consecutive_losses for item in summaries), default=0),
    )


def _weighted_average(summaries: tuple[PerformanceSummary, ...], name: str) -> float | None:
    values = tuple((getattr(item, name), item.record_count) for item in summaries if getattr(item, name) is not None and item.record_count)
    total = sum(weight for _, weight in values)
    return None if total <= 0 else sum(value * weight for value, weight in values) / total


def _summary_payload(summary: PerformanceSummary) -> dict[str, object]:
    return {
        "record_count": summary.record_count,
        "winning_trades": summary.winning_trades,
        "losing_trades": summary.losing_trades,
        "gross_profit": summary.gross_profit,
        "gross_loss": summary.gross_loss,
        "net_profit": summary.net_profit,
        "total_fees": summary.total_fees,
        "maximum_drawdown": summary.maximum_drawdown,
        "win_rate": summary.win_rate,
    }


def _stable_configuration_payload(configuration, *, excluded_fields: set[str] | None = None):
    if configuration is None:
        return {"default": True}
    excluded = excluded_fields or set()
    if is_dataclass(configuration):
        payload = {}
        for item in fields(configuration):
            if item.name in excluded:
                continue
            payload[item.name] = _stable_configuration_value(getattr(configuration, item.name))
        return payload
    return _stable_configuration_value(configuration)


def _stable_configuration_value(value):
    if isinstance(value, Path):
        return "<path>"
    if isinstance(value, tuple):
        return tuple(_stable_configuration_value(item) for item in value)
    if isinstance(value, list):
        return tuple(_stable_configuration_value(item) for item in value)
    if is_dataclass(value):
        return _stable_configuration_payload(value)
    return getattr(value, "value", value)


def _json_default(value):
    if isinstance(value, Path):
        return value.name
    if isinstance(value, datetime):
        return value.isoformat()
    return getattr(value, "value", str(value))


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _optional_aware(value: datetime | None, name: str) -> None:
    if value is not None:
        _aware(value, name)
