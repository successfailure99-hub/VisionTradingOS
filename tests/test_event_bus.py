from core.event_bus import EventBus


def test_event_bus():

    bus = EventBus()

    results = []

    def receiver(data):
        results.append(data)

    bus.subscribe("hello", receiver)

    bus.publish("hello", 100)

    assert results == [100]