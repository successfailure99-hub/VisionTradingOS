"""
Deterministic dashboard presentation formatters.
"""

from datetime import datetime


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
    return str(value) if value is not None else MISSING


def integer(value: int | None) -> str:
    return str(value) if value is not None else MISSING


def price(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else MISSING


def ratio(value: float | None) -> str:
    return f"{value:.4f}" if value is not None else MISSING


def timestamp(value: datetime | None) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if value is not None else MISSING


def semantic_kind(value) -> str:
    normalized = text(value).lower()
    if normalized in {"-", "none", "not ready", "no", "offline", "stopped", "created"}:
        return "neutral"
    if any(token in normalized for token in ("error", "rejected", "failed", "conflict", "not suitable")):
        return "negative"
    if any(token in normalized for token in ("warning", "starting", "stopping", "blocked", "not ready")):
        return "warning"
    if any(token in normalized for token in ("running", "ready", "connected", "yes", "approved", "bullish", "suitable", "aligned")):
        return "positive"
    return "neutral"


def pnl_kind(value: float | None) -> str:
    if value is None or value == 0:
        return "neutral"
    return "positive" if value > 0 else "negative"
