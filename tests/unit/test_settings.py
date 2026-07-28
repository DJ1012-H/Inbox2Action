from __future__ import annotations

import pytest
from pydantic import ValidationError

from inbox2action.config import Settings


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "llm_enabled": False,
        "llm_base_url": "https://api.deepseek.com",
        "llm_model_name": "deepseek-v4-flash",
        "llm_thinking_mode": "disabled",
        "llm_timeout_seconds": 120,
        "llm_max_retries": 1,
        "llm_max_tokens": 2048,
        "llm_max_tool_steps": 6,
        "run_deepseek_integration_tests": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_defaults_disable_network_and_mask_key() -> None:
    settings = make_settings(llm_api_key="placeholder-value-only")

    assert settings.llm_enabled is False
    assert settings.llm_model_name == "deepseek-v4-flash"
    assert settings.llm_max_retries == 1
    assert settings.api_key_configured is True
    assert "placeholder-value-only" not in repr(settings)


@pytest.mark.parametrize(
    "field,value",
    [
        ("llm_base_url", "http://api.deepseek.com"),
        ("llm_base_url", "https://example.invalid"),
        ("llm_base_url", "https://api.deepseek.com:443"),
        ("llm_timeout_seconds", 0),
        ("llm_timeout_seconds", 121),
        ("llm_max_tokens", 0),
        ("llm_max_tokens", 32769),
        ("llm_max_tool_steps", 0),
        ("llm_model_name", "another-model"),
    ],
)
def test_invalid_settings_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{field: value})
