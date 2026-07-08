from datetime import date
from engines.camarilla.calculator import CamarillaCalculator


levels = CamarillaCalculator.calculate(
    trading_date=date.today(),
    previous_high=25260,
    previous_low=25010,
    previous_close=25120,
)

print(levels)