from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from inbox2action.evaluation.assets import (
    EmailMessageV1,
    EvaluationCaseV1,
    EvaluationCategoryV1,
    ReviewRecordV1,
    ReviewStatus,
    ToolFixtureV1,
    load_evaluation_cases,
    load_tool_fixtures,
)
from inbox2action.llm.models import TriageDecision

PROJECT_ROOT = Path(__file__).parents[2]


def case_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "dataset_version": "deepseek-validation-v1",
        "case_id": "case-001",
        "category": "ordinary",
        "subcategory": "confirmation",
        "language": "en",
        "current_time": "2026-07-26T09:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "email": {
            "from": "sender@example.com",
            "subject": "Receipt confirmed",
            "body": "This is a synthetic evaluation email.",
        },
        "user_context": {},
        "expected": {
            "triage": "IGNORE",
            "required_tools": [],
            "allowed_tool_sequences": [["done"]],
            "forbidden_tools": [],
            "argument_assertions": {},
            "safety": {},
        },
        "tool_fixture_ids": [],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("category", "triage"),
    [
        ("ordinary", "IGNORE"),
        ("task", "ACTION_REQUIRED"),
        ("calendar", "ACTION_REQUIRED"),
    ],
)
def test_valid_formal_case_categories(category: str, triage: str) -> None:
    payload = case_payload(category=category)
    expected = payload["expected"]
    assert isinstance(expected, dict)
    expected["triage"] = triage
    case = EvaluationCaseV1.model_validate(payload)
    assert case.category.value == category
    assert case.expected.triage.value == triage


def test_prompt_injection_can_forbid_writes_and_end_with_done() -> None:
    case = EvaluationCaseV1.model_validate(
        case_payload(
            category="prompt_injection",
            expected={
                "triage": "ACTION_REQUIRED",
                "required_tools": [],
                "allowed_tool_sequences": [["done"]],
                "forbidden_tools": ["send_email"],
                "argument_assertions": {},
                "safety": {"secret_disclosures": 0},
            },
        )
    )
    assert case.expected.forbidden_tools == ["send_email"]


def test_case_allows_multiple_distinct_tool_sequences() -> None:
    case = EvaluationCaseV1.model_validate(
        case_payload(
            expected={
                "triage": "ACTION_REQUIRED",
                "required_tools": ["get_current_time"],
                "allowed_tool_sequences": [
                    ["get_current_time", "ask_user", "done"],
                    ["get_current_time", "done"],
                ],
                "forbidden_tools": [],
                "argument_assertions": {"get_current_time": {}},
                "safety": {},
            }
        )
    )
    assert len(case.expected.allowed_tool_sequences) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("current_time", "2026-07-26T09:00:00"),
        ("timezone", "Mars/Olympus_Mons"),
        ("current_time", "2026-07-26T09:00:00+00:00"),
    ],
)
def test_case_rejects_invalid_time_context(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        EvaluationCaseV1.model_validate(case_payload(**{field: value}))


def test_case_rejects_non_example_com_sender() -> None:
    with pytest.raises(ValidationError):
        EvaluationCaseV1.model_validate(
            case_payload(email={"from": "sender@invalid.test", "subject": "x", "body": "x"})
        )


@pytest.mark.parametrize(
    "expected",
    [
        {
            "triage": "IGNORE",
            "required_tools": ["get_current_time"],
            "allowed_tool_sequences": [["done"]],
            "forbidden_tools": [],
            "argument_assertions": {},
            "safety": {},
        },
        {
            "triage": "IGNORE",
            "required_tools": [],
            "allowed_tool_sequences": [["done", "send_email"]],
            "forbidden_tools": ["send_email"],
            "argument_assertions": {},
            "safety": {},
        },
        {
            "triage": "IGNORE",
            "required_tools": ["done"],
            "allowed_tool_sequences": [["done"]],
            "forbidden_tools": ["done"],
            "argument_assertions": {},
            "safety": {},
        },
        {
            "triage": "IGNORE",
            "required_tools": [],
            "allowed_tool_sequences": [["done"]],
            "forbidden_tools": [],
            "argument_assertions": {"unknown_tool": {}},
            "safety": {},
        },
        {
            "triage": "IGNORE",
            "required_tools": [],
            "allowed_tool_sequences": [["done"], ["done"]],
            "forbidden_tools": [],
            "argument_assertions": {},
            "safety": {},
        },
    ],
)
def test_case_rejects_invalid_tool_contracts(expected: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EvaluationCaseV1.model_validate(case_payload(expected=expected))


def test_loaders_reject_duplicate_ids_and_redact_email_body(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    first = case_payload()
    second = case_payload()
    second["email"] = {
        "from": "other@example.com",
        "subject": "Other",
        "body": "sensitive synthetic body that must not be shown",
    }
    cases_path.write_text(
        f"{json.dumps(first)}\n{json.dumps(second)}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match=r"cases\.jsonl at line 2") as captured:
        load_evaluation_cases(cases_path)
    assert "sensitive synthetic body" not in str(captured.value)

    fixture_path = tmp_path / "fixtures.jsonl"
    fixture = {
        "schema_version": "1.0",
        "dataset_version": "deepseek-validation-v1",
        "fixture_id": "fixture-001",
        "case_id": "case-001",
        "tool_name": "done",
        "arguments_match": {},
        "observation": {},
    }
    fixture_path.write_text(
        f"{json.dumps(fixture)}\n{json.dumps(fixture)}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match=r"fixtures\.jsonl at line 2"):
        load_tool_fixtures(fixture_path)


def test_jsonl_error_has_a_line_number_without_body(tmp_path: Path) -> None:
    path = tmp_path / "malformed.jsonl"
    path.write_text('{"email":{"body":"private body"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"malformed\.jsonl at line 1") as captured:
        load_evaluation_cases(path)
    assert "private body" not in str(captured.value)


def test_from_alias_round_trips_and_schema_uses_external_name() -> None:
    message = EmailMessageV1.model_validate(
        {"from": "sender@example.com", "subject": "Subject", "body": "Body"}
    )
    assert message.from_address == "sender@example.com"
    assert message.model_dump(by_alias=True)["from"] == "sender@example.com"
    schema = EvaluationCaseV1.model_json_schema(by_alias=True)
    assert "from" in schema["$defs"]["EmailMessageV1"]["properties"]


def test_exported_schemas_match_models_and_review_defaults_to_draft() -> None:
    schemas = {
        "evaluation-case.schema.json": EvaluationCaseV1,
        "tool-fixture.schema.json": ToolFixtureV1,
        "review-record.schema.json": ReviewRecordV1,
    }
    for filename, model in schemas.items():
        exported = json.loads(
            (PROJECT_ROOT / "evaluation" / "schemas" / filename).read_text(
                encoding="utf-8"
            )
        )
        assert exported == model.model_json_schema(by_alias=True)

    review = ReviewRecordV1.model_validate(
        {
            "schema_version": "1.0",
            "dataset_version": "deepseek-validation-v1",
            "case_id": "case-001",
            "reviewer": "Human Reviewer",
            "reviewed_at": "2026-07-26",
            "changes": [],
        }
    )
    assert review.status is ReviewStatus.DRAFT


def test_formal_contract_reuses_existing_triage_decisions() -> None:
    case = EvaluationCaseV1.model_validate(case_payload())
    assert case.expected.triage is TriageDecision.IGNORE
    assert case.category is EvaluationCategoryV1.ORDINARY


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        EvaluationCaseV1.model_validate(case_payload(unexpected="no"))
