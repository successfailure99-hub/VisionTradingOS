"""
====================================================
Vision Trading OS
Strategy Result
====================================================
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class StrategyResult:

    strategy: str

    signal: str = "NO_SETUP"

    confidence: int = 0

    reasons: list[str] = field(default_factory=list)

    risks: list[str] = field(default_factory=list)

    recommendation: str = ""

    entry: float | None = None

    stop_loss: float | None = None

    target1: float | None = None

    target2: float | None = None