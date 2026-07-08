"""
====================================================
Vision Trading OS
Event Bus
====================================================
"""

from collections import defaultdict


class EventBus:

    def __init__(self):
        self._subscribers = defaultdict(list)

    def subscribe(self, event_name, callback):
        self._subscribers[event_name].append(callback)

    def publish(self, event_name, data=None):

        for callback in self._subscribers[event_name]:
            callback(data)