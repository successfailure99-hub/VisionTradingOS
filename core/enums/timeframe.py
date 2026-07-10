"""
====================================================
Vision Trading OS
TimeFrame Enum
====================================================
"""

from enum import Enum


class TimeFrame(str, Enum):
    """
    Standard timeframes used throughout
    Vision Trading OS.
    """

    ONE_MINUTE = "1m"

    THREE_MINUTE = "3m"

    FIVE_MINUTE = "5m"

    TEN_MINUTE = "10m"

    FIFTEEN_MINUTE = "15m"

    THIRTY_MINUTE = "30m"

    ONE_HOUR = "1h"

    ONE_DAY = "1D"