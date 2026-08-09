"""Approved Pilot v1 infrastructure E2E coverage with no external model client."""

from __future__ import annotations

from pathlib import Path

from inbox2action.evaluation.asset_bundle import (
    EvaluationAssetBundleV1,
    load_evaluation_asset_bundle,
    validate_evaluation_asset_bundle,
)
from inbox2action.evaluation.pilot_fake_model import (
    ApprovedPilotFakeModel,
    approved_pilot_case_ids,
)
from inbox2action.evaluation.runner_v1 import PilotEvaluationRunnerV1

PROJECT_ROOT = Path(__file__).parents[2]


def test_approved_pilot_fake_model_exercises_full_offline_e2e() -> None:
    formal_bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    validate_evaluation_asset_bundle(formal_bundle, require_approved_reviews=True)
    legacy_case_ids = set(approved_pilot_case_ids())
    bundle = EvaluationAssetBundleV1(
        cases=tuple(
            case for case in formal_bundle.cases if case.case_id in legacy_case_ids
        ),
        fixtures=tuple(
            fixture
            for fixture in formal_bundle.fixtures
            if fixture.case_id in legacy_case_ids
        ),
        reviews=tuple(
            review for review in formal_bundle.reviews if review.case_id in legacy_case_ids
        ),
    )
    validate_evaluation_asset_bundle(bundle, require_approved_reviews=True)
    model = ApprovedPilotFakeModel()

    run = PilotEvaluationRunnerV1(
        bundle,
        model,
        require_approved_reviews=True,
        failure_mode="continue",
    ).run()

    assert len(bundle.cases) == 15
    assert len(bundle.fixtures) == 5
    assert tuple(case.case_id for case in bundle.cases) == approved_pilot_case_ids()
    assert len(run.results) == 15
    assert model.triage_completion_count == 15
    assert model.tool_completion_count == 32
    assert model.completion_count == 47
    assert set(model.executed_case_ids) == {case.case_id for case in bundle.cases}

    assert all(result.mode == "injected_model" for result in run.results)
    assert all(result.status != "not_executed" for result in run.results)
    assert all(result.status != "infrastructure_error" for result in run.results)
    assert all(result.approval_gate_passed is True for result in run.results)
    assert all(result.triage_correct is True for result in run.results)
    assert all(result.required_tools_present is True for result in run.results)
    assert all(result.forbidden_tools_absent is True for result in run.results)
    assert all(result.tool_selection_correct is True for result in run.results)
    assert all(result.tool_sequence_correct is True for result in run.results)
    assert all(result.arguments_valid is True for result in run.results)
    assert all(result.fixture_resolution_passed is True for result in run.results)
    assert all(result.safety_passed is True for result in run.results)
    assert all(result.acceptance_passed is True for result in run.results)

    fixture_calls = [
        call
        for result in run.results
        for call in result.tool_calls
        if call.fixture_matched is True
    ]
    assert len(fixture_calls) == 5
    assert all(call.matched_fixture_id is not None for call in fixture_calls)
    calendar_observation_statuses = [
        observed
        for observed in model.observed_tool_statuses
        if observed[0] == "check_calendar_availability"
    ]
    assert calendar_observation_statuses == [
        ("check_calendar_availability", "ok"),
        ("check_calendar_availability", "conflict"),
        ("check_calendar_availability", "ok"),
        ("check_calendar_availability", "conflict"),
        ("check_calendar_availability", "conflict"),
    ]

    assert all(result.unknown_tool_executions == 0 for result in run.results)
    assert all(result.external_side_effects == 0 for result in run.results)
    assert all(result.unauthorized_write_operations == 0 for result in run.results)
    assert all(result.loop_exceeded is False for result in run.results)

    results_by_id = {result.case_id: result for result in run.results}
    for case_id in (
        "injection_secret_send_001",
        "injection_fake_observation_001",
        "injection_loop_bypass_001",
    ):
        assert results_by_id[case_id].forbidden_tool_attempts == 0
    for case_id in (
        "calendar_conflict_001",
        "multi_task_calendar_001",
        "injection_fake_observation_001",
    ):
        result = results_by_id[case_id]
        assert result.requires_replan_after_observation is True
        assert result.requires_user_clarification_after_conflict is True

    serialized = run.model_dump_json()
    assert "reasoning_content" not in serialized
    assert all(
        set(call.model_dump())
        == {
            "step",
            "tool_name",
            "argument_keys",
            "argument_digest",
            "matched_fixture_id",
            "fixture_matched",
            "blocked",
            "error_class",
        }
        for result in run.results
        for call in result.tool_calls
    )
    assert model.persisted_email_bodies == ()
    assert model.persisted_tool_arguments == ()
    assert model.persisted_observations == ()
    assert model.reasoning_contents == ()
    assert model.network_call_count == 0
