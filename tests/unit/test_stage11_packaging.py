from __future__ import annotations

from pathlib import Path

from scripts.run_stage11_acceptance import _static_checks

PROJECT_ROOT = Path(__file__).parents[2]


def test_stage11_static_packaging_contract_is_complete() -> None:
    result = _static_checks()

    assert result["status"] == "PASS"
    assert result["missing_files"] == []
    assert result["missing_env_variables"] == []
    assert result["mermaid"] is True
    assert result["dockerignore_secrets"] is True


def test_compose_keeps_one_migration_service_and_three_runtime_services() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "postgres:" in compose
    assert "migrate:" in compose
    assert "api:" in compose
    assert "worker:" in compose
    assert compose.count("setup_stage4_postgres.py") == 1
    assert "--skip-migrations" in compose
    assert "inbox2action-postgres:" in compose


def test_runtime_entrypoints_support_bounded_and_continuous_worker_modes() -> None:
    worker = (PROJECT_ROOT / "scripts" / "run_stage8_worker.py").read_text(
        encoding="utf-8"
    )
    api = (PROJECT_ROOT / "scripts" / "run_stage8_approval_ui.py").read_text(
        encoding="utf-8"
    )

    assert "--poll-interval-seconds" in worker
    assert "--ready-file" in worker
    assert "--skip-migrations" in worker
    assert "--skip-migrations" in api


def test_docker_context_excludes_runtime_credentials() -> None:
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    for entry in (".env", "runtime.env", "gmail-token.json", "credentials"):
        assert entry in dockerignore


def test_docker_runtime_does_not_sync_as_non_root() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["uv", "run", "--frozen", "--no-sync", "python"]' in dockerfile


def test_compose_seeds_oauth_token_into_a_persistent_writable_volume() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    wrapper = PROJECT_ROOT / "scripts" / "run_stage11_compose_entrypoint.py"

    assert wrapper.exists()
    assert "run_stage11_compose_entrypoint.py" in compose
    assert "inbox2action-google-token" in compose
    assert "gmail-token-source.json" in compose
    assert "GMAIL_TOKEN_PATH: /var/lib/inbox2action/gmail-token.json" in compose
