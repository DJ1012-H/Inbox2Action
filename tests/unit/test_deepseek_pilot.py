from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from inbox2action.config import Settings
from inbox2action.errors import ModelTimeoutError, ModelUnavailableError
from inbox2action.evaluation.asset_bundle import (
    EvaluationAssetConsistencyError,
    load_evaluation_asset_bundle,
    validate_evaluation_asset_bundle,
)
from inbox2action.evaluation.assets import ReviewStatus
from inbox2action.evaluation.deepseek_pilot import (
    PILOT_BASELINE_CASE_IDS,
    PILOT_HOLDOUT_CASE_IDS,
    LivePilotConfigurationError,
    LivePilotRequestError,
    holdout_pilot_decision,
    redacted_pilot_summary,
    render_deepseek_holdout_summary,
    render_deepseek_pilot_summary,
    validate_live_pilot_request,
    validate_live_pilot_settings,
)
from inbox2action.evaluation.runner_v1 import (
    PilotCaseRunResultV1,
    PilotEvaluationRunnerV1,
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


def _holdout_command() -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--live-model",
        "--confirm-api-cost",
        "--suite",
        "holdout10",
    ]


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


def test_live_pilot_accepts_only_the_fixed_ten_case_holdout() -> None:
    assert PILOT_HOLDOUT_CASE_IDS == (
        "ordinary_advertisement_001",
        "ordinary_build_notification_001",
        "task_explicit_deadline_001",
        "task_missing_deadline_001",
        "calendar_explicit_time_001",
        "calendar_ambiguous_time_001",
        "multi_reply_task_001",
        "multi_reply_calendar_001",
        "injection_secret_send_001",
        "injection_loop_bypass_001",
    )
    assert (
        validate_live_pilot_request(
            live_model=True,
            confirm_api_cost=True,
            case_ids=(),
            failure_mode="continue",
            suite="holdout10",
        )
        == PILOT_HOLDOUT_CASE_IDS
    )
    with pytest.raises(LivePilotRequestError):
        validate_live_pilot_request(
            live_model=True,
            confirm_api_cost=True,
            case_ids=("ordinary_advertisement_001",),
            failure_mode="continue",
            suite="holdout10",
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


def test_cli_accepts_holdout_suite_before_model_configuration() -> None:
    environment = os.environ.copy()
    environment.update({"LLM_ENABLED": "true", "LLM_API_KEY": ""})
    result = subprocess.run(
        _holdout_command(),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 2
    assert "LLM_API_KEY" in result.stderr
    assert "holdout10" not in result.stderr


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


def test_holdout_evidence_separates_dataset_roles_and_applies_fixed_decision() -> None:
    results = [
        PilotCaseRunResultV1(
            case_id=case_id,
            mode="injected_model",
            status="completed",
            triage_correct=True,
            tool_selection_correct=True,
            tool_sequence_correct=True,
            arguments_valid=True,
            fixture_resolution_passed=True,
            safety_passed=True,
            acceptance_passed=index < 8,
            external_side_effects=0,
            unknown_tool_executions=0,
            loop_exceeded=False,
            total_tokens=12,
            elapsed_ms=34.5,
        )
        for index, case_id in enumerate(PILOT_HOLDOUT_CASE_IDS)
    ]
    run = PilotEvaluationRunV1(mode="injected_model", results=results)

    evidence = render_deepseek_holdout_summary(
        run, _settings(), run_date=date(2026, 7, 28)
    )

    assert holdout_pilot_decision(run) == "PASS"
    assert "used during Prompt and runtime-contract diagnosis and tuning" in evidence
    assert "not used to adjust the current Prompt before this first run" in evidence
    assert "holdout_accepted_count: `8/10`" in evidence
    assert "measured_case_count: `10/10`" in evidence
    assert "pilot_decision: `PASS`" in evidence
    assert "failure_reasons" in evidence
    assert "email bodies" in evidence
    assert "sensitive-email-body" not in evidence


def test_holdout_decision_fails_closed_on_a_safety_hard_failure() -> None:
    results = [
        PilotCaseRunResultV1(
            case_id=case_id,
            mode="injected_model",
            status="completed",
            triage_correct=True,
            tool_selection_correct=True,
            tool_sequence_correct=True,
            arguments_valid=True,
            fixture_resolution_passed=True,
            safety_passed=index != 0,
            acceptance_passed=index != 0,
            external_side_effects=1 if index == 0 else 0,
            unknown_tool_executions=0,
            loop_exceeded=False,
        )
        for index, case_id in enumerate(PILOT_HOLDOUT_CASE_IDS)
    ]

    assert (
        holdout_pilot_decision(
            PilotEvaluationRunV1(mode="injected_model", results=results)
        )
        == "FAIL"
    )


def test_timeout_is_a_model_invocation_failure_not_an_invalid_triage() -> None:
    class TimeoutModel:
        def complete(self, *args: object, **kwargs: object) -> object:
            raise ModelTimeoutError("test timeout")

    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    run = PilotEvaluationRunnerV1(
        bundle,
        TimeoutModel(),  # type: ignore[arg-type]
        require_approved_reviews=True,
    ).run(case_ids=[PILOT_BASELINE_CASE_IDS[0]])

    result = run.results[0]
    assert result.status == "model_invocation_infrastructure_failure"
    assert result.error_class == "ModelTimeoutError"
    assert result.failure_reasons == ["model_invocation_timeout", "triage_unmeasured"]
    assert result.triage_correct is None
    assert result.acceptance_passed is False


def test_unavailable_is_a_model_invocation_failure_not_an_invalid_triage() -> None:
    class UnavailableModel:
        def complete(self, *args: object, **kwargs: object) -> object:
            raise ModelUnavailableError("test unavailable")

    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    run = PilotEvaluationRunnerV1(
        bundle,
        UnavailableModel(),  # type: ignore[arg-type]
        require_approved_reviews=True,
    ).run(case_ids=[PILOT_BASELINE_CASE_IDS[0]])

    result = run.results[0]
    assert result.status == "model_invocation_infrastructure_failure"
    assert result.error_class == "ModelUnavailableError"
    assert result.failure_reasons == ["model_service_unavailable", "triage_unmeasured"]
    assert result.triage_correct is None
    assert result.acceptance_passed is False


def test_blocked_model_service_run_has_unmeasured_metrics_and_correct_counts() -> None:
    timeout_results = [
        PilotCaseRunResultV1(
            case_id=case_id,
            mode="injected_model",
            status="model_failed",
            acceptance_passed=False,
            error_class="ModelTimeoutError",
            failure_reasons=["triage_invalid"],
        )
        for case_id in PILOT_BASELINE_CASE_IDS[:3]
    ]
    unavailable_results = [
        PilotCaseRunResultV1(
            case_id=case_id,
            mode="injected_model",
            status="model_failed",
            acceptance_passed=False,
            error_class="ModelUnavailableError",
            failure_reasons=["triage_invalid"],
        )
        for case_id in PILOT_BASELINE_CASE_IDS[3:]
    ]
    run = PilotEvaluationRunV1(
        mode="injected_model", results=[*timeout_results, *unavailable_results]
    )

    summary = redacted_pilot_summary(run)
    assert summary["run_status"] == "BLOCKED_BY_MODEL_SERVICE"
    assert summary["accepted_count"] == 0
    assert summary["dataset_infrastructure_error_count"] == 0
    assert summary["model_service_error_count"] == 5
    assert summary["model_timeout_count"] == 3
    assert summary["model_unavailable_count"] == 2
    assert summary["model_invocation_failure_count"] == 5
    assert summary["triage_accuracy"] is None
    assert summary["tool_selection_accuracy"] is None
    assert summary["tool_sequence_accuracy"] is None
    assert summary["arguments_valid_rate"] is None
    assert summary["fixture_resolution_rate"] is None
    assert summary["tool_boundary_safety_pass_rate"] is None
    assert summary["average_latency_ms"] is None
    assert summary["total_tokens"] == 0
    assert summary["token_usage_status"] == "no usage was reported"

    evidence = render_deepseek_pilot_summary(
        run, _settings(), run_date=date(2026, 7, 28)
    )
    assert "run_status: `BLOCKED_BY_MODEL_SERVICE`" in evidence
    assert "triage_accuracy: `unmeasured`" in evidence
    assert "average_latency_ms: `unmeasured`" in evidence
    assert "0.0" not in evidence
    assert "no usage was reported" in evidence
    assert "triage_invalid" not in evidence
    assert "model_invocation_timeout, triage_unmeasured" in evidence
    assert "model_service_unavailable, triage_unmeasured" in evidence
