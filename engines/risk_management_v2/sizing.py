"""
Position sizing for Risk Management Engine V2.
"""

from math import floor

from engines.risk_management_v2.configuration import RiskManagementV2Configuration
from engines.risk_management_v2.models import PositionSizeRecommendation, RiskManagementV2Input


class PositionSizeCalculator:
    def calculate(
        self,
        inputs: RiskManagementV2Input,
        configuration: RiskManagementV2Configuration,
        *,
        risk_multiplier: float = 1.0,
    ) -> PositionSizeRecommendation:
        risk_distance = abs(inputs.proposed_entry_price - inputs.proposed_invalidation_price)
        risk_per_unit = risk_distance * inputs.contract_multiplier
        requested = inputs.account.current_equity * configuration.risk_per_trade_fraction
        maximum = inputs.account.current_equity * configuration.maximum_risk_per_trade_fraction
        approved_risk = min(requested * risk_multiplier, maximum, inputs.account.available_capital)
        raw_quantity = approved_risk / risk_per_unit
        rounded_quantity = floor(raw_quantity / inputs.quantity_step) * inputs.quantity_step
        total_quantity_cap = _quantity_capacity(
            inputs.account.current_equity * configuration.maximum_total_exposure_fraction
            - inputs.account.current_total_exposure,
            inputs,
        )
        instrument_quantity_cap = _quantity_capacity(
            inputs.account.current_equity * configuration.maximum_instrument_exposure_fraction
            - inputs.instrument_exposure.current_notional_exposure,
            inputs,
        )
        capital_quantity_cap = _quantity_capacity(inputs.account.available_capital, inputs)
        capped_quantity = max(
            0,
            min(
                rounded_quantity,
                configuration.maximum_position_quantity,
                total_quantity_cap,
                instrument_quantity_cap,
                capital_quantity_cap,
            ),
        )
        final_quantity = floor(capped_quantity / inputs.quantity_step) * inputs.quantity_step
        if final_quantity < configuration.minimum_position_quantity:
            final_quantity = 0
        return PositionSizeRecommendation(
            requested_risk_amount=requested,
            approved_risk_amount=final_quantity * risk_per_unit,
            risk_per_unit=risk_per_unit,
            raw_quantity=raw_quantity,
            rounded_quantity=rounded_quantity,
            capped_quantity=capped_quantity,
            final_quantity=final_quantity,
            quantity_step=inputs.quantity_step,
            contract_multiplier=inputs.contract_multiplier,
            reduced=final_quantity < rounded_quantity,
        )


def _quantity_capacity(amount: float, inputs: RiskManagementV2Input) -> int:
    if amount <= 0.0:
        return 0
    unit_notional = inputs.proposed_entry_price * inputs.contract_multiplier
    return floor((amount / unit_notional) / inputs.quantity_step) * inputs.quantity_step
