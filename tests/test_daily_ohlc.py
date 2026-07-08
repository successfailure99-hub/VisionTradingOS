from datetime import date

from core.models.daily_ohlc import DailyOHLC


ohlc = DailyOHLC(
    trading_date=date.today(),
    open=25150,
    high=25260,
    low=25010,
    close=25120,
)

print(ohlc)