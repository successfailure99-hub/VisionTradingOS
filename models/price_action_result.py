"""
====================================================
Vision Trading OS
Price Action Result
====================================================
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class PriceActionResult:

    trend: str = "UNKNOWN"

    structure: str = "UNKNOWN"

    hh: bool = False
    hl: bool = False
    lh: bool = False
    ll: bool = False

    bos: bool = False
    choch: bool = False

    swing_high: float | None = None
    swing_low: float | None = None

    strength: str = "UNKNOWN"

    confidence: int = 0

    evidence: list[str] = field(default_factory=list)