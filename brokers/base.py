"""
Broker client protocol definitions.
"""

from typing import Any, Protocol


class BrokerOrderClient(Protocol):
    def place_order(self, **kwargs: Any) -> str:
        ...

    def modify_order(self, **kwargs: Any) -> str:
        ...

    def cancel_order(self, **kwargs: Any) -> str:
        ...
