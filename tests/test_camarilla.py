"""
====================================================
Vision Trading OS
Test - Camarilla Calculator
====================================================
"""

from datetime import date

from core.models.daily_ohlc import DailyOHLC
from engines.camarilla.calculator import CamarillaCalculator


def test_camarilla_calculator_uses_daily_ohlc_input():
    daily_ohlc = DailyOHLC(
        trading_date=date(2026, 7, 10),
        open=25150,
        high=25260,
        low=25010,
        close=25120,
    )

    levels = CamarillaCalculator.calculate(daily_ohlc)

    assert levels.trading_date == daily_ohlc.trading_date
    assert levels.previous_high == 25260
    assert levels.previous_low == 25010
    assert levels.previous_close == 25120
    assert levels.pivot == 25130.00
    assert levels.h3 == 25188.75
    assert levels.h4 == 25257.50
    assert levels.l3 == 25051.25
    assert levels.l4 == 24982.50


def test_camarilla_calculator_rejects_invalid_range():
    daily_ohlc = DailyOHLC(
        trading_date=date(2026, 7, 10),
        open=25150,
        high=25010,
        low=25260,
        close=25120,
    )

    try:
        CamarillaCalculator.calculate(daily_ohlc)
    except ValueError:
        return

    raise AssertionError("Expected invalid Camarilla range to raise ValueError")
