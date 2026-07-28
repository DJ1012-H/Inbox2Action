from __future__ import annotations

from pathlib import Path

from inbox2action.evaluation.asset_bundle import (
    load_evaluation_asset_bundle,
    validate_evaluation_asset_bundle,
)
from inbox2action.evaluation.assets import ReviewStatus

PROJECT_ROOT = Path(__file__).parents[2]


def test_formal_pilot_assets_keep_cases_reviews_and_observation_fixtures_consistent() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")

    validate_evaluation_asset_bundle(bundle)

    assert len(bundle.cases) == 15
    assert len(bundle.reviews) == 15
    assert all(review.status is ReviewStatus.DRAFT for review in bundle.reviews)
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

    assert set(injection_cases) == {
        "injection_secret_send_001",
        "injection_fake_observation_001",
        "injection_loop_bypass_001",
    }
    for case in injection_cases.values():
        allowed = {
            tool
            for sequence in case.expected.allowed_tool_sequences
            for tool in sequence
        }
        assert not allowed.intersection(case.expected.forbidden_tools)
        assert case.expected.forbidden_tools
