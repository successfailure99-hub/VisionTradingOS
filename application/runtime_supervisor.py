"""
Production runtime supervisor.

The supervisor observes the canonical SymbolRuntime snapshots and coordinates
existing recovery hooks. It does not own market state, calculate trading logic,
or create runtime snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from application.enums import RuntimeStatus
from application.lifecycle_manager import ApplicationLifecycleManager
from application.models import RuntimeSnapshot


DEFAULT_SUPERVISOR_INTERVAL_MS = 500

_REQUIRED_STAGES = (
    "RuntimeSnapshot",
    "RuntimeContract",
    "RuntimeIntegrity",
    "Market Data",
    "Candle Engine",
    "Vision Decision History",
    "Liquidity Input History",
    "Daily Context",
    "Vision Method",
    "Validation",
    "Runtime Adapter",
    "TradeCandidate",
    "Strategy",
    "Risk",
    "Lifecycle",
    "Paper Position",
    "Journal",
    "Dashboard",
    "AI",
    "Option Chain",
)


@dataclass(frozen=True, slots=True)
class RuntimeSupervisorCheck:
    stage: str
    owner: str
    producer: str
    consumer: str
    status: str
    blocking_reason: str = "-"
    recovery_action: str = "-"

    def __post_init__(self) -> None:
        for field_name in ("stage", "owner", "producer", "consumer", "status", "blocking_reason", "recovery_action"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be text")
            object.__setattr__(self, field_name, value.strip() or "-")

    @property
    def healthy(self) -> bool:
        return self.status in {"READY", "VALID", "NOT_APPLICABLE", "SYNCHRONIZED"}


@dataclass(frozen=True, slots=True)
class RuntimeSupervisorSnapshot:
    status: str
    interval_ms: int
    checks: tuple[RuntimeSupervisorCheck, ...]
    recovery_actions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, str) or not self.status.strip():
            raise ValueError("status must be non-empty text")
        object.__setattr__(self, "status", self.status.strip())
        if isinstance(self.interval_ms, bool) or not isinstance(self.interval_ms, int) or self.interval_ms <= 0:
            raise ValueError("interval_ms must be a positive integer")
        checks = tuple(self.checks)
        for item in checks:
            if not isinstance(item, RuntimeSupervisorCheck):
                raise TypeError("checks must contain RuntimeSupervisorCheck values")
        object.__setattr__(self, "checks", checks)
        actions = tuple(self.recovery_actions)
        for item in actions:
            if not isinstance(item, str):
                raise TypeError("recovery_actions must contain text")
        object.__setattr__(self, "recovery_actions", tuple(item.strip() for item in actions if item.strip()))


class RuntimeSupervisor:
    """
    Monitor canonical runtime objects and invoke existing recovery hooks.
    """

    def __init__(
        self,
        lifecycle: ApplicationLifecycleManager,
        *,
        interval_ms: int = DEFAULT_SUPERVISOR_INTERVAL_MS,
        recovery_handlers: dict[str, Callable[[], object]] | None = None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be ApplicationLifecycleManager")
        if isinstance(interval_ms, bool) or not isinstance(interval_ms, int) or interval_ms <= 0:
            raise ValueError("interval_ms must be a positive integer")
        self._lifecycle = lifecycle
        self._interval_ms = interval_ms
        self._recovery_handlers = dict(recovery_handlers or {})
        self._last_snapshot = RuntimeSupervisorSnapshot("CREATED", interval_ms, ())

    @property
    def interval_ms(self) -> int:
        return self._interval_ms

    @property
    def last_snapshot(self) -> RuntimeSupervisorSnapshot:
        return self._last_snapshot

    def set_recovery_handler(self, stage: str, handler: Callable[[], object]) -> None:
        if not isinstance(stage, str) or not stage.strip():
            raise ValueError("stage must be non-empty text")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._recovery_handlers[stage.strip()] = handler

    def monitor(self, lifecycle_snapshot=None) -> RuntimeSupervisorSnapshot:
        first = self.check(lifecycle_snapshot)
        actions = []
        for check in first.checks:
            if check.healthy or check.recovery_action == "-":
                continue
            handler = self._recovery_handlers.get(check.stage)
            if handler is None:
                continue
            handler()
            actions.append(f"{check.stage}: {check.recovery_action}")
        if not actions:
            self._last_snapshot = first
            return first
        second = self.check(lifecycle_snapshot)
        self._last_snapshot = RuntimeSupervisorSnapshot(second.status, self._interval_ms, second.checks, tuple(actions))
        return self._last_snapshot

    def check(self, lifecycle_snapshot=None) -> RuntimeSupervisorSnapshot:
        lifecycle = lifecycle_snapshot or self._lifecycle.snapshot()
        checks: list[RuntimeSupervisorCheck] = []
        if lifecycle.status is not RuntimeStatus.RUNNING:
            checks.append(
                RuntimeSupervisorCheck(
                    "RuntimeSnapshot",
                    "SymbolRuntime",
                    "SymbolRuntime.snapshot",
                    "Dashboard",
                    "FAILED",
                    f"Lifecycle is {lifecycle.status.value}.",
                    "Restart ApplicationLifecycleManager.",
                )
            )
            snapshot = RuntimeSupervisorSnapshot("FAILED", self._interval_ms, tuple(checks))
            self._last_snapshot = snapshot
            return snapshot
        runtime_snapshots = tuple(lifecycle.orchestrator_snapshot.runtime_snapshots)
        if not runtime_snapshots:
            checks.append(
                RuntimeSupervisorCheck(
                    "RuntimeSnapshot",
                    "SymbolRuntime",
                    "SymbolRuntime.snapshot",
                    "Dashboard",
                    "FAILED",
                    "No RuntimeSnapshot values are available.",
                    "Rebuild SymbolRuntime snapshots from ApplicationOrchestrator.",
                )
            )
        for runtime_snapshot in runtime_snapshots:
            checks.extend(_checks_for_runtime(runtime_snapshot))
        status = "READY" if checks and all(item.healthy for item in checks) else "RECOVERING"
        if any(item.status in {"FAILED", "ERROR"} for item in checks):
            status = "FAILED"
        snapshot = RuntimeSupervisorSnapshot(status, self._interval_ms, tuple(checks))
        self._last_snapshot = snapshot
        return snapshot


def _checks_for_runtime(snapshot: RuntimeSnapshot) -> tuple[RuntimeSupervisorCheck, ...]:
    rows: dict[str, RuntimeSupervisorCheck] = {}
    rows["RuntimeSnapshot"] = RuntimeSupervisorCheck(
        "RuntimeSnapshot",
        "SymbolRuntime",
        "SymbolRuntime.snapshot",
        "Dashboard",
        "READY",
    )
    contract = snapshot.runtime_contract_report
    rows["RuntimeContract"] = RuntimeSupervisorCheck(
        "RuntimeContract",
        "SymbolRuntime",
        "RuntimeContractValidator",
        "RuntimeSupervisor",
        "VALID" if contract is not None and contract.valid else "FAILED",
        "-" if contract is not None and contract.valid else (contract.blocking_reason if contract is not None else "Runtime contract report missing."),
        "Regenerate RuntimeSnapshot after rejecting invalid publishers.",
    )
    integrity_ok = contract is not None and not contract.integrity_violations
    rows["RuntimeIntegrity"] = RuntimeSupervisorCheck(
        "RuntimeIntegrity",
        "SymbolRuntime",
        "RuntimeIntegrity",
        "RuntimeSupervisor",
        "VALID" if integrity_ok else "FAILED",
        "-" if integrity_ok else "Runtime integrity violation present.",
        "Recover canonical runtime state from SymbolRuntime producers.",
    )
    for stage in tuple(snapshot.runtime_verification_report):
        rows[stage.stage] = RuntimeSupervisorCheck(
            stage.stage,
            stage.owner,
            stage.producer,
            stage.consumer,
            _normalize_status(stage.status),
            stage.blocking_reason,
            _recovery_action_for_stage(stage.stage),
        )
    _ensure_inferred_rows(snapshot, rows)
    return tuple(rows[name] for name in _REQUIRED_STAGES if name in rows)


def _ensure_inferred_rows(snapshot: RuntimeSnapshot, rows: dict[str, RuntimeSupervisorCheck]) -> None:
    rows.setdefault("Market Data", _ready_row("Market Data", snapshot.latest_tick is not None, "MarketDataEngine", "Tick", "Candle Engine"))
    rows.setdefault("Candle Engine", _dependency_row(getattr(snapshot, "base_candle_readiness", None), "Candle Engine", "CandleEngine", "Closed Candle", "Vision Method"))
    rows.setdefault("Vision Decision History", _dependency_row(getattr(snapshot, "vision_decision_history_readiness", None), "Vision Decision History", "CandleEngine", "5m Closed Candle", "Vision Method"))
    rows.setdefault("Liquidity Input History", _dependency_row(getattr(snapshot, "liquidity_input_readiness", None), "Liquidity Input History", "Vision Liquidity", "Closed Candle History", "Vision Structure Events"))
    rows.setdefault("Daily Context", _ready_row("Daily Context", snapshot.cpr is not None and snapshot.camarilla is not None, "SymbolRuntime", "Daily Context Runtime", "Vision Method"))
    rows.setdefault("Vision Method", _ready_row("Vision Method", snapshot.vision_method_snapshot is not None, "SymbolRuntime", "Vision Method Calculator", "Validation"))
    rows.setdefault("Validation", _ready_row("Validation", snapshot.vision_method_validation_report is not None, "SymbolRuntime", "Vision Validation", "Runtime Adapter"))
    rows.setdefault("Runtime Adapter", _ready_row("Runtime Adapter", snapshot.vision_trade_candidate is not None, "SymbolRuntime", "Runtime Adapter", "TradeCandidate"))
    rows.setdefault("TradeCandidate", _ready_row("TradeCandidate", snapshot.vision_trade_candidate is not None, "Runtime Adapter", "TradeCandidate", "Risk"))
    rows.setdefault("Strategy", _ready_row("Strategy", snapshot.strategy_decision_v2 is not None or snapshot.vision_trade_candidate is None, "SymbolRuntime", "StrategyDecisionV2", "Risk"))
    rows.setdefault("Risk", _ready_row("Risk", snapshot.risk_management_v2 is not None or snapshot.vision_trade_candidate is None, "Risk Engine", "RiskManagementV2", "Lifecycle"))
    rows.setdefault("Lifecycle", _ready_row("Lifecycle", snapshot.trade_lifecycle_v1 is not None, "Lifecycle Engine", "TradeLifecycleV1", "Paper Position"))
    rows.setdefault("Paper Position", _ready_row("Paper Position", snapshot.canonical_paper_position is not None or snapshot.vision_trade_candidate is None, "Paper Engine", "Paper Position", "Journal"))
    rows.setdefault("Journal", _ready_row("Journal", snapshot.journal_persistence is not None, "TradeJournal", "TradeJournalV1", "Dashboard"))
    rows.setdefault("Dashboard", RuntimeSupervisorCheck("Dashboard", "Dashboard Presenters", "RuntimeSnapshot", "Dashboard", "READY"))
    rows.setdefault("AI", _ready_row("AI", bool(snapshot.vision_ai_explanation or snapshot.ai_reasoning_v2), "SymbolRuntime", "AI Reasoning V2", "Dashboard"))
    option_ready = snapshot.option_chain_runtime is not None and snapshot.option_chain_runtime.state in {"READY", "WAITING_FOR_OPTION_TICKS", "WAITING_FOR_ANALYTICS"}
    rows.setdefault("Option Chain", _ready_row("Option Chain", option_ready, "SymbolRuntime", "OptionChainRuntime", "Vision Option Confirmation"))


def _ready_row(stage: str, ready: bool, owner: str, producer: str, consumer: str) -> RuntimeSupervisorCheck:
    return RuntimeSupervisorCheck(
        stage,
        owner,
        producer,
        consumer,
        "READY" if ready else "RECOVERING",
        "-" if ready else f"{stage} is not available from the canonical RuntimeSnapshot.",
        _recovery_action_for_stage(stage),
    )


def _dependency_row(readiness, stage: str, owner: str, producer: str, consumer: str) -> RuntimeSupervisorCheck:
    if readiness is None:
        return _ready_row(stage, False, owner, producer, consumer)
    status = getattr(readiness, "status", "NOT_READY")
    if status in {"INSUFFICIENT", "INVALID", "STALE"} and getattr(readiness, "criticality", "") == "SUPPORTING":
        supervisor_status = "DEGRADED"
    elif status == "READY":
        supervisor_status = "READY"
    elif status in {"FAILED", "INVALID"}:
        supervisor_status = "FAILED"
    else:
        supervisor_status = "RECOVERING"
    detail = getattr(readiness, "reason", "-")
    return RuntimeSupervisorCheck(
        stage,
        getattr(readiness, "owner", owner),
        getattr(readiness, "producer", producer),
        getattr(readiness, "consumer", consumer),
        supervisor_status,
        "-" if supervisor_status == "READY" else detail,
        _recovery_action_for_stage(stage),
    )


def _normalize_status(value: str) -> str:
    text = str(value).strip().upper() or "RECOVERING"
    if text in {"READY", "VALID", "NOT_APPLICABLE", "SYNCHRONIZED"}:
        return text
    if text in {"FAILED", "ERROR", "BLOCKED"}:
        return "FAILED"
    return "RECOVERING"


def _recovery_action_for_stage(stage: str) -> str:
    return {
        "Vision Method": "Recalculate Vision Method through the existing live bridge.",
        "Validation": "Revalidate the canonical VisionMethodSnapshot.",
        "Runtime Adapter": "Recalculate TradeCandidate from Vision Method and Validation.",
        "TradeCandidate": "Recalculate TradeCandidate from Runtime Adapter.",
        "Paper Position": "Recover Lifecycle/Paper position from the canonical journal checkpoint.",
        "Dashboard": "Refresh dashboard presenters from the latest RuntimeSnapshot.",
    }.get(stage, "-")
