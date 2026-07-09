"""
====================================================
Vision Trading OS
Test - CPR Engine
====================================================
"""

from datetime import date

from core.event_bus import EventBus
from core.events import CPR_UPDATED

from core.models.daily_ohlc import DailyOHLC

from engines.cpr.cpr_engine import CPREngine


# ==================================================
# Create Event Bus
# ==================================================

event_bus = EventBus()


# ==================================================
# Event Listener
# ==================================================

def on_cpr_updated(levels):
    print("\n========== CPR EVENT RECEIVED ==========")
    print(levels)


event_bus.subscribe(
    CPR_UPDATED,
    on_cpr_updated,
)


# ==================================================
# Create Engine
# ==================================================

engine = CPREngine(event_bus)


# ==================================================
# Previous Day OHLC
# ==================================================

daily_ohlc = DailyOHLC(
    trading_date=date.today(),
    open=25150,
    high=25260,
    low=25010,
    close=25120,
)


# ==================================================
# Calculate CPR
# ==================================================

levels = engine.calculate(daily_ohlc)


# ==================================================
# Results
# ==================================================

print("\n========== ENGINE DATA ==========")
print(levels)

print("\nEngine Ready:", engine.is_ready())

print("\nCached Levels:")
print(engine.levels)