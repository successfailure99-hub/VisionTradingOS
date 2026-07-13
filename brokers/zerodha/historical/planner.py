"""
Zerodha historical request planner.
"""

from datetime import timedelta

from brokers.zerodha.historical.models import ZerodhaHistoricalChunk, ZerodhaHistoricalRequest
from core.enums.timeframe import TimeFrame


MAX_CHUNKS = {
    TimeFrame.ONE_MINUTE: timedelta(days=60),
    TimeFrame.THREE_MINUTES: timedelta(days=100),
    TimeFrame.FIVE_MINUTES: timedelta(days=100),
    TimeFrame.TEN_MINUTES: timedelta(days=100),
    TimeFrame.FIFTEEN_MINUTES: timedelta(days=180),
    TimeFrame.THIRTY_MINUTES: timedelta(days=180),
    TimeFrame.ONE_HOUR: timedelta(days=365),
    TimeFrame.DAILY: timedelta(days=2000),
}


class ZerodhaHistoricalRequestPlanner:
    def plan(
        self,
        request: ZerodhaHistoricalRequest,
    ) -> tuple[ZerodhaHistoricalChunk, ...]:
        if not isinstance(request, ZerodhaHistoricalRequest):
            raise TypeError("request must be ZerodhaHistoricalRequest")
        if request.timeframe not in MAX_CHUNKS:
            raise ValueError(f"unsupported historical timeframe: {request.timeframe.value}")
        max_duration = MAX_CHUNKS[request.timeframe]
        chunks = []
        start = request.start_at
        while start < request.end_at:
            end = min(start + max_duration, request.end_at)
            chunks.append(ZerodhaHistoricalChunk(start, end))
            start = end
        return tuple(chunks)
