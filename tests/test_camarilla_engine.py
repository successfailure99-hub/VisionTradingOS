"""
====================================================
Vision Trading OS
Test - Camarilla Engine
====================================================
"""

from datetime import date

from core.event_bus import EventBus
from core.events import CAMARILLA_UPDATED

from core.models.daily_ohlc import DailyOHLC

from engines.camarilla.camarilla_engine import CamarillaEngine


# ==================================================
# Create Event Bus
# ==================================================

event_bus = EventBus()


# ==================================================
# Event Listener
# ==================================================

def on_camarilla_updated(levels):
    print("\n========== EVENT RECEIVED ==========")
    print(levels)


event_bus.subscribe(
    CAMARILLA_UPDATED,
    on_camarilla_updated,
)


# ==================================================
# Create Engine
# ==================================================

engine = CamarillaEngine(event_bus)


# ==================================================
# Create Previous Day OHLC
# ==================================================

daily_ohlc = DailyOHLC(
    trading_date=date.today(),
    open=25150,
    high=25260,
    low=25010,
    close=25120,
)


# ==================================================
# Calculate Levels
# ==================================================

levels = engine.calculate(daily_ohlc)


# ==================================================
# Display Results
# ==================================================

print("\n========== ENGINE DATA ==========")
print(levels)

print("\nEngine Ready:", engine.is_ready())

print("\nCached Levels:")
print(engine.levels)