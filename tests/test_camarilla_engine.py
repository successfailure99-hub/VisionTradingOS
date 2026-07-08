from datetime import date

from core.event_bus import EventBus
from core.events import CAMARILLA_UPDATED

from engines.camarilla.camarilla_engine import CamarillaEngine


bus = EventBus()


def on_camarilla(levels):
    print("\n========== EVENT RECEIVED ==========")
    print(levels)


bus.subscribe(CAMARILLA_UPDATED, on_camarilla)


engine = CamarillaEngine(bus)

levels = engine.calculate(
    trading_date=date.today(),
    previous_high=25260,
    previous_low=25010,
    previous_close=25120,
)

print("\n========== ENGINE DATA ==========")
print(levels)

print("\nEngine Ready:", engine.is_ready())