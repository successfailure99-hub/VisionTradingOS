"""
====================================================
Vision Trading OS
Base Engine
====================================================
"""

from typing import Any

from core.event_bus import EventBus


class BaseEngine:
    """
    Base class for all Vision Trading OS engines.

    Provides:

    - Event Bus access
    - Cache
    - Ready status
    - Cache clearing
    """

    def __init__(self, event_bus: EventBus):

        self._event_bus = event_bus

        self._data: Any = None

    @property
    def data(self):

        return self._data

    def is_ready(self) -> bool:

        return self._data is not None

    def clear(self) -> None:

        self._data = None