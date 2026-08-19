from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def runtime_env_path() -> Path:
    """Return the single external runtime configuration path for this user."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    base_path = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    return base_path / "Inbox2Action" / "secrets" / "runtime.env"


_DEFAULT_RUNTIME_ENV_PATH = runtime_env_path()


def resolve_configured_path(
    explicit: str | Path | None,
    configured: Path | None,
    *,
    setting_name: str,
) -> Path:
    """Resolve a CLI path over a configured external path without discovery."""

    value = explicit if explicit is not None else configured
    if value is None or not str(value).strip():
        raise ValueError(f"{setting_name} must be configured or provided explicitly")
    return Path(value).expanduser()


class Settings(BaseSettings):
    """Validated, non-leaking runtime settings for the model probe."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=_DEFAULT_RUNTIME_ENV_PATH,
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
        120.0,
        gt=0,
        le=120,
        validation_alias="LLM_TIMEOUT_SECONDS",
    )
    llm_max_retries: int = Field(
        1,
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
    database_url: SecretStr | None = Field(
        default=None,
        validation_alias="INBOX2ACTION_DATABASE_URL",
    )
    gmail_client_secrets_path: Path | None = Field(
        default=None,
        validation_alias="GMAIL_CLIENT_SECRETS_PATH",
    )
    gmail_token_path: Path | None = Field(
        default=None,
        validation_alias="GMAIL_TOKEN_PATH",
    )
    clickup_enabled: bool = Field(False, validation_alias="CLICKUP_ENABLED")
    clickup_api_token: SecretStr | None = Field(
        default=None,
        validation_alias="CLICKUP_API_TOKEN",
    )
    clickup_list_id: str | None = Field(
        default=None,
        validation_alias="CLICKUP_LIST_ID",
    )
    clickup_timeout_seconds: float = Field(
        10.0,
        gt=0,
        le=30,
        validation_alias="CLICKUP_TIMEOUT_SECONDS",
    )
    run_clickup_integration_tests: bool = Field(
        False,
        validation_alias="RUN_CLICKUP_INTEGRATION_TESTS",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Keep process env precedence while resolving LOCALAPPDATA at runtime."""

        configured_env_file = getattr(dotenv_settings, "env_file", None)
        if configured_env_file == _DEFAULT_RUNTIME_ENV_PATH:
            dotenv_settings = DotEnvSettingsSource(
                settings_cls,
                env_file=runtime_env_path(),
                env_file_encoding="utf-8",
            )
        return init_settings, env_settings, dotenv_settings, file_secret_settings

    @field_validator(
        "database_url",
        "gmail_client_secrets_path",
        "gmail_token_path",
        "clickup_api_token",
        "clickup_list_id",
        mode="before",
    )
    @classmethod
    def blank_values_are_unset(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("clickup_list_id")
    @classmethod
    def validate_clickup_list_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized.isascii() or not normalized.isdigit():
            raise ValueError("CLICKUP_LIST_ID must contain only ASCII digits")
        return normalized

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

    @property
    def database_url_value(self) -> str | None:
        """Return the database URL only at the database connection boundary."""

        if self.database_url is None:
            return None
        return self.database_url.get_secret_value() or None

    @property
    def clickup_api_token_value(self) -> str | None:
        """Return the ClickUp token only at the provider construction boundary."""

        if self.clickup_api_token is None:
            return None
        return self.clickup_api_token.get_secret_value() or None

    @property
    def clickup_api_token_configured(self) -> bool:
        return self.clickup_api_token_value is not None
