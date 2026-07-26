from __future__ import annotations

import pytest

from inbox2action.evaluation.asset_bundle import EvaluationAssetBundleV1
from inbox2action.evaluation.assets import EvaluationCaseV1, ToolFixtureV1
from inbox2action.evaluation.fixture_matcher import ToolFixtureMatcherV1
from inbox2action.evaluation.fixture_runtime import (
    FixtureBackedToolRuntimeV1,
    FixtureNotFoundRuntimeError,
)
from inbox2action.tools.schemas import NoArguments


def case() -> EvaluationCaseV1:
    return EvaluationCaseV1.model_validate(
        {
            "schema_version": "1.0", "dataset_version": "deepseek-validation-v1",
            "case_id": "case-001", "category": "task", "subcategory": "synthetic",
            "language": "en", "current_time": "2026-07-26T09:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "email": {"from": "sender@example.com", "subject": "Synthetic", "body": "Synthetic body."},
            "user_context": {},
            "expected": {"triage": "ACTION_REQUIRED", "required_tools": ["get_current_time"], "allowed_tool_sequences": [["get_current_time", "done"]], "forbidden_tools": [], "argument_assertions": {"get_current_time": {}}, "safety": {}},
            "tool_fixture_ids": ["fixture-001"],
        }
    )


def fixture() -> ToolFixtureV1:
    return ToolFixtureV1.model_validate(
        {
            "schema_version": "1.0", "dataset_version": "deepseek-validation-v1",
            "fixture_id": "fixture-001", "case_id": "case-001", "tool_name": "get_current_time",
            "arguments_match": {},
            "observation": {"tool_name": "get_current_time", "observation_type": "current_time", "status": "ok", "data": {"now": "2026-07-26T09:00:00+08:00", "timezone": "Asia/Shanghai"}},
        }
    )


def runtime() -> FixtureBackedToolRuntimeV1:
    bundled_case = case()
    bundle = EvaluationAssetBundleV1(cases=(bundled_case,), fixtures=(fixture(),), reviews=())
    return FixtureBackedToolRuntimeV1(bundled_case, ToolFixtureMatcherV1(bundle))


def test_runtime_returns_fixture_observation_and_safe_stable_digest() -> None:
    first = runtime()
    observation = first.get_current_time(NoArguments())
    observation.data["now"] = "changed"
    again = first.get_current_time(NoArguments())
    assert again.data["now"] == "2026-07-26T09:00:00+08:00"
    assert first.events[0].argument_digest == first.events[1].argument_digest
    assert first.events[0].argument_keys == ()
    assert "2026-07-26T09:00:00+08:00" not in str(first.events[0])


def test_runtime_fails_closed_when_a_fixture_is_missing() -> None:
    missing_case = case().model_copy(update={"tool_fixture_ids": []})
    bundle = EvaluationAssetBundleV1(cases=(missing_case,), fixtures=(), reviews=())
    missing = FixtureBackedToolRuntimeV1(missing_case, ToolFixtureMatcherV1(bundle))
    with pytest.raises(FixtureNotFoundRuntimeError):
        missing.get_current_time(NoArguments())
    assert missing.events[0].blocked_reason == "fixture_not_found"
