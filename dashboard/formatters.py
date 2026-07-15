"""
Deterministic dashboard presentation formatters.
"""

import math
import re
from datetime import date, datetime
from numbers import Real


MISSING = "-"


def text(value) -> str:
    return str(value) if value not in (None, "") else MISSING


def joined(values: tuple[str, ...] | list[str]) -> str:
    return ", ".join(str(value) for value in values if value not in (None, "")) or MISSING


def yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def ready(value: bool) -> str:
    return "Ready" if value else "Not Ready"


def quantity(value: int | None) -> str:
    return str(value) if _finite_number(value) else MISSING


def integer(value: int | None) -> str:
    return str(value) if _finite_number(value) else MISSING


def price(value: float | None) -> str:
    return f"{value:.2f}" if _finite_number(value) else MISSING


def ratio(value: float | None) -> str:
    return f"{value:.4f}" if _finite_number(value) else MISSING


def timestamp(value: datetime | None) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if value is not None else MISSING


def date_text(value: date | None) -> str:
    if value is None or isinstance(value, datetime) or not isinstance(value, date):
        return MISSING
    return value.isoformat()


def semantic_kind(value) -> str:
    normalized = _status_key(value)
    if normalized in {
        "RUNNING",
        "READY",
        "HEALTHY",
        "CONNECTED",
        "ALLOW",
        "APPROVED",
        "BULLISH",
        "PROFIT",
        "SUITABLE",
        "ALIGNED",
        "YES",
    }:
        return "positive"
    if normalized in {"STOPPED", "WAITING", "CREATED", "NEUTRAL", "NO_POSITION", "NONE", "NO", "-"}:
        return "neutral"
    if normalized in {"DEGRADED", "WARNING", "STARTING", "STOPPING", "CONFLICT", "PARTIAL", "RECOVERY_PENDING", "NOT_READY", "MIXED"}:
        return "warning"
    if normalized in {"ERROR", "LOCKED", "BLOCKED", "REJECTED", "FAILED", "BEARISH", "LOSS", "DISCONNECTED", "NOT_SUITABLE"}:
        return "negative"
    return "neutral"


def pnl_kind(value: float | None) -> str:
    if not _finite_number(value) or value == 0:
        return "neutral"
    return "positive" if value > 0 else "negative"


def _finite_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    return math.isfinite(float(value))


def _status_key(value) -> str:
    normalized = text(value).strip().upper()
    if normalized == MISSING:
        return MISSING
    return "_".join(part for part in re.split(r"[\s_-]+", normalized) if part)
