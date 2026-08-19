from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

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
        "clickup_enabled": False,
        "clickup_api_token": None,
        "clickup_list_id": None,
        "clickup_timeout_seconds": 10,
        "run_clickup_integration_tests": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_clickup_defaults_are_disabled_and_unconfigured() -> None:
    settings = make_settings()

    assert settings.clickup_enabled is False
    assert settings.clickup_api_token is None
    assert settings.clickup_list_id is None
    assert settings.clickup_timeout_seconds == 10
    assert settings.run_clickup_integration_tests is False
    assert settings.clickup_api_token_configured is False


def test_clickup_token_uses_secretstr_and_never_appears_in_repr() -> None:
    token = "cu-secret-placeholder"
    settings = make_settings(clickup_api_token=token)

    assert isinstance(settings.clickup_api_token, SecretStr)
    assert settings.clickup_api_token_value == token
    assert settings.clickup_api_token_configured is True
    assert token not in repr(settings)


def test_blank_clickup_credentials_are_unset() -> None:
    settings = make_settings(clickup_api_token="", clickup_list_id="  ")

    assert settings.clickup_api_token is None
    assert settings.clickup_list_id is None
    assert settings.clickup_api_token_value is None


def test_clickup_list_id_is_normalized_as_a_string() -> None:
    settings = make_settings(clickup_list_id=" 123456 ")

    assert settings.clickup_list_id == "123456"
    assert isinstance(settings.clickup_list_id, str)


@pytest.mark.parametrize("list_id", ["123x", "-123", "12.3", "１２３"])
def test_non_numeric_clickup_list_id_is_rejected(list_id: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(clickup_list_id=list_id)


@pytest.mark.parametrize("timeout", [0, -1, 30.1, 31])
def test_clickup_timeout_has_safe_bounds(timeout: float) -> None:
    with pytest.raises(ValidationError):
        make_settings(clickup_timeout_seconds=timeout)


def test_clickup_timeout_accepts_positive_value_at_or_below_thirty() -> None:
    assert make_settings(clickup_timeout_seconds=30).clickup_timeout_seconds == 30
