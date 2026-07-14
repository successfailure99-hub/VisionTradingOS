import pytest

from engines.position_management_v1 import PositionManagementV1Configuration


def test_defaults_are_conservative_and_offline():
    cfg = PositionManagementV1Configuration()
    assert cfg.auto_exit_on_invalidation is True
    assert cfg.auto_partial_exit_on_objective is False
    assert cfg.auto_full_exit_on_objective is False
    assert not any("broker" in field or "credential" in field or "order" in field for field in cfg.__dataclass_fields__)


def test_boolean_fraction_conflict_and_integer_validation():
    with pytest.raises(TypeError):
        PositionManagementV1Configuration(allow_partial_exit=1)
    with pytest.raises(ValueError):
        PositionManagementV1Configuration(partial_exit_fraction=1.0)
    with pytest.raises(ValueError):
        PositionManagementV1Configuration(auto_partial_exit_on_objective=True, auto_full_exit_on_objective=True)
    with pytest.raises(TypeError):
        PositionManagementV1Configuration(history_limit=True)
    with pytest.raises(ValueError):
        PositionManagementV1Configuration(minimum_remaining_quantity=0)
