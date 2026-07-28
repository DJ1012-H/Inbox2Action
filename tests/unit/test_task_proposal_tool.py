from __future__ import annotations

import pytest
from pydantic import ValidationError

from inbox2action.evaluation.asset_bundle import EvaluationAssetBundleV1
from inbox2action.evaluation.assets import EvaluationCaseV1, ToolFixtureV1
from inbox2action.evaluation.fixture_matcher import ToolFixtureMatcherV1
from inbox2action.evaluation.fixture_runtime import FixtureBackedToolRuntimeV1
from inbox2action.llm.models import ToolCall
from inbox2action.tools.mock_tools import MockToolRuntime
from inbox2action.tools.policy import InvalidToolArgumentsError
from inbox2action.tools.registry import ToolRegistry
from inbox2action.tools.schemas import SaveTaskProposalArgs


def _call(arguments: str) -> ToolCall:
    return ToolCall(id="task-call-1", name="save_task_proposal", arguments=arguments)


def test_schema_requires_an_explicit_offset_and_rejects_external_fields() -> None:
    parsed = SaveTaskProposalArgs.model_validate(
        {
            "title": "task title",
            "description": "task description",
            "due_at": "2026-07-30T18:00:00+08:00",
            "priority": "high",
        }
    )
    assert parsed.due_at is not None
    assert parsed.due_at.isoformat() == "2026-07-30T18:00:00+08:00"

    with pytest.raises(ValidationError, match="explicit UTC offset"):
        SaveTaskProposalArgs.model_validate(
            {
                "title": "task title",
                "description": "task description",
                "due_at": "2026-07-30T18:00:00",
                "priority": "high",
            }
        )

    with pytest.raises(ValidationError):
        SaveTaskProposalArgs.model_validate(
            {
                "title": "task title",
                "description": "task description",
                "priority": "medium",
                "clickup_token": "must-not-be-accepted",
            }
        )


def test_registry_saves_only_an_in_memory_task_proposal() -> None:
    runtime = MockToolRuntime()
    registry = ToolRegistry(runtime)

    observation = registry.execute(
        _call(
            '{"title":"task title","description":"task description",'
            '"due_at":"2026-07-30T18:00:00+08:00","priority":"high"}'
        )
    )

    assert "save_task_proposal" in registry.openai_tool_names()
    assert observation.data["saved"] is True
    assert observation.data["proposal_type"] == "task"
    assert observation.data["external_side_effect"] is False
    assert len(runtime.task_proposals) == 1
    assert runtime.task_proposals[0].proposal_id == "task-proposal-1"
    assert registry.validate_call(
        _call(
            '{"title":"task title","description":"private description",'
            '"priority":"medium"}'
        )
    ).trace_arguments == {
        "title_length": len("task title"),
        "description_length": len("private description"),
        "due_at_present": False,
        "priority": "medium",
    }


def test_invalid_task_proposal_never_executes_runtime() -> None:
    runtime = MockToolRuntime()
    registry = ToolRegistry(runtime)

    with pytest.raises(InvalidToolArgumentsError):
        registry.execute(_call('{"title":"","description":"x","priority":"high"}'))

    assert runtime.task_proposals == []


def test_fixture_runtime_matches_task_proposal_arguments_exactly() -> None:
    case = EvaluationCaseV1.model_validate(
        {
            "schema_version": "1.0",
            "dataset_version": "deepseek-validation-v1",
            "case_id": "task-proposal-fixture-001",
            "category": "task",
            "subcategory": "mock",
            "language": "zh-CN",
            "current_time": "2026-07-26T14:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "email": {"from": "sender@example.com", "subject": "subject", "body": "body"},
            "user_context": {},
            "expected": {
                "triage": "ACTION_REQUIRED",
                "required_tools": ["save_task_proposal"],
                "allowed_tool_sequences": [["save_task_proposal", "done"]],
                "forbidden_tools": [],
                "argument_assertions": {"save_task_proposal": {"title": "task title"}},
                "safety": {},
            },
            "tool_fixture_ids": ["fixture-task-proposal-001"],
        }
    )
    fixture = ToolFixtureV1.model_validate(
        {
            "schema_version": "1.0",
            "dataset_version": "deepseek-validation-v1",
            "fixture_id": "fixture-task-proposal-001",
            "case_id": case.case_id,
            "tool_name": "save_task_proposal",
            "arguments_match": {
                "title": "task title",
                "description": "task description",
                "due_at": "2026-07-30T18:00:00+08:00",
                "priority": "high",
            },
            "observation": {
                "tool_name": "save_task_proposal",
                "observation_type": "task_proposal",
                "status": "proposal_created",
                "data": {"saved": True, "proposal_type": "task", "external_side_effect": False},
            },
        }
    )
    runtime = FixtureBackedToolRuntimeV1(
        case,
        ToolFixtureMatcherV1(EvaluationAssetBundleV1(cases=(case,), fixtures=(fixture,), reviews=())),
    )

    observation = runtime.save_task_proposal(
        SaveTaskProposalArgs.model_validate(
            {
                "title": "task title",
                "description": "task description",
                "due_at": "2026-07-30T18:00:00+08:00",
                "priority": "high",
            }
        )
    )

    assert observation.data["external_side_effect"] is False
    assert runtime.events[-1].fixture_id == fixture.fixture_id
