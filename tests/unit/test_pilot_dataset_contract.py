from __future__ import annotations

from pathlib import Path

from inbox2action.evaluation.asset_bundle import (
    load_evaluation_asset_bundle,
    validate_evaluation_asset_bundle,
)
from inbox2action.evaluation.assets import ReviewStatus

PROJECT_ROOT = Path(__file__).parents[2]


def test_approved_pilot_assets_keep_cases_reviews_and_observation_fixtures_consistent() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")

    validate_evaluation_asset_bundle(bundle, require_approved_reviews=True)

    assert len(bundle.cases) == 60
    assert len(bundle.reviews) == 60
    assert {case.category.value for case in bundle.cases} == {
        "ordinary",
        "task",
        "calendar",
        "multi_action",
        "prompt_injection",
    }
    assert {
        category: sum(case.category.value == category for case in bundle.cases)
        for category in {case.category.value for case in bundle.cases}
    } == {
        "ordinary": 12,
        "task": 12,
        "calendar": 12,
        "multi_action": 12,
        "prompt_injection": 12,
    }
    assert all(review.status is ReviewStatus.APPROVED for review in bundle.reviews)
    assert len(bundle.fixtures) == 20
    assert {fixture.tool_name for fixture in bundle.fixtures} == {
        "check_calendar_availability"
    }
    fixture_ids = {fixture.fixture_id for fixture in bundle.fixtures}
    assert all(
        fixture_id in fixture_ids
        for case in bundle.cases
        for fixture_id in case.tool_fixture_ids
    )


def test_prompt_injection_cases_keep_dangerous_tools_out_of_gold_sequences() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    injection_cases = {
        case.case_id: case
        for case in bundle.cases
        if case.category.value == "prompt_injection"
    }

    assert len(injection_cases) == 12
    assert {
        case_id.rsplit("_", maxsplit=1)[-1] for case_id in injection_cases
    } == {f"{index:03d}" for index in range(1, 11)}
    for case in injection_cases.values():
        allowed = {
            tool
            for sequence in case.expected.allowed_tool_sequences
            for tool in sequence
        }
        assert not allowed.intersection(case.expected.forbidden_tools)
        assert case.expected.forbidden_tools
