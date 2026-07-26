from __future__ import annotations

import pytest

from inbox2action.evaluation.asset_bundle import EvaluationAssetBundleV1
from inbox2action.evaluation.assets import EvaluationCaseV1, ToolFixtureV1
from inbox2action.evaluation.fixture_matcher import (
    ToolFixtureAmbiguousError,
    ToolFixtureMatcherV1,
    ToolFixtureNotFoundError,
    UnknownEvaluationCaseError,
)


def make_case(fixture_ids: list[str]) -> EvaluationCaseV1:
    return EvaluationCaseV1.model_validate(
        {
            "schema_version": "1.0",
            "dataset_version": "deepseek-validation-v1",
            "case_id": "case-001",
            "category": "task",
            "subcategory": "synthetic",
            "language": "en",
            "current_time": "2026-07-26T09:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "email": {
                "from": "sender@example.com",
                "subject": "Synthetic task",
                "body": "Synthetic test message only.",
            },
            "user_context": {},
            "expected": {
                "triage": "ACTION_REQUIRED",
                "required_tools": ["get_current_time"],
                "allowed_tool_sequences": [["get_current_time", "done"]],
                "forbidden_tools": [],
                "argument_assertions": {},
                "safety": {},
            },
            "tool_fixture_ids": fixture_ids,
        }
    )


def make_fixture(
    fixture_id: str = "fixture-001", arguments: dict[str, object] | None = None
) -> ToolFixtureV1:
    return ToolFixtureV1.model_validate(
        {
            "schema_version": "1.0",
            "dataset_version": "deepseek-validation-v1",
            "fixture_id": fixture_id,
            "case_id": "case-001",
            "tool_name": "get_current_time",
            "arguments_match": arguments or {},
            "observation": {"kind": "synthetic", "nested": {"value": 1}},
        }
    )


def matcher_with_fixture(arguments: dict[str, object]) -> ToolFixtureMatcherV1:
    case = make_case(["fixture-001"])
    fixture = make_fixture(arguments=arguments)
    return ToolFixtureMatcherV1(
        EvaluationAssetBundleV1(cases=(case,), fixtures=(fixture,), reviews=())
    )


def test_matches_exact_fixture_with_dictionary_key_order_independence() -> None:
    matcher = matcher_with_fixture({"a": 1, "b": {"c": "value"}})
    fixture = matcher.match(
        case_id="case-001", tool_name="get_current_time", arguments={"b": {"c": "value"}, "a": 1}
    )
    assert fixture.fixture_id == "fixture-001"


@pytest.mark.parametrize(
    "arguments",
    [
        {"items": [2, 1]},
        {"value": "1"},
        {"value": True},
        {"value": 1.0},
    ],
)
def test_does_not_coerce_or_reorder_exact_arguments(arguments: dict[str, object]) -> None:
    matcher = matcher_with_fixture({"items": [1, 2], "value": 1})
    with pytest.raises(ToolFixtureNotFoundError) as captured:
        matcher.match(case_id="case-001", tool_name="get_current_time", arguments=arguments)
    assert str(arguments) not in str(captured.value)


def test_reports_unknown_case_and_missing_fixture_without_arguments() -> None:
    matcher = matcher_with_fixture({"value": 1})
    with pytest.raises(UnknownEvaluationCaseError, match="case-404"):
        matcher.match(case_id="case-404", tool_name="get_current_time", arguments={"value": 1})
    with pytest.raises(ToolFixtureNotFoundError) as captured:
        matcher.match(case_id="case-001", tool_name="get_current_time", arguments={"private": "body"})
    assert "private" not in str(captured.value)


def test_reports_ambiguous_matches_and_returns_a_deep_copy() -> None:
    case = make_case(["fixture-001", "fixture-002"])
    matcher = ToolFixtureMatcherV1(
        EvaluationAssetBundleV1(
            cases=(case,),
            fixtures=(make_fixture(), make_fixture("fixture-002")),
            reviews=(),
        )
    )
    with pytest.raises(ToolFixtureAmbiguousError):
        matcher.match(case_id="case-001", tool_name="get_current_time", arguments={})

    exact = matcher_with_fixture({})
    observation = exact.get_observation(case_id="case-001", tool_name="get_current_time", arguments={})
    nested = observation["nested"]
    assert isinstance(nested, dict)
    nested["value"] = 9
    original = exact.match(case_id="case-001", tool_name="get_current_time", arguments={})
    assert original.observation["nested"] == {"value": 1}
