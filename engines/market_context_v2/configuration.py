"""
Configuration for Market Context Engine V2.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarketContextV2Configuration:
    price_action_weight: int = 4
    option_chain_weight: int = 4
    camarilla_weight: int = 2
    cpr_weight: int = 2
    vwap_weight: int = 1

    strong_direction_score: int = 6
    minimum_direction_score: int = 2
    high_conflict_score: int = 4

    minimum_primary_sources: int = 1
    require_price_action_or_option_chain: bool = True

    allow_partial_secondary_inputs: bool = True
    neutralize_on_primary_conflict: bool = True
    history_limit: int = 120

    def __post_init__(self) -> None:
        weights = (
            "price_action_weight",
            "option_chain_weight",
            "camarilla_weight",
            "cpr_weight",
            "vwap_weight",
        )
        for name in weights:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be a positive integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")

        secondary = (
            self.camarilla_weight,
            self.cpr_weight,
            self.vwap_weight,
        )
        if self.price_action_weight < max(secondary):
            raise ValueError("price_action_weight must preserve primary hierarchy")
        if self.option_chain_weight < max(secondary):
            raise ValueError("option_chain_weight must preserve primary hierarchy")

        for name in (
            "strong_direction_score",
            "minimum_direction_score",
            "high_conflict_score",
            "history_limit",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be a positive integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")

        if self.strong_direction_score <= self.minimum_direction_score:
            raise ValueError(
                "strong_direction_score must exceed minimum_direction_score"
            )
        if self.minimum_primary_sources not in (1, 2):
            raise ValueError("minimum_primary_sources must be 1 or 2")
        for name in (
            "require_price_action_or_option_chain",
            "allow_partial_secondary_inputs",
            "neutralize_on_primary_conflict",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
