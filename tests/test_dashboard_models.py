"""
Tests for dashboard presentation models.
"""

from dataclasses import FrozenInstanceError, fields

import pytest

from dashboard.models import (
    DashboardAIView,
    DashboardJournalView,
    DashboardMarketView,
    DashboardPositionView,
    DashboardRuntimeView,
    DashboardStrategyView,
    DashboardView,
)


def test_presentation_models_are_frozen():
    view = DashboardRuntimeView("Created", "Dry Run", "Analysis Only", ("NIFTY",), False, False, 0, 0, 0, None, None, None)
    with pytest.raises(FrozenInstanceError):
        view.application_status = "Running"


def test_models_accept_optional_values_and_tuples_are_immutable():
    runtime = DashboardRuntimeView("Created", "Dry Run", "Analysis Only", ("NIFTY",), False, False, 0, 0, 0, None, None, None)
    market = DashboardMarketView("NIFTY", "1m", "Created", None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, "-", "-", "-", "-", None)
    ai = DashboardAIView("NIFTY", "-", "-", "-", "-", "-", "-", ())
    strategy = DashboardStrategyView("NIFTY", "-", "-", "-", "-", "-", "-", "-", "-", None, None, None, "-")
    position = DashboardPositionView("NIFTY", False, "-", None, None, None, None, None, None, None)
    journal = DashboardJournalView("NIFTY", None, "-", None, None, None)
    dashboard = DashboardView(runtime, (market,), (ai,), (strategy,), (position,), (journal,))
    assert dashboard.markets == (market,)
    assert isinstance(dashboard.markets, tuple)


def test_models_do_not_contain_engine_objects():
    runtime = DashboardRuntimeView("Created", "Dry Run", "Analysis Only", ("NIFTY",), False, False, 0, 0, 0, None, None, None)
    values = tuple(getattr(runtime, field.name) for field in fields(runtime))
    assert all("Engine" not in type(value).__name__ for value in values)
