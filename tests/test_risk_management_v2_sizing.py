from engines.risk_management_v2 import PositionSizeCalculator
from tests.test_risk_management_v2_calculator import account, config, exposure, risk_input


def size(inputs=None, configuration=None, risk_multiplier=1.0):
    return PositionSizeCalculator().calculate(
        inputs or risk_input(),
        configuration or config(),
        risk_multiplier=risk_multiplier,
    )


def test_basic_fixed_fraction_risk_per_unit_and_round_down():
    result = size()

    assert result.requested_risk_amount == 50.0
    assert result.risk_per_unit == 50.0
    assert result.raw_quantity == 1.0
    assert result.rounded_quantity == 1
    assert result.final_quantity == 1


def test_quantity_step_and_never_rounds_up():
    result = size(risk_input(quantity_step=2, proposed_invalidation_price=83.0, proposed_objective_price=148.0))

    assert result.raw_quantity == 2.0
    assert result.final_quantity == 2
    smaller = size(risk_input(quantity_step=2))
    assert smaller.raw_quantity == 1.0
    assert smaller.final_quantity == 0


def test_maximum_cap_capital_total_and_instrument_exposure_caps():
    base = risk_input(proposed_invalidation_price=83.0, proposed_objective_price=148.0)
    capped = size(base, config(maximum_position_quantity=1))
    capital = size(risk_input(account=account(available_capital=120.0), proposed_invalidation_price=83.0, proposed_objective_price=148.0))
    total = size(risk_input(account=account(current_total_exposure=2380.0), proposed_invalidation_price=83.0, proposed_objective_price=148.0))
    instrument = size(risk_input(instrument_exposure=exposure(current_notional_exposure=880.0), proposed_invalidation_price=83.0, proposed_objective_price=148.0))

    assert capped.final_quantity == 1
    assert capital.final_quantity == 1
    assert total.final_quantity == 1
    assert instrument.final_quantity == 1
    assert all(item.reduced for item in (capped, capital, total, instrument))


def test_reduced_multiplier_and_zero_valid_quantity_without_broker_calls():
    reduced = size(
        risk_input(proposed_invalidation_price=83.0, proposed_objective_price=148.0),
        risk_multiplier=0.5,
    )
    zero = size(risk_input(account=account(available_capital=10.0)))

    assert reduced.final_quantity == 1
    assert reduced.approved_risk_amount < reduced.requested_risk_amount
    assert zero.final_quantity == 0
