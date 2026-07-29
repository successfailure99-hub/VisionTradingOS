"""
Vision Method V1 contract validators.
"""

from __future__ import annotations

from application.enums import RuntimeInstrument
from core.enums.timeframe import TimeFrame

from .models import VisionMethodSnapshot


def validate_vision_method_snapshot(
    snapshot: VisionMethodSnapshot,
    *,
    instrument: RuntimeInstrument | None = None,
    timeframe: TimeFrame | None = None,
) -> VisionMethodSnapshot:
    if not isinstance(snapshot, VisionMethodSnapshot):
        raise TypeError("snapshot must be VisionMethodSnapshot.")
    if instrument is not None:
        if not isinstance(instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument.")
        if snapshot.instrument is not instrument:
            raise ValueError("instrument mismatch.")
    if timeframe is not None:
        if not isinstance(timeframe, TimeFrame):
            raise TypeError("timeframe must be TimeFrame.")
        if snapshot.timeframe is not timeframe:
            raise ValueError("timeframe mismatch.")
    return snapshot
