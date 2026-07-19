"""
Performance analytics bounded domain values.
"""

from enum import Enum


class AnalyticsGroupType(Enum):
    INSTRUMENT = "instrument"
    DIRECTION = "direction"
    SETUP = "setup"
    ENTRY_TYPE = "entry_type"
    EXIT_TYPE = "exit_type"
    TIME_OF_DAY = "time_of_day"
    CAMARILLA = "camarilla"
    CPR = "cpr"
    AI_CONFIDENCE = "ai_confidence"


class AnalyticsPeriod(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ReviewClassification(Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"


class AnalyticsRecordStatus(Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    DISABLED = "disabled"
