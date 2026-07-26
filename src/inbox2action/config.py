from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated, non-leaking runtime settings for the model probe."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    llm_enabled: bool = Field(False, validation_alias="LLM_ENABLED")
    llm_base_url: str = Field(
        "https://api.deepseek.com",
        validation_alias="LLM_BASE_URL",
    )
    llm_api_key: SecretStr | None = Field(None, validation_alias="LLM_API_KEY")
    llm_model_name: str = Field(
        "deepseek-v4-flash",
        validation_alias="LLM_MODEL_NAME",
    )
    llm_thinking_mode: Literal["disabled", "enabled"] = Field(
        "disabled",
        validation_alias="LLM_THINKING_MODE",
    )
    llm_timeout_seconds: float = Field(
        30.0,
        gt=0,
        le=120,
        validation_alias="LLM_TIMEOUT_SECONDS",
    )
    llm_max_retries: int = Field(
        0,
        ge=0,
        le=3,
        validation_alias="LLM_MAX_RETRIES",
    )
    llm_max_tokens: int = Field(
        2048,
        gt=0,
        le=32768,
        validation_alias="LLM_MAX_TOKENS",
    )
    llm_max_tool_steps: int = Field(
        6,
        gt=0,
        le=20,
        validation_alias="LLM_MAX_TOOL_STEPS",
    )
    run_deepseek_integration_tests: bool = Field(
        False,
        validation_alias="RUN_DEEPSEEK_INTEGRATION_TESTS",
    )

    @field_validator("llm_base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https":
            raise ValueError("LLM_BASE_URL must use HTTPS")
        if parsed.hostname != "api.deepseek.com":
            raise ValueError("LLM_BASE_URL host is not allowed")
        if parsed.username or parsed.password or parsed.port is not None:
            raise ValueError("LLM_BASE_URL must not contain credentials or a port")
        if parsed.query or parsed.fragment:
            raise ValueError("LLM_BASE_URL must not contain a query or fragment")
        return value.rstrip("/")

    @field_validator("llm_model_name")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        if value != "deepseek-v4-flash":
            raise ValueError("only deepseek-v4-flash is allowed in stage two")
        return value

    @property
    def api_key_value(self) -> str | None:
        """Return the key only for the internal SDK construction boundary."""

        if self.llm_api_key is None:
            return None
        return self.llm_api_key.get_secret_value() or None

    @property
    def api_key_configured(self) -> bool:
        return self.api_key_value is not None
