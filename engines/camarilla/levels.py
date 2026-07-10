from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class CamarillaLevels:
    """
    Stores the complete immutable Camarilla levels for one trading day.
    """

    trading_date: date

    previous_high: float
    previous_low: float
    previous_close: float

    pivot: float

    h3: float
    h4: float
    h5: float
    h6: float

    l3: float
    l4: float
    l5: float
    l6: float
