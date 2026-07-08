from core.event_bus import EventBus
from core.events import CAMARILLA_UPDATED

bus = EventBus()


def on_camarilla(levels):
    print("Received Camarilla Levels")
    print(levels)


bus.subscribe(CAMARILLA_UPDATED, on_camarilla)

bus.publish(
    CAMARILLA_UPDATED,
    {
        "H4": 25250,
        "L4": 24980,
    },
)