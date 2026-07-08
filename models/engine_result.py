"""
====================================================
Vision Trading OS
Engine Result Model
====================================================
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class EngineResult:

    engine: str

    status: str = "OK"

    confidence: int = 0

    trend: str = "UNKNOWN"

    evidence: list[str] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)

    recommendation: str = ""