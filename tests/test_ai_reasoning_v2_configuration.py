import pytest

from engines.ai_reasoning_v2 import AIReasoningV2Configuration


def test_defaults_are_frozen_slotted_and_safe():
    config = AIReasoningV2Configuration()
    assert config.very_high_confidence == 0.85
    assert config.high_confidence == 0.70
    assert config.history_limit == 120
    assert hasattr(AIReasoningV2Configuration, "__slots__")
    with pytest.raises(Exception):
        config.history_limit = 1


def test_threshold_and_count_validation():
    with pytest.raises(ValueError):
        AIReasoningV2Configuration(very_high_confidence=0.5, high_confidence=0.7)
    with pytest.raises(ValueError):
        AIReasoningV2Configuration(low_confidence=-0.1)
    with pytest.raises(TypeError):
        AIReasoningV2Configuration(maximum_cautions=True)
    with pytest.raises(ValueError):
        AIReasoningV2Configuration(maximum_watch_conditions=0)
    with pytest.raises(TypeError):
        AIReasoningV2Configuration(include_secondary_confirmations=1)


def test_no_prompt_model_api_or_environment_fields():
    fields = set(AIReasoningV2Configuration.__dataclass_fields__)
    forbidden = ("api", "key", "token", "prompt", "model", "env")
    assert not any(any(word in name.lower() for word in forbidden) for name in fields)
