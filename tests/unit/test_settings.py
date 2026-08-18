from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from inbox2action.config import Settings, resolve_configured_path


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


def test_external_runtime_env_is_loaded_and_process_env_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "LocalAppData"
    runtime_env = local_app_data / "Inbox2Action" / "secrets" / "runtime.env"
    runtime_env.parent.mkdir(parents=True)
    runtime_env.write_text(
        """LLM_ENABLED=true
LLM_API_KEY=runtime-secret
LLM_BASE_URL=https://api.deepseek.com
INBOX2ACTION_DATABASE_URL=postgresql://user:runtime-password@localhost/db
GMAIL_CLIENT_SECRETS_PATH=C:/external/gmail-client.json
GMAIL_TOKEN_PATH=C:/external/gmail-token.json
""",
        encoding="utf-8",
    )
    for name in (
        "LLM_ENABLED",
        "LLM_API_KEY",
        "INBOX2ACTION_DATABASE_URL",
        "GMAIL_CLIENT_SECRETS_PATH",
        "GMAIL_TOKEN_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    settings = Settings()

    assert settings.llm_enabled is True
    assert settings.api_key_value == "runtime-secret"
    assert settings.database_url_value == (
        "postgresql://user:runtime-password@localhost/db"
    )
    assert settings.gmail_client_secrets_path == Path("C:/external/gmail-client.json")
    assert settings.gmail_token_path == Path("C:/external/gmail-token.json")
    assert "runtime-secret" not in repr(settings)
    assert "runtime-password" not in repr(settings)

    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "process-secret")
    monkeypatch.setenv(
        "INBOX2ACTION_DATABASE_URL",
        "postgresql://user:process-password@localhost/db",
    )
    overridden = Settings()

    assert overridden.llm_enabled is False
    assert overridden.api_key_value == "process-secret"
    assert overridden.database_url_value == (
        "postgresql://user:process-password@localhost/db"
    )
    assert "process-secret" not in repr(overridden)
    assert "process-password" not in repr(overridden)


def test_missing_runtime_env_uses_safe_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "missing-local-app-data"))
    for name in (
        "LLM_ENABLED",
        "LLM_API_KEY",
        "INBOX2ACTION_DATABASE_URL",
        "GMAIL_CLIENT_SECRETS_PATH",
        "GMAIL_TOKEN_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.llm_enabled is False
    assert settings.api_key_configured is False
    assert settings.database_url_value is None
    assert settings.gmail_client_secrets_path is None
    assert settings.gmail_token_path is None


def test_explicit_gmail_path_overrides_configured_path(tmp_path: Path) -> None:
    configured = tmp_path / "configured.json"
    explicit = tmp_path / "explicit.json"

    assert resolve_configured_path(
        explicit,
        configured,
        setting_name="GMAIL_CLIENT_SECRETS_PATH or --client-secrets",
    ) == explicit
    assert resolve_configured_path(
        None,
        configured,
        setting_name="GMAIL_CLIENT_SECRETS_PATH or --client-secrets",
    ) == configured
    with pytest.raises(ValueError, match="must be configured"):
        resolve_configured_path(
            None,
            None,
            setting_name="GMAIL_CLIENT_SECRETS_PATH or --client-secrets",
        )


def test_stage6_worker_parser_uses_settings_for_optional_gmail_paths() -> None:
    script_path = Path(__file__).parents[2] / "scripts" / "run_stage6_worker.py"
    spec = importlib.util.spec_from_file_location("stage6_worker_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = module.build_parser().parse_args(["--max-messages", "1"])

    assert args.client_secrets is None
    assert args.token_path is None
    assert args.max_messages == 1
