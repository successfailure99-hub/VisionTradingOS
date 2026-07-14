"""
Configuration for the live option-chain runtime.
"""

from dataclasses import dataclass


def _require_bool(value: bool, field_name: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")
    return value


@dataclass(frozen=True, slots=True)
class LiveOptionChainConfiguration:
    require_all_pairs: bool = True
    maximum_quote_age_seconds: int = 15
    reject_crossed_market: bool = True
    publish_on_every_accepted_batch: bool = True

    def __post_init__(self) -> None:
        _require_bool(self.require_all_pairs, "require_all_pairs")
        _require_bool(self.reject_crossed_market, "reject_crossed_market")
        _require_bool(
            self.publish_on_every_accepted_batch,
            "publish_on_every_accepted_batch",
        )
        if (
            isinstance(self.maximum_quote_age_seconds, bool)
            or not isinstance(self.maximum_quote_age_seconds, int)
        ):
            raise TypeError("maximum_quote_age_seconds must be int")
        if self.maximum_quote_age_seconds <= 0:
            raise ValueError("maximum_quote_age_seconds must be positive")
