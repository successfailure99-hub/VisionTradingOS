"""
Zerodha historical data package.
"""

from brokers.zerodha.historical.client import KiteHistoricalClient, ZerodhaHistoricalClientProtocol
from brokers.zerodha.historical.enums import HistoricalGapType, ZerodhaHistoricalStatus
from brokers.zerodha.historical.intervals import interval_duration, to_zerodha_interval
from brokers.zerodha.historical.manager import ZerodhaHistoricalDataManager
from brokers.zerodha.historical.models import (
    HistoricalGap,
    ZerodhaHistoricalChunk,
    ZerodhaHistoricalRequest,
    ZerodhaHistoricalResult,
    ZerodhaHistoricalSnapshot,
)
from brokers.zerodha.historical.normalizer import ZerodhaHistoricalCandleNormalizer
from brokers.zerodha.historical.planner import ZerodhaHistoricalRequestPlanner
from brokers.zerodha.historical.validator import ZerodhaHistoricalSeriesValidator

__all__ = [
    "ZerodhaHistoricalStatus",
    "HistoricalGapType",
    "ZerodhaHistoricalRequest",
    "ZerodhaHistoricalChunk",
    "HistoricalGap",
    "ZerodhaHistoricalResult",
    "ZerodhaHistoricalSnapshot",
    "ZerodhaHistoricalClientProtocol",
    "KiteHistoricalClient",
    "to_zerodha_interval",
    "interval_duration",
    "ZerodhaHistoricalCandleNormalizer",
    "ZerodhaHistoricalRequestPlanner",
    "ZerodhaHistoricalSeriesValidator",
    "ZerodhaHistoricalDataManager",
]
