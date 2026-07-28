from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from inbox2action.config import Settings
from inbox2action.evaluation.asset_bundle import (
    EvaluationAssetConsistencyError,
    load_evaluation_asset_bundle,
    validate_evaluation_asset_bundle,
)
from inbox2action.evaluation.assets import ReviewStatus
from inbox2action.evaluation.deepseek_pilot import (
    PILOT_BASELINE_CASE_IDS,
    LivePilotConfigurationError,
    LivePilotRequestError,
    render_deepseek_pilot_summary,
    validate_live_pilot_request,
    validate_live_pilot_settings,
)
from inbox2action.evaluation.runner_v1 import (
    PilotCaseRunResultV1,
    PilotEvaluationRunV1,
)

PROJECT_ROOT = Path(__file__).parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "run_deepseek_pilot.py"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "llm_enabled": True,
        "llm_api_key": "placeholder-only",
        "llm_base_url": "https://api.deepseek.com",
        "llm_model_name": "deepseek-v4-flash",
        "llm_thinking_mode": "disabled",
    }
    values.update(overrides)
    return Settings(**values)


def _live_command(*case_ids: str) -> list[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--live-model",
        "--confirm-api-cost",
    ]
    for case_id in case_ids:
        command.extend(("--case-id", case_id))
    return command


def test_live_pilot_requires_both_explicit_authorization_flags() -> None:
    with pytest.raises(LivePilotRequestError):
        validate_live_pilot_request(
            live_model=False,
            confirm_api_cost=True,
            case_ids=PILOT_BASELINE_CASE_IDS,
            failure_mode="continue",
        )
    with pytest.raises(LivePilotRequestError):
        validate_live_pilot_request(
            live_model=True,
            confirm_api_cost=False,
            case_ids=PILOT_BASELINE_CASE_IDS,
            failure_mode="continue",
        )


def test_live_pilot_accepts_only_the_fixed_five_case_baseline() -> None:
    assert (
        validate_live_pilot_request(
            live_model=True,
            confirm_api_cost=True,
            case_ids=PILOT_BASELINE_CASE_IDS,
            failure_mode="continue",
        )
        == PILOT_BASELINE_CASE_IDS
    )
    with pytest.raises(LivePilotRequestError):
        validate_live_pilot_request(
            live_model=True,
            confirm_api_cost=True,
            case_ids=(*PILOT_BASELINE_CASE_IDS, "ordinary_advertisement_001"),
            failure_mode="continue",
        )


def test_missing_api_key_fails_before_client_construction() -> None:
    with pytest.raises(LivePilotConfigurationError) as exc_info:
        validate_live_pilot_settings(_settings(llm_api_key=None))
    assert exc_info.value.missing == ("LLM_API_KEY",)


def test_unapproved_review_fails_before_a_model_can_be_constructed() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    changed_review = bundle.reviews[0].model_copy(update={"status": ReviewStatus.DRAFT})
    changed_bundle = bundle.model_copy(
        update={"reviews": (changed_review, *bundle.reviews[1:])}
    )
    with pytest.raises(EvaluationAssetConsistencyError):
        validate_evaluation_asset_bundle(changed_bundle, require_approved_reviews=True)


def test_cli_refuses_before_settings_or_network_when_authorization_is_missing() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], check=False, capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "--live-model" in result.stderr


def test_cli_rejects_an_unknown_case_before_model_configuration() -> None:
    result = subprocess.run(
        _live_command("unknown_case_id"), check=False, capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "five documented" in result.stderr


def test_cli_reports_only_missing_configuration_name() -> None:
    environment = os.environ.copy()
    environment.update({"LLM_ENABLED": "true", "LLM_API_KEY": ""})
    result = subprocess.run(
        _live_command(*PILOT_BASELINE_CASE_IDS),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 2
    assert "LLM_API_KEY" in result.stderr
    assert "Authorization" not in result.stderr


def test_evidence_is_redacted_and_covers_the_required_result_fields() -> None:
    run = PilotEvaluationRunV1(
        mode="injected_model",
        results=[
            PilotCaseRunResultV1(
                case_id=PILOT_BASELINE_CASE_IDS[0],
                mode="injected_model",
                status="completed",
                triage_correct=True,
                tool_selection_correct=True,
                tool_sequence_correct=True,
                arguments_valid=True,
                fixture_resolution_passed=True,
                safety_passed=True,
                acceptance_passed=True,
                total_tokens=12,
                elapsed_ms=34.5,
            )
        ],
    )
    evidence = render_deepseek_pilot_summary(
        run, _settings(), run_date=date(2026, 7, 28)
    )
    assert "ordinary_simple_confirmation_001" in evidence
    assert "accepted_count" in evidence
    assert "Tool arguments" in evidence
    assert "reasoning_content" in evidence
    assert "sensitive-email-body" not in evidence
    assert "complete-observation-payload" not in evidence
