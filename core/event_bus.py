"""
====================================================
Vision Trading OS
Event Bus
====================================================
"""

from collections import defaultdict
from typing import Callable, Any


class EventBus:
    """
    Simple Publish/Subscribe Event Bus
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_name: str, callback: Callable) -> None:
        """
        Subscribe a callback to an event.
        """
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable) -> None:
        """
        Remove a callback from an event.
        """
        if callback in self._subscribers[event_name]:
            self._subscribers[event_name].remove(callback)

    def publish(self, event_name: str, data: Any = None) -> None:
        """
        Publish an event to all subscribers.
        """
        for callback in self._subscribers[event_name]:
            callback(data)

    def clear(self) -> None:
        """
        Remove all subscribers.
        """
        self._subscribers.clear()